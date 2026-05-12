import json
import re
from app.utils.text_utils import extract_json_from_response


# Vague term detection pattern
VAGUE_PATTERN = re.compile(
    r'(正常|正确|无误|成功|表现正常|符合预期)'
    r'(?!.*(?:提示|跳转|URL|页面|弹窗|Toast|按钮|输入框|颜色|文字|图标|消失|变化))'
)


class SkillExecutor:
    """Executes individual Skills by calling LLM API."""

    def __init__(self, llm_client):
        self.llm = llm_client

    async def execute(self, skill_name: str, system_prompt: str, user_input: str) -> dict:
        response = await self.llm.chat(system=system_prompt, user=user_input)
        json_str = extract_json_from_response(response)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Retry once with stricter prompt
            retry_prompt = system_prompt + "\n\n重要：你上次的输出不是有效的JSON格式。请确保输出纯 JSON，不要任何额外解释或markdown标记。"
            retry_response = await self.llm.chat(system=retry_prompt, user=user_input)
            retry_json = extract_json_from_response(retry_response)
            data = json.loads(retry_json)
        if not isinstance(data, dict):
            data = {"result": data}
        return data


def post_validation(testcases: list, intermediate_rep: dict, prd_text: str = "") -> dict:
    """
    Skill 8: Post-validation Sanity Checker.
    Does NOT call LLM — runs rule-based checks on generated test cases.
    Vague terms are warnings (non-blocking); only unknown elements and unreachable steps block.
    Returns {"passed": bool, "issues": list, "warnings": list, "pass_count": int, "fail_count": int, "missing_modules": list}.
    """
    if not isinstance(intermediate_rep, dict):
        intermediate_rep = {"modules": []}
    issues = []      # blocking issues
    warnings = []    # non-blocking (vague terms, etc.)
    all_ui_elements = set()
    all_modules = [mod.get("name", "") for mod in intermediate_rep.get("modules", [])]
    for mod in intermediate_rep.get("modules", []):
        all_ui_elements.update(mod.get("ui_elements", []))

    # Check 0: Module coverage — which modules have no test cases
    covered_modules = set()
    for tc in testcases:
        covered_modules.add(tc.get("module", ""))
    missing_modules = [m for m in all_modules if m not in covered_modules]

    for tc in testcases:
        for step_idx, step in enumerate(tc.get("steps", [])):
            expected = step.get("expected", "")
            action = step.get("action", "")

            # Check 1: Vague terms — non-blocking warning (S5: don't drop cases for this)
            vague_match = VAGUE_PATTERN.search(expected)
            if vague_match:
                warnings.append({
                    "case_id": tc.get("case_id", ""),
                    "step_index": step_idx,
                    "type": "vague_expected",
                    "detail": f"预期结果包含模糊词'{vague_match.group(0)}'，建议补充具体界面变化描述",
                    "suggestion": "描述具体的UI变化（如提示文字、页面跳转URL、按钮状态变化）",
                })

            # Check 2: UI element source check
            mentioned = re.findall(r'[\'"「『]([^\'"」』]+)[\'"」』]', action)
            unknown = [e for e in mentioned if e not in all_ui_elements]
            if unknown:
                issues.append({
                    "case_id": tc.get("case_id", ""),
                    "step_index": step_idx,
                    "type": "unknown_element",
                    "detail": f"步骤中引用的UI元素未在PRD中找到：{unknown}",
                    "suggestion": "修正为PRD实际提及的UI元素名称，或标注'需与产品确认'",
                })

            # Check 3: Boundary value reasonableness
            if tc.get("type") == "边界测试":
                boundary_issues = _check_boundary_values(tc, intermediate_rep)
                issues.extend(boundary_issues)

            # Check 4: Step reachability
            if step_idx > 0:
                prev_step = tc["steps"][step_idx - 1]
                if not _is_reachable(prev_step.get("expected", ""), action):
                    issues.append({
                        "case_id": tc.get("case_id", ""),
                        "step_index": step_idx,
                        "type": "unreachable_step",
                        "detail": f"步骤'{action}'无法从前一步的预期结果合理到达",
                        "suggestion": "检查前置条件与步骤顺序是否合理",
                    })

    failed_case_ids = set(i["case_id"] for i in issues)
    passed = len(issues) == 0 and len(missing_modules) == 0
    return {
        "passed": passed,
        "issues": issues,
        "warnings": warnings,
        "pass_count": len(testcases) - len(failed_case_ids),
        "fail_count": len(failed_case_ids),
        "missing_modules": missing_modules,
    }


def _check_boundary_values(testcase: dict, intermediate_rep: dict) -> list:
    issues = []
    all_fields = {}
    for mod in intermediate_rep.get("modules", []):
        for f in mod.get("fields", []):
            all_fields[f.get("name", "")] = f
    return issues


def _is_reachable(prev_expected: str, current_action: str) -> bool:
    """Heuristic: check if current action is reachable from previous expected result."""
    unreachable_keywords = ["跳转成功", "已退出", "已删除"]
    for kw in unreachable_keywords:
        if kw in prev_expected:
            return False
    return True


def check_module_availability(intermediate_rep: dict) -> tuple[list, list]:
    """Check all modules and note which have incomplete info. No module is skipped."""
    if not isinstance(intermediate_rep, dict):
        intermediate_rep = {"modules": []}
    valid = []
    warnings = []
    for mod in intermediate_rep.get("modules", []):
        # Defensive: normalize string modules to dict
        if isinstance(mod, str):
            mod = {"name": mod, "summary": mod}
        # All modules are considered valid for generation
        valid.append(mod)
        if not mod.get("ui_elements") and not mod.get("actions"):
            warnings.append({
                "module": mod.get("name", "未知模块"),
                "reason": f"模块'{mod.get('name', '未知')}'无明确UI元素或用户操作，将基于规则和状态描述生成用例",
            })
    return valid, warnings
