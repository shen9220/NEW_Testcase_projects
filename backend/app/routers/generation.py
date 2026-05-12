import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.project import GenerationStartRequest
from app.services.ai_generator import generator, AIGenerationError, GenerationCancelledError
from app.services.skill_prompts import SKILL_EXTRACT_MODULES, SKILL_GENERATE_FOR_MODULE
from app.services.log_service import log_operation
from app.repositories.local_storage import LocalStorage
from app.repositories.project_repo import ProjectRepository
from app.repositories.testcase_repo import TestcaseRepository
from app.utils.id_generator import now_iso, generate_case_id

router = APIRouter(prefix="/generation", tags=["generation"])
logger = logging.getLogger(__name__)
_local = LocalStorage()
_project_repo = ProjectRepository(_local)
_testcase_repo = TestcaseRepository(_local)

# In-memory generation state
_generation_tasks: dict = {}

GENERATION_TIMEOUT = 900  # 15-minute hard timeout for background generation


@router.post("/start")
async def start_generation(req: GenerationStartRequest, background_tasks: BackgroundTasks):
    """Start AI test case generation for a document."""
    task_id = req.task_id
    project = await _project_repo.get_by_task_id(task_id)
    if not project:
        raise HTTPException(status_code=404, detail="任务不存在")

    prd_content = project.get("prd_content") or _local.read_text(task_id, "prd_content.md")
    if not prd_content:
        raise HTTPException(status_code=400, detail="PRD 内容为空")

    # Initialize generation state with cancellation event
    cancel_event = asyncio.Event()
    _generation_tasks[task_id] = {
        "status": "processing",
        "progress": {"current_skill": "extract_modules", "skill_index": 1, "total_skills": 8, "skill_name": "提取功能模块"},
        "started_at": now_iso(),
        "_cancel_event": cancel_event,
    }

    # Run in background
    background_tasks.add_task(_run_generation, task_id, prd_content, cancel_event)

    await log_operation(task_id, "generate", f"开始AI生成测试用例，模型deepseek-chat")

    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "status": "processing",
            "message": "生成已开始，正在提取功能模块...",
        },
        "message": "success",
    }


async def _run_generation(task_id: str, prd_content: str, cancel_event: asyncio.Event = None):
    """Background task: run generation pipeline and save results."""
    async def progress_callback(progress: dict):
        """Update in-memory task state so polling frontend sees real-time progress."""
        task = _generation_tasks.get(task_id)
        if task:
            task["progress"] = progress

    async def save_callback(cases: list, stats: dict):
        """Save partial results so timeout doesn't lose all progress."""
        try:
            proj_uuid = ""
            proj = await _project_repo.get_by_task_id(task_id)
            if proj:
                proj_uuid = proj.get("id", "")
            for i, tc in enumerate(cases):
                if not tc.get("case_id"):
                    tc["case_id"] = f"TC-P{i + 1:04d}"
            await _testcase_repo.save_batch(task_id, cases, proj_uuid)
            task = _generation_tasks.get(task_id)
            if task:
                task["testcase_count"] = len(cases)
                task["stats"] = stats
            logger.info(f"Partial save: {len(cases)} cases for {task_id}")
        except Exception as e:
            logger.warning(f"Partial save failed: {e}")

    try:
        result = await asyncio.wait_for(
            generator.generate(prd_content,
                               progress_callback=progress_callback,
                               cancellation_event=cancel_event,
                               save_callback=save_callback),
            timeout=GENERATION_TIMEOUT
        )

        _generation_tasks[task_id]["status"] = result.get("status", "completed")
        _generation_tasks[task_id]["testcase_count"] = len(result.get("testcases", []))
        _generation_tasks[task_id]["stats"] = result.get("stats", {})
        _generation_tasks[task_id]["completed_at"] = now_iso()

        # Store module data for potential regenerate (F7 fix — reuse instead of re-extract)
        all_module_names = []
        all_modules = []
        if result.get("testcases"):
            seen = set()
            for tc in result["testcases"]:
                mod_name = tc.get("module", "")
                if mod_name and mod_name not in seen:
                    seen.add(mod_name)
                    all_module_names.append(mod_name)
                    all_modules.append({"name": mod_name})
        _generation_tasks[task_id]["_all_modules"] = all_modules
        _generation_tasks[task_id]["_all_module_names"] = all_module_names

        if result.get("failure"):
            _generation_tasks[task_id]["failure"] = result["failure"]
        if result.get("validation_issues"):
            _generation_tasks[task_id]["validation_issues"] = result["validation_issues"]

        # Save test cases
        testcases = result.get("testcases", [])
        if testcases:
            proj_uuid = ""
            proj = await _project_repo.get_by_task_id(task_id)
            if proj:
                proj_uuid = proj.get("id", "")
            await _testcase_repo.save_batch(task_id, testcases, proj_uuid)

        # Update project status
        await _project_repo.update_status(task_id, result.get("status", "completed"), len(testcases))
        await log_operation(task_id, "generate",
                           f"AI生成完成：{len(testcases)}条用例，"
                           f"模块{result.get('stats', {}).get('modules_found', 0)}个")

    except GenerationCancelledError:
        logger.info(f"Generation cancelled by user for {task_id}")
        # Preserve any partial results already saved
        existing = await _testcase_repo.get_all_by_task(task_id)
        _generation_tasks[task_id]["status"] = "partial"
        _generation_tasks[task_id]["testcase_count"] = len(existing) if existing else 0
        _generation_tasks[task_id]["failure"] = {
            "reason": "cancelled",
            "details": ["生成已被用户取消"],
            "suggestion": "已保留部分生成结果，可点击补全按钮继续"
        }
        _generation_tasks[task_id]["completed_at"] = now_iso()
        await _project_repo.update_status(task_id, "partial", len(existing) if existing else 0)
        await log_operation(task_id, "generate", "用户取消生成")

    except asyncio.TimeoutError:
        logger.error(f"Generation timed out for {task_id} after {GENERATION_TIMEOUT}s")
        # Salvage partial results saved by save_callback during generation
        existing = await _testcase_repo.get_all_by_task(task_id)
        _generation_tasks[task_id]["status"] = "partial" if existing else "failed"
        _generation_tasks[task_id]["testcase_count"] = len(existing) if existing else 0
        timeout_min = GENERATION_TIMEOUT // 60
        if existing:
            _generation_tasks[task_id]["failure"] = {
                "reason": "timeout",
                "details": [f"生成超时（{timeout_min}分钟），已保存 {len(existing)} 条部分用例"],
                "suggestion": "可点击「全部补全」继续生成未覆盖的模块，或精简PRD后重试"
            }
        else:
            _generation_tasks[task_id]["failure"] = {
                "reason": "timeout",
                "details": [f"生成超时（{timeout_min}分钟），模块较多或API响应慢"],
                "suggestion": "建议：1) 精简PRD文档减少模块数量；2) 分模块逐个生成；3) 检查API网络连接后重试"
            }
        _generation_tasks[task_id]["completed_at"] = now_iso()
        await _project_repo.update_status(task_id, _generation_tasks[task_id]["status"], len(existing) if existing else 0)
        await log_operation(task_id, "generate", f"生成超时 ({GENERATION_TIMEOUT}s)，已保存{len(existing)}条部分结果")

    except AIGenerationError as e:
        logger.error(f"Generation failed for {task_id}: {e}")
        _generation_tasks[task_id]["status"] = "failed"
        _generation_tasks[task_id]["failure"] = {"reason": "ai_error", "details": [str(e)]}
        _generation_tasks[task_id]["completed_at"] = now_iso()
        await _project_repo.update_status(task_id, "failed", 0)
        await log_operation(task_id, "generate", f"AI生成失败：{e}")
    except Exception as e:
        logger.error(f"Unexpected error for {task_id}: {e}")
        _generation_tasks[task_id]["status"] = "failed"
        _generation_tasks[task_id]["failure"] = {"reason": "unexpected_error", "details": [str(e)]}
        _generation_tasks[task_id]["completed_at"] = now_iso()
        await _project_repo.update_status(task_id, "failed", 0)


@router.get("/{task_id}/status")
async def get_generation_status(task_id: str):
    """Query generation progress."""
    task = _generation_tasks.get(task_id)
    if not task:
        project = await _project_repo.get_by_task_id(task_id)
        if not project:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {
            "code": 200,
            "data": {
                "task_id": task_id,
                "status": project.get("status", "unknown"),
                "testcase_count": project.get("testcase_count", 0),
                "stats": {},
                "completed_at": project.get("updated_at", ""),
            },
            "message": "success",
        }

    response_data = {"task_id": task_id}
    for key in ["status", "progress", "testcase_count", "stats", "failure",
                "validation_issues", "started_at", "completed_at"]:
        if key in task:
            response_data[key] = task[key]

    return {"code": 200, "data": response_data, "message": "success"}


@router.post("/{task_id}/cancel")
async def cancel_generation(task_id: str):
    """Cancel an in-progress generation by signalling the cancellation event."""
    task = _generation_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.get("status") != "processing":
        raise HTTPException(status_code=400, detail="任务不在生成中，无法取消")

    cancel_event = task.get("_cancel_event")
    if cancel_event:
        cancel_event.set()
        logger.info(f"Cancellation signalled for {task_id}")
        await log_operation(task_id, "cancel", "用户取消生成")
    else:
        logger.warning(f"No cancel_event found for {task_id}, marking as failed")
        task["status"] = "failed"
        task["failure"] = {"reason": "cancelled", "details": ["无活跃生成进程，强制标记为失败"]}
        task["completed_at"] = now_iso()

    return {
        "code": 200,
        "data": {"task_id": task_id, "message": "取消信号已发送，正在中止..."},
        "message": "success",
    }


@router.get("/{task_id}/testcases")
async def get_generation_testcases(task_id: str, page: int = 1, page_size: int = 20,
                                    module: str = ""):
    """Get test cases generated for a task, optionally filtered by module."""
    result = await _testcase_repo.get_by_task(task_id, page, page_size, module=module)
    return {"code": 200, "data": {"task_id": task_id, **result}, "message": "success"}


@router.get("/{task_id}/testcases-all")
async def get_all_testcases(task_id: str):
    """Get ALL test cases for a task without pagination (for module-grouped display)."""
    all_cases = await _testcase_repo.get_all_by_task(task_id)
    return {"code": 200, "data": {"task_id": task_id, "items": all_cases, "total": len(all_cases)}, "message": "success"}


@router.post("/{task_id}/regenerate-modules")
async def regenerate_modules(task_id: str, background_tasks: BackgroundTasks):
    """Regenerate test cases for uncovered modules only."""
    project = await _project_repo.get_by_task_id(task_id)
    if not project:
        raise HTTPException(status_code=404, detail="任务不存在")

    prd_content = project.get("prd_content") or _local.read_text(task_id, "prd_content.md")
    if not prd_content:
        raise HTTPException(status_code=400, detail="PRD 内容为空")

    # Get current stats to find uncovered modules
    task = _generation_tasks.get(task_id, {})
    stats = task.get("stats", {})
    uncovered = stats.get("modules_uncovered", [])

    if not uncovered:
        # F7 fix: Use stored module data instead of re-extracting
        stored_modules = task.get("_all_modules", [])
        if stored_modules:
            all_module_names = [m.get("name", "") for m in stored_modules]
        else:
            # Fallback: compute from existing test cases + re-extract
            existing = await _testcase_repo.get_all_by_task(task_id)
            intermediate_rep = await generator._run_skill(
                "extract_modules", SKILL_EXTRACT_MODULES,
                f"以下是要分析的PRD文档：\n\n{prd_content}"
            )
            if isinstance(intermediate_rep, list):
                intermediate_rep = {"modules": intermediate_rep}
            if not isinstance(intermediate_rep, dict):
                intermediate_rep = {"modules": []}
            all_module_names = [m.get("name", "") for m in intermediate_rep.get("modules", [])]
        existing = await _testcase_repo.get_all_by_task(task_id)
        covered = set(c.get("module", "") for c in existing)
        uncovered = [m for m in all_module_names if m not in covered]

    if not uncovered:
        raise HTTPException(status_code=400, detail="所有模块已覆盖，无需重新生成")

    # Update state
    _generation_tasks[task_id] = {
        "status": "processing",
        "progress": {"current_skill": "generate_for_module", "skill_index": 2, "total_skills": 8, "skill_name": "补全未覆盖模块"},
        "started_at": now_iso(),
        "stats": stats,
    }

    background_tasks.add_task(_regenerate_modules, task_id, prd_content, uncovered)

    await log_operation(task_id, "regenerate", f"开始补全未覆盖模块：{uncovered}")

    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "status": "processing",
            "uncovered_modules": uncovered,
            "message": f"正在为 {len(uncovered)} 个未覆盖模块重新生成用例...",
        },
        "message": "success",
    }


async def _regenerate_modules(task_id: str, prd_content: str, module_names: list):
    """Background task: regenerate cases for specific modules with temp escalation (F7 fix)."""
    try:
        # F7 fix: Use stored module data instead of re-extracting
        task_state = _generation_tasks.get(task_id, {})
        stored_modules = task_state.get("_all_modules", [])

        if stored_modules:
            target_modules = [m for m in stored_modules if m.get("name") in module_names]
            logger.info(f"Using stored module data for {len(target_modules)} target modules")
        else:
            # Fallback: re-extract (should rarely happen)
            logger.warning("No stored module data found, re-extracting (fallback)")
            intermediate_rep = await generator._run_skill(
                "extract_modules", SKILL_EXTRACT_MODULES,
                f"以下是要分析的PRD文档：\n\n{prd_content}"
            )
            if isinstance(intermediate_rep, list):
                intermediate_rep = {"modules": intermediate_rep}
            if not isinstance(intermediate_rep, dict):
                intermediate_rep = {"modules": []}
            all_modules = intermediate_rep.get("modules", [])
            target_modules = [m for m in all_modules if m.get("name") in module_names]

        new_cases = []
        # Temperature escalation: start at 0.35 for regeneration
        regen_temps = [0.35, 0.5]
        for mod in target_modules:
            mod_name = mod.get("name", "")
            mod_input = generator._build_module_input(mod)
            retry_prompt = (
                SKILL_GENERATE_FOR_MODULE
                + "\n\n【重要提醒】该模块在上一次生成中被遗漏。即使信息不完整也必须至少生成一条P0正向用例，"
                + "缺失信息在notes中标注'需与产品确认'。"
            )
            generated = False
            for retry_temp in regen_temps:
                logger.info(
                    f"  Regenerating '{mod_name}' with temp={retry_temp}"
                )
                cases = await generator._run_skill(
                    "generate_for_module", retry_prompt,
                    mod_input, skill_max_tokens=generator.llm.max_tokens,
                    temperature=retry_temp
                )
                if isinstance(cases, list) and len(cases) > 0:
                    for c in cases:
                        c.setdefault("module", mod_name)
                    new_cases.extend(cases)
                    generated = True
                    logger.info(f"    Generated {len(cases)} cases for '{mod_name}'")
                    break
            if not generated:
                logger.warning(f"    Failed to generate cases for '{mod_name}' after all retries")

        # Remove old cases for these modules and save new ones
        existing_cases = await _testcase_repo.get_all_by_task(task_id)
        keep_cases = [c for c in existing_cases if c.get("module") not in module_names]
        all_cases = keep_cases + new_cases

        # Re-assign IDs
        for i, tc in enumerate(all_cases):
            if not tc.get("case_id"):
                tc["case_id"] = generate_case_id(i)

        proj_uuid = ""
        proj = await _project_repo.get_by_task_id(task_id)
        if proj:
            proj_uuid = proj.get("id", "")

        await _testcase_repo.save_batch(task_id, all_cases, proj_uuid)

        # Update stats — use stored module names or compute from cases
        if stored_modules:
            all_module_names = [m.get("name", "") for m in stored_modules]
        else:
            all_module_names = module_names  # fallback to requested modules
        covered = set(c.get("module", "") for c in all_cases)
        still_missing = [m for m in all_module_names if m not in covered]

        # Build module states for regenerate result
        module_states = {}
        for m_name in all_module_names:
            if m_name in covered:
                module_states[m_name] = {"status": "covered", "retries": 0}
            else:
                module_states[m_name] = {"status": "needs_prd_update", "retries": 2,
                                          "reason": "补全后仍未生成用例，可能PRD信息不足"}

        _generation_tasks[task_id] = {
            "status": "completed" if not still_missing else "partial",
            "testcase_count": len(all_cases),
            "stats": {
                "modules_found": len(all_module_names),
                "modules_covered": len(all_module_names) - len(still_missing),
                "modules_uncovered": still_missing,
                "total_cases": len(all_cases),
                "module_states": module_states,
            },
            "completed_at": now_iso(),
        }

        await _project_repo.update_status(task_id, _generation_tasks[task_id]["status"], len(all_cases))
        await log_operation(task_id, "regenerate",
                           f"补全完成：新增{len(new_cases)}条用例，"
                           f"覆盖{len(all_module_names) - len(still_missing)}/{len(all_module_names)}个模块")

    except Exception as e:
        logger.error(f"Regenerate failed for {task_id}: {e}")
        _generation_tasks[task_id]["status"] = "failed"
        _generation_tasks[task_id]["failure"] = {"reason": "regenerate_error", "details": [str(e)]}
        _generation_tasks[task_id]["completed_at"] = now_iso()
        await _project_repo.update_status(task_id, "failed", 0)


@router.post("/{task_id}/regenerate-module/{module_name:path}")
async def regenerate_single_module(task_id: str, module_name: str,
                                     background_tasks: BackgroundTasks):
    """Regenerate test cases for a single specific module."""
    project = await _project_repo.get_by_task_id(task_id)
    if not project:
        raise HTTPException(status_code=404, detail="任务不存在")

    prd_content = project.get("prd_content") or _local.read_text(task_id, "prd_content.md")
    if not prd_content:
        raise HTTPException(status_code=400, detail="PRD 内容为空")

    # Get stored module data
    task = _generation_tasks.get(task_id, {})
    stored_modules = task.get("_all_modules", [])
    target_mod = None
    for m in stored_modules:
        if m.get("name") == module_name:
            target_mod = m
            break

    if not target_mod:
        # Try extracting fresh
        try:
            intermediate_rep = await generator._run_skill(
                "extract_modules", SKILL_EXTRACT_MODULES,
                f"以下是要分析的PRD文档：\n\n{prd_content}"
            )
            if isinstance(intermediate_rep, list):
                intermediate_rep = {"modules": intermediate_rep}
            if not isinstance(intermediate_rep, dict):
                intermediate_rep = {"modules": []}
            for m in intermediate_rep.get("modules", []):
                mod_name = m if isinstance(m, str) else m.get("name", "")
                if mod_name == module_name:
                    target_mod = m if isinstance(m, dict) else {"name": m}
                    break
        except Exception:
            pass

    if not target_mod:
        raise HTTPException(status_code=404, detail=f"模块 '{module_name}' 不存在")

    # Set up processing state
    _generation_tasks[task_id] = {
        **_generation_tasks.get(task_id, {}),
        "status": "processing",
        "progress": {"current_skill": "generate_for_module", "skill_index": 3,
                      "total_skills": 8, "skill_name": f"重新生成: {module_name}"},
    }

    background_tasks.add_task(_regenerate_single_module, task_id, prd_content, target_mod)

    await log_operation(task_id, "regenerate", f"单模块重新生成: {module_name}")

    return {
        "code": 200,
        "data": {"task_id": task_id, "module": module_name, "message": f"正在重新生成模块: {module_name}"},
        "message": "success",
    }


async def _regenerate_single_module(task_id: str, prd_content: str, mod: dict):
    """Background task: regenerate cases for a single module."""
    try:
        mod_name = mod.get("name", "") if isinstance(mod, dict) else str(mod)
        if isinstance(mod, str):
            mod = {"name": mod}
        mod_input = generator._build_module_input(mod)
        new_cases = []
        for retry_temp in [0.35, 0.5]:
            cases = await generator._run_skill(
                "generate_for_module", SKILL_GENERATE_FOR_MODULE,
                mod_input, skill_max_tokens=generator.llm.max_tokens,
                temperature=retry_temp
            )
            if isinstance(cases, list) and len(cases) > 0:
                for c in cases:
                    c.setdefault("module", mod_name)
                new_cases = cases
                break

        # Replace old cases for this module, keep others
        existing_cases = await _testcase_repo.get_all_by_task(task_id)
        keep_cases = [c for c in existing_cases if c.get("module") != mod_name]
        all_cases = keep_cases + new_cases

        for i, tc in enumerate(all_cases):
            if not tc.get("case_id"):
                tc["case_id"] = generate_case_id(i)

        proj_uuid = ""
        proj = await _project_repo.get_by_task_id(task_id)
        if proj:
            proj_uuid = proj.get("id", "")
        await _testcase_repo.save_batch(task_id, all_cases, proj_uuid)

        covered = set(c.get("module", "") for c in all_cases)
        all_names = list(set(
            [c.get("module", "") for c in all_cases] +
            [c.get("module", "") for c in existing_cases if c.get("module")]
        ))
        still_missing = [m for m in all_names if m not in covered]

        _generation_tasks[task_id] = {
            "status": "completed" if not still_missing else "partial",
            "testcase_count": len(all_cases),
            "stats": {"modules_found": len(all_names), "modules_covered": len(all_names) - len(still_missing),
                       "modules_uncovered": still_missing, "total_cases": len(all_cases)},
            "completed_at": now_iso(),
        }
        await _project_repo.update_status(task_id, _generation_tasks[task_id]["status"], len(all_cases))
        await log_operation(task_id, "regenerate",
                           f"单模块 {mod_name} 重新生成完成：{len(new_cases)}条")

    except Exception as e:
        logger.error(f"Single module regenerate failed for {task_id}: {e}")
        _generation_tasks[task_id]["status"] = "failed"
        _generation_tasks[task_id]["failure"] = {"reason": "regenerate_error", "details": [str(e)]}
        _generation_tasks[task_id]["completed_at"] = now_iso()
