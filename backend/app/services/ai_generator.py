import json
import os
import re
import asyncio
import logging
import hashlib
import time
from typing import Callable, Optional
import httpx
from json_repair import repair_json
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError
from app.config import settings
from app.utils.bot_config_loader import load_bot_config
from app.services.skill_prompts import (
    SKILL_EXTRACT_MODULES,
    SKILL_GENERATE_FOR_MODULE,
    SKILL_EXTRACT_CONSTRAINTS,
    SKILL_BOUNDARY_COMPLETION,
    SKILL_STATE_TRANSITION,
    SKILL_REFINE_STEPS,
    SKILL_DEDUPLICATE,
)
from app.services.skill_executor import post_validation, check_module_availability
from app.utils.id_generator import generate_case_id

logger = logging.getLogger(__name__)

# Module extraction cache: prd_hash → (timestamp, modules)
# Avoids re-running Skill 1 for identical PRDs within 24 hours
_module_extraction_cache: dict = {}
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Human-readable labels for each progress step
SKILL_LABELS = {
    "extract_modules": "提取功能模块",
    "extract_modules_implicit": "扫描隐含模块",
    "generate_for_module": "逐模块生成用例",
    "extract_constraints": "提取字段约束",
    "boundary_completion": "补充边界用例",
    "state_transition": "状态转换补充",
    "refine_steps": "步骤具体化",
    "deduplicate": "语义去重与校验",
}

# State-transition keywords for conditional Skill 5
STATE_TRANSITION_KEYWORDS = [
    "状态", "流转", "审批", "审核", "驳回", "通过", "提交",
    "待处理", "处理中", "已完成", "已关闭", "进行中", "待审核",
    "status", "state", "workflow", "approve", "reject",
]


class AIGenerationError(Exception):
    pass


class GenerationCancelledError(AIGenerationError):
    pass


class LLMClient:
    """DeepSeek API wrapper (OpenAI-compatible) with retry on timeout."""

    def __init__(self, bot_name: str = "testcase_generator"):
        self.bot_name = bot_name
        try:
            config = load_bot_config(bot_name)
        except Exception as e:
            logger.warning(
                f"Failed to load bot_config.yaml for '{bot_name}': {e}. "
                f"Falling back to defaults."
            )
            config = {}

        api_key = (
            config.get("api_key", "")
            or settings.deepseek_api_key
            or os.getenv("DEEPSEEK_API_KEY", "")
        )
        base_url = config.get("base_url") or "https://api.deepseek.com/v1"

        request_timeout = float(config.get("request_timeout", 120))
        timeout = httpx.Timeout(timeout=request_timeout, connect=30.0)

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = config.get("model") or "deepseek-chat"
        self.temperature = config.get("temperature", 0.15)
        self.max_tokens = config.get("max_tokens", 8192)

    async def chat(self, system: str, user: str, max_tokens: int = None,
                   temperature: float = None) -> tuple[str, str]:
        """Returns (content, finish_reason). finish_reason='length' means output was truncated."""
        tokens = max_tokens or self.max_tokens
        temp = temperature if temperature is not None else self.temperature
        for attempt in range(2):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temp,
                    max_tokens=tokens,
                )
                choice = response.choices[0]
                content = choice.message.content or ""
                finish_reason = choice.finish_reason or ""
                return content, finish_reason
            except (APITimeoutError, APIConnectionError) as e:
                if attempt < 1:
                    await asyncio.sleep(1)
                    logger.warning(
                        f"LLM call timed out (attempt {attempt + 1}/2). "
                        f"Retrying..."
                    )
                else:
                    raise AIGenerationError(
                        f"LLM API 调用失败: 连续 2 次超时。"
                        f"请检查网络连接或确认 DeepSeek API Key 有效。"
                    )
            except Exception as e:
                raise AIGenerationError(f"LLM API 调用失败: {e}")


class AIGenerator:
    """Orchestrates the 7+1 Skill pipeline to generate test cases from PRD text."""

    def __init__(self, llm: LLMClient = None):
        self.llm = llm or LLMClient()

    @staticmethod
    def validate_prd(prd_text: str) -> tuple[bool, str, str]:
        """Validate PRD content before generation. Returns (valid, error_type, message)."""
        if not prd_text or not prd_text.strip():
            return False, "PRD_EMPTY", "PRD 内容为空，请上传或输入 PRD 文档"
        stripped = prd_text.strip()
        if len(stripped) < 50:
            return False, "PRD_TOO_SHORT", "PRD 内容过短（少于 50 字符），无法提取功能模块"
        # Heuristic: PRD should have some structural markers
        has_structure = bool(re.search(r'[#＃]+\s|模块|功能|需求|用户|系统|页面|接口', stripped))
        if not has_structure:
            return False, "PRD_TOO_SHORT", "PRD 缺少明显的功能描述结构，请确认内容为完整需求文档"
        return True, "", ""

    @staticmethod
    def _normalize_module(mod) -> dict:
        """Normalize a module entry to always be a dict. LLM may return strings."""
        if isinstance(mod, dict):
            return mod
        if isinstance(mod, str):
            return {"name": mod, "summary": mod, "relevant_text": mod}
        return {"name": str(mod), "summary": str(mod)}

    @staticmethod
    def _normalize_modules(modules: list) -> list:
        """Ensure every item in the modules list is a dict with at least a 'name' key."""
        normalized = []
        for mod in modules:
            norm = AIGenerator._normalize_module(mod)
            if norm.get("name"):  # skip truly empty entries
                normalized.append(norm)
        return normalized

    async def generate(self, prd_text: str,
                       progress_callback: Optional[Callable] = None,
                       cancellation_event: Optional[asyncio.Event] = None,
                       save_callback: Optional[Callable] = None) -> dict:
        """
        Run the full generation pipeline with mandatory per-module coverage.
        Every extracted module gets at least one test case, even with incomplete PRD info.
        If save_callback is provided, called with (cases, stats) after module batch so timeout preserves partial results.
        Returns {"status", "testcases", "stats", "failure"/"validation_issues"}.
        """
        async def _check_cancelled():
            if cancellation_event and cancellation_event.is_set():
                raise GenerationCancelledError("生成已被用户取消")

        async def _report(skill_index: int, skill_name: str, detail: str = ""):
            if progress_callback:
                try:
                    await progress_callback({
                        "skill_index": skill_index,
                        "skill_name": SKILL_LABELS.get(skill_name, skill_name),
                        "current_skill": skill_name,
                        "total_skills": 8,
                        "detail": detail,
                    })
                except Exception:
                    pass  # never let progress failure kill generation

        # Validate PRD content before any LLM call
        prd_valid, prd_error_type, prd_error_msg = self.validate_prd(prd_text)
        if not prd_valid:
            return {
                "status": "failed",
                "testcases": [],
                "failure": {
                    "reason": prd_error_type,
                    "details": [prd_error_msg],
                    "suggestion": "请提供完整的功能需求描述后重试",
                },
            }

        # Skill 1: Extract modules + intermediate representation
        # Check cache first — avoid re-running LLM for identical PRDs within TTL
        prd_hash = hashlib.sha256(prd_text.encode("utf-8")).hexdigest()
        cached = _module_extraction_cache.get(prd_hash)
        use_cache = False
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            intermediate_rep = cached[1]
            if not isinstance(intermediate_rep, (dict, list)):
                logger.warning(f"Discarding stale cache entry for hash={prd_hash[:12]}... (type={type(intermediate_rep).__name__})")
                del _module_extraction_cache[prd_hash]
            else:
                use_cache = True
                logger.info(f"Skill 1: Using cached module extraction (hash={prd_hash[:12]}...)")

        if not use_cache:
            await _check_cancelled()
            await _report(1, "extract_modules")
            logger.info("Skill 1: Extracting modules (pass 1: structure-based)...")
            intermediate_rep = await self._run_skill(
                "extract_modules", SKILL_EXTRACT_MODULES,
                f"以下是要分析的PRD文档：\n\n{prd_text}"
            )
            if isinstance(intermediate_rep, list):
                intermediate_rep = {"modules": intermediate_rep}

            # S1: Second pass — scan for implicit modules via verb phrases
            await _check_cancelled()
            await _report(2, "extract_modules_implicit")
            implicit_prompt = (
                SKILL_EXTRACT_MODULES
                + "\n\n【第二轮提取】请重新扫描PRD，专门识别第一轮可能遗漏的隐含模块。"
                + "重点关注：\n"
                + "1. 散落在非功能描述中的功能需求（如'支持导出'、'需要记录日志'）\n"
                + "2. 多处分散描述但未形成独立标题的功能\n"
                + "3. 以动宾短语形式出现的隐含功能（'查看xxx'、'删除xxx'、'修改xxx'）\n"
                + "只输出第一轮遗漏的模块，如果确认没有遗漏则返回 {\"modules\": []}"
            )
            try:
                implicit_rep = await self._run_skill(
                    "extract_modules_implicit", implicit_prompt,
                    f"以下是要分析的PRD文档：\n\n{prd_text}",
                    temperature=0.25  # slightly higher temp for broader scan
                )
                if isinstance(implicit_rep, list):
                    implicit_rep = {"modules": implicit_rep}
                implicit_modules = implicit_rep.get("modules", []) if isinstance(implicit_rep, dict) else []
            except Exception as e:
                logger.warning(f"Second-pass module extraction failed, using first pass only: {e}")
                implicit_modules = []

            # Merge: deduplicate by module name
            existing_names = {m.get("name", "") for m in intermediate_rep.get("modules", [])}
            new_from_implicit = []
            for m in implicit_modules:
                m_name = m.get("name", "")
                if m_name and m_name not in existing_names:
                    new_from_implicit.append(m)
                    existing_names.add(m_name)
            if new_from_implicit:
                logger.info(
                    f"  Second pass found {len(new_from_implicit)} additional modules: "
                    f"{[m.get('name') for m in new_from_implicit]}"
                )
                intermediate_rep["modules"].extend(new_from_implicit)

            # Cache the result
            _module_extraction_cache[prd_hash] = (time.time(), intermediate_rep)
            # Cleanup stale entries (>24h)
            stale = [h for h, (ts, _) in _module_extraction_cache.items()
                      if time.time() - ts > _CACHE_TTL_SECONDS]
            for h in stale:
                del _module_extraction_cache[h]

        all_modules = self._normalize_modules(intermediate_rep.get("modules", []))
        intermediate_rep["modules"] = all_modules
        if not all_modules:
            return {
                "status": "failed",
                "testcases": [],
                "failure": {
                    "reason": "no_modules_extracted",
                    "details": ["未能从PRD中提取到任何功能模块"],
                    "suggestion": "请确认PRD文档内容完整且包含功能描述",
                },
            }

        # Check module info completeness (no skipping — all modules proceed)
        valid_modules, module_warnings = check_module_availability(intermediate_rep)
        if module_warnings:
            logger.warning(
                f"{len(module_warnings)} module(s) have incomplete info, "
                f"will generate best-effort cases with notes"
            )

        # Extract global context once for all modules (S4)
        global_context = self._extract_global_context(prd_text)
        if global_context:
            logger.info("Global context extracted for cross-module enrichment")

        # Skill 2: Generate cases per module with enriched input + higher tokens
        await _check_cancelled()
        await _report(3, "generate_for_module",
                       f"准备为 {len(valid_modules)} 个模块生成用例...")
        logger.info(f"Skill 2: Generating cases for {len(valid_modules)} modules...")
        all_cases = []
        completed_count = [0]  # mutable counter for progress
        semaphore = asyncio.Semaphore(5)  # max 5 concurrent LLM calls

        async def _generate_one_module(idx: int, mod: dict) -> list:
            if isinstance(mod, str):
                mod = {"name": mod, "summary": mod}
            mod_name = mod.get("name", "")
            async with semaphore:
                await _check_cancelled()
                logger.info(f"  Generating module {idx + 1}/{len(valid_modules)}: {mod_name}")
                mod_input = self._build_module_input(mod, global_context)
                try:
                    cases = await self._run_skill(
                        "generate_for_module", SKILL_GENERATE_FOR_MODULE,
                        mod_input, skill_max_tokens=self.llm.max_tokens
                    )
                except AIGenerationError:
                    logger.warning(f"    LLM error for module '{mod_name}', skipping")
                    return []
                if isinstance(cases, list):
                    for c in cases:
                        c.setdefault("module", mod_name)
                    completed_count[0] += 1
                    await _report(3, "generate_for_module",
                                   f"模块 {completed_count[0]}/{len(valid_modules)}: {mod_name} ✓")
                    logger.info(f"    Generated {len(cases)} cases for '{mod_name}'")
                    return cases
                else:
                    completed_count[0] += 1
                    logger.warning(f"    Failed to generate cases for '{mod_name}'")
                    return []

        # Execute all module generations in parallel (max 3 at a time)
        results = await asyncio.gather(*[
            _generate_one_module(i, mod) for i, mod in enumerate(valid_modules)
        ], return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_cases.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"  Module generation failed with exception: {result}")

        # Skill 2b: Cross-check — retry any modules with zero cases (temp escalation)
        all_module_names = [m.get("name", "") for m in all_modules]
        covered_modules = set(c.get("module", "") for c in all_cases)
        missing_modules = [m for m in all_modules if m.get("name", "") not in covered_modules]

        # Save partial results so timeout doesn't lose all progress
        if save_callback and all_cases:
            try:
                await save_callback(all_cases, {
                    "modules_found": len(all_modules),
                    "modules_covered": len(covered_modules),
                    "total_cases": len(all_cases),
                })
            except Exception:
                pass

        # Initialize module state tracking
        module_states = {}
        for m in all_modules:
            name = m.get("name", "")
            module_states[name] = {"status": "covered" if name in covered_modules else "failed", "retries": 0}

        if missing_modules:
            await _check_cancelled()
            await _report(3, "generate_for_module",
                           f"重试 {len(missing_modules)} 个遗漏模块...")
            logger.warning(
                f"  {len(missing_modules)} module(s) have no cases, retrying: "
                f"{[m.get('name') for m in missing_modules]}"
            )
            # Temperature escalation: 0.25 → 0.35 for retries to break determinism
            retry_temps = [0.25, 0.35]
            for mod in missing_modules:
                mod_name = mod.get("name", "")
                mod_input = self._build_module_input(mod, global_context)
                retry_prompt = (
                    SKILL_GENERATE_FOR_MODULE
                    + "\n\n【重要提醒】上一轮你未给该模块生成任何测试用例。"
                    + "请务必至少生成一条P0正向用例，即使信息不完整也必须在notes中标注。"
                )
                # Try with escalating temperatures
                for retry_idx, retry_temp in enumerate(retry_temps):
                    logger.info(
                        f"  Retrying module '{mod_name}' with temp={retry_temp} "
                        f"(attempt {retry_idx + 1}/{len(retry_temps)})"
                    )
                    cases = await self._run_skill(
                        "generate_for_module", retry_prompt,
                        mod_input, skill_max_tokens=self.llm.max_tokens,
                        temperature=retry_temp
                    )
                    if isinstance(cases, list) and len(cases) > 0:
                        for c in cases:
                            c.setdefault("module", mod_name)
                        all_cases.extend(cases)
                        module_states[mod_name] = {"status": "covered", "retries": retry_idx + 1}
                        logger.info(f"    Retry generated {len(cases)} cases for '{mod_name}'")
                        break
                else:
                    # All retries failed
                    module_states[mod_name] = {
                        "status": "failed",
                        "retries": len(retry_temps),
                        "reason": "生成失败（已尝试不同温度重试）"
                    }
                    logger.warning(f"    All retries failed for '{mod_name}'")

        # Skill 3+5: Extract constraints and state transitions in parallel
        # Both are independent — only depend on PRD text, not on each other
        await _check_cancelled()
        await _report(4, "extract_constraints", "并行提取约束与状态转换...")
        logger.info("Skills 3+5: Running extract_constraints & state_transition in parallel...")

        # Check if PRD has state-transition content; skip Skill 5 if not
        prd_lower = prd_text.lower()
        has_state_transitions = any(
            kw in prd_lower for kw in STATE_TRANSITION_KEYWORDS
        )

        async def _run_extract_constraints():
            constraints = await self._run_skill(
                "extract_constraints", SKILL_EXTRACT_CONSTRAINTS,
                f"以下是要分析的PRD文档：\n\n{prd_text}"
            )
            return constraints if isinstance(constraints, list) else []

        async def _run_state_transition():
            if not has_state_transitions:
                logger.info("  No state-transition keywords found in PRD, skipping Skill 5")
                return []
            state_cases = await self._run_skill(
                "state_transition", SKILL_STATE_TRANSITION,
                f"PRD文档：\n{prd_text}\n已有用例标题：{[c.get('title', '') for c in all_cases]}"
            )
            return state_cases if isinstance(state_cases, list) else []

        constraints, state_cases = await asyncio.gather(
            _run_extract_constraints(), _run_state_transition()
        )
        all_cases.extend(state_cases)

        # Skill 4: Boundary completion (only for explicit constraints found in Skill 3)
        explicit_constraints = [
            c for c in constraints
            if c.get("constraints") and c.get("constraints") != "PRD未明确"
        ]
        if explicit_constraints:
            await _check_cancelled()
            await _report(5, "boundary_completion")
            logger.info(f"Skill 4: Boundary completion with {len(explicit_constraints)} explicit constraints...")
            boundary_cases = await self._run_skill(
                "boundary_completion", SKILL_BOUNDARY_COMPLETION,
                f"字段约束（仅含明确约束）：{json.dumps(explicit_constraints, ensure_ascii=False)}\n已有用例数：{len(all_cases)}"
            )
            if isinstance(boundary_cases, list):
                all_cases.extend(boundary_cases)

        # Skill 6-8 Loop: refine → deduplicate → validate (max 2 retries)
        await _check_cancelled()
        await _report(7, "refine_steps")
        MAX_RETRIES = 2
        deduped = []
        validation = {}
        for attempt in range(MAX_RETRIES + 1):
            logger.info(f"Refine-Dedup-Validate attempt {attempt + 1}...")

            # Skill 6: Refine steps
            refine_prompt = SKILL_REFINE_STEPS
            if attempt > 0:
                refine_prompt += f"\n\n上一次校验发现以下问题，请针对性修正：\n{json.dumps(validation.get('issues', []), ensure_ascii=False)}"
            refined = await self._run_skill(
                "refine_steps", refine_prompt,
                f"以下用例需要步骤细化：\n{json.dumps(all_cases, ensure_ascii=False)}"
            )
            if not isinstance(refined, list):
                refined = all_cases
            elif len(refined) != len(all_cases):
                logger.warning(
                    f"  Refine changed case count: {len(all_cases)} → {len(refined)}. "
                    f"Reverting to pre-refine cases to avoid silent drop."
                )
                refined = all_cases

            # Skill 7: Deduplicate
            await _report(8, "deduplicate",
                           f"校验与去重 (第 {attempt + 1} 轮)")
            deduped = await self._run_skill(
                "deduplicate", SKILL_DEDUPLICATE,
                f"以下用例需要去重审核：\n{json.dumps(refined, ensure_ascii=False)}"
            )
            if not isinstance(deduped, list):
                deduped = refined
            elif len(deduped) < len(refined) * 0.5:
                logger.warning(
                    f"  Dedup dropped {len(refined) - len(deduped)}/{len(refined)} cases "
                    f"(>{50}%). Too aggressive — reverting to pre-dedup cases."
                )
                deduped = refined

            # Skill 8: Post-validation (non-LLM)
            validation = post_validation(deduped, intermediate_rep, prd_text)
            if validation["passed"]:
                break
            elif attempt < MAX_RETRIES:
                logger.info(f"  Validation found {len(validation.get('issues', []))} issues, retrying...")
                all_cases = deduped
            else:
                logger.warning(f"  Validation still failing after {MAX_RETRIES} retries")

        # Assign case IDs
        for i, tc in enumerate(deduped):
            tc["case_id"] = generate_case_id(i)

        # Build stats
        final_covered = set(c.get("module", "") for c in deduped)
        final_missing = [m for m in all_module_names if m not in final_covered]

        # Update module_states with final coverage status
        for m_name in all_module_names:
            if m_name in final_covered:
                module_states.setdefault(m_name, {})["status"] = "covered"
            elif module_states.get(m_name, {}).get("retries", 0) >= 2:
                module_states[m_name] = {
                    "status": "needs_prd_update",
                    "retries": module_states[m_name]["retries"],
                    "reason": "多次生成失败，可能PRD信息不足"
                }
            else:
                module_states.setdefault(m_name, {"status": "failed", "retries": 0})

        result = {
            "status": "completed",
            "testcases": deduped,
            "stats": {
                "modules_found": len(all_modules),
                "modules_with_warnings": len(module_warnings),
                "warning_details": module_warnings,
                "modules_covered": len(all_module_names) - len(final_missing),
                "modules_uncovered": final_missing,
                "total_cases": len(deduped),
                "module_states": module_states,
            },
        }
        if not validation.get("passed") or final_missing:
            result["status"] = "partial"
            result["validation_issues"] = validation.get("issues", [])
            if final_missing:
                result["validation_issues"].append({
                    "type": "missing_module_coverage",
                    "detail": f"以下模块仍未生成用例：{final_missing}",
                    "suggestion": "请补充PRD中对应模块的详细信息后重新生成",
                })

        return result

    def _extract_global_context(self, prd_text: str) -> str:
        """Extract global context from PRD: roles, common rules, error handling sections."""
        parts = []
        # Look for role definitions
        role_patterns = [
            r'(?:角色|用户角色|权限角色)[：:]\s*(.+?)(?:\n|$)',
            r'(?:用户类型|参与者)[：:]\s*(.+?)(?:\n|$)',
        ]
        for pat in role_patterns:
            m = re.search(pat, prd_text, re.IGNORECASE)
            if m:
                parts.append(f"角色定义：{m.group(1).strip()}")

        # Look for common/global rules
        rule_section = re.search(
            r'(?:公共规则|通用规则|全局规则|通用约束)[：:]*\s*\n(.+?)(?=\n#|\n##|\Z)',
            prd_text, re.IGNORECASE | re.DOTALL
        )
        if rule_section:
            parts.append(f"公共规则：{rule_section.group(1).strip()[:2000]}")

        # Look for error/exception handling
        error_section = re.search(
            r'(?:异常处理|错误处理|异常场景)[：:]*\s*\n(.+?)(?=\n#|\n##|\Z)',
            prd_text, re.IGNORECASE | re.DOTALL
        )
        if error_section:
            parts.append(f"异常处理：{error_section.group(1).strip()[:1000]}")

        # Look for auth/session requirements
        auth_section = re.search(
            r'(?:登录要求|认证方式|权限控制|鉴权)[：:]*\s*\n(.+?)(?=\n#|\n##|\Z)',
            prd_text, re.IGNORECASE | re.DOTALL
        )
        if auth_section:
            parts.append(f"认证要求：{auth_section.group(1).strip()[:1000]}")

        return "\n".join(parts) if parts else ""

    def _build_module_input(self, mod: dict, global_context: str = "") -> str:
        """Build enriched user input for a single module, with optional global context."""
        # Defensive: normalize to dict if string was passed
        if isinstance(mod, str):
            mod = {"name": mod, "summary": mod, "relevant_text": mod}
        parts = []
        if global_context:
            parts.append("【全局信息】")
            parts.append(global_context)
            parts.append("【当前模块】")
        parts.extend([
            f"模块名：{mod.get('name', '')}",
            f"概述：{mod.get('summary', '')}",
        ])
        if mod.get("ui_elements"):
            parts.append(f"UI元素：{json.dumps(mod['ui_elements'], ensure_ascii=False)}")
        else:
            parts.append("UI元素：PRD未明确列出（请根据业务规则推断，并在notes中标注）")
        if mod.get("fields"):
            parts.append(f"输入字段：{json.dumps(mod['fields'], ensure_ascii=False)}")
        if mod.get("actions"):
            parts.append(f"用户操作：{json.dumps(mod['actions'], ensure_ascii=False)}")
        if mod.get("rules_explicit"):
            parts.append(f"业务规则：{json.dumps(mod['rules_explicit'], ensure_ascii=False)}")
        if mod.get("states"):
            parts.append(f"状态：{json.dumps(mod['states'], ensure_ascii=False)}")
        if mod.get("missing_info"):
            parts.append(f"缺失信息（需在用例notes中标注）：{json.dumps(mod['missing_info'], ensure_ascii=False)}")
        parts.append(f"PRD原文：{mod.get('relevant_text', '')}")
        return "\n".join(parts)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM output: strip markdown fences, match brackets."""
        text = text.strip()
        # Strip ```json / ``` fences
        m = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Find first JSON-like bracket span (prefer objects over arrays)
        for left, right in [('{', '}'), ('[', ']')]:
            start = text.find(left)
            end = text.rfind(right)
            if start != -1 and end != -1 and end > start:
                return text[start:end + 1]
        # Fallback: if text looks like a plain string but contains newlines,
        # the LLM may have returned a free-text response. Return as-is;
        # caller should handle the parse failure gracefully.
        return text

    async def _run_skill(self, name: str, system_prompt: str, user_input: str,
                         skill_max_tokens: int = None, temperature: float = None) -> dict | list:
        def _safe_parse_json(json_text: str) -> dict | list:
            """Parse JSON and enforce dict/list return type.
            str/int/float/bool/None from json.loads are treated as parse failures."""
            try:
                result = json.loads(json_text)
            except json.JSONDecodeError:
                repaired = repair_json(json_text)
                result = json.loads(repaired)
            if not isinstance(result, (dict, list)):
                raise json.JSONDecodeError(
                    f"Expected dict or list, got {type(result).__name__}",
                    json_text, 0
                )
            return result

        try:
            response, finish_reason = await self.llm.chat(
                system=system_prompt, user=user_input,
                max_tokens=skill_max_tokens, temperature=temperature
            )
            json_text = self._extract_json(response)
            try:
                return _safe_parse_json(json_text)
            except json.JSONDecodeError:
                logger.warning(
                    f"Skill {name}: JSON parse/repair/type-check failed, retrying..."
                )
        except AIGenerationError:
            raise
        except json.JSONDecodeError as e:
            if finish_reason == "length":
                base = skill_max_tokens or self.llm.max_tokens
                retry_tokens = base * 2
                logger.warning(
                    f"Skill {name}: output truncated (finish_reason=length). "
                    f"Retrying with {retry_tokens} tokens..."
                )
            else:
                retry_tokens = None

            logger.warning(
                f"Skill {name}: JSON parse/repair/type-check failed ({e}), retrying..."
            )
        except Exception as e:
            raise AIGenerationError(f"Skill {name} 执行失败: {e}")

        # ── Retry once with stricter prompt ──────────────────────
        retry_prompt = (
            system_prompt
            + "\n\n【重要】请输出纯 JSON，不要用 Markdown 代码块包裹。"
            + "所有字符串内的双引号必须用反斜杠转义。"
            + "确保 JSON 结构完整，最后一行是闭合的 } 或 ]。"
        )
        try:
            retry_response, retry_finish = await self.llm.chat(
                system=retry_prompt, user=user_input,
                max_tokens=retry_tokens, temperature=temperature
            )
            retry_json = self._extract_json(retry_response)
            return _safe_parse_json(retry_json)
        except AIGenerationError:
            raise
        except json.JSONDecodeError as e:
            raise AIGenerationError(
                f"Skill {name} JSON 解析失败（已尝试修复+重试）: {e}"
            )
        except Exception as e:
            raise AIGenerationError(f"Skill {name} 执行失败: {e}")


# Singleton
generator = AIGenerator()
