# AI Bot 配置与 Skills 技能定义

## 设计原则

**核心原则：所有测试用例必须从 PRD 原文推导，严禁使用固化模板或臆想功能。** 
每个 Skill 通过精心设计的 Prompt 引导 LLM 分析实际 PRD 内容，而非套用预设模式。

## Bot 配置文件 (`ai_engine/bot_config.yaml`)

```yaml
bots:
  testcase_generator:
    provider: deepseek
    model: deepseek-chat
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1
    temperature: 0.15
    max_tokens: 4096
    request_timeout: 120
```

## Skill 体系总览

Skills 是生成流水线中的子任务，每个 Skill 通过独立的 system prompt + user prompt 调用 LLM，之间通过结构化 JSON 传递数据。

```
PRD全文
  │
  ├─ Skill 1: extract_modules ──→ 功能模块列表 + 中间表示 [{name, summary, relevant_text,
  │                                      ui_elements, fields, actions, rules_explicit, states, missing_info}]
  │   ├─ 检查：有可生成的模块？→ 否则终止并返回失败
  │
  ├─ Skill 2: generate_for_module (每个模块独立调用) ──→ 模块用例列表
  │
  ├─ Skill 3: extract_constraints ──→ 字段约束列表 [{field, type, constraint, module}]
  │
  ├─ Skill 4: boundary_completion ──→ 边界/异常用例列表
  │
  ├─ Skill 5: state_transition ──→ 状态转换用例列表
  │
  ├─ Skill 6: refine_steps ──→ 步骤具体化后的全部用例
  │
  ├─ Skill 7: deduplicate ──→ 去重后的用例列表
  │
  └─ Skill 8: post_validation (Sanity Checker) ──→ 校验通过/失败
       ├─ 失败 → 打回 Skill 6 重试（最多 2 次）
       └─ 仍失败 → 终止，返回校验错误详情
```

---

## Skill 1: extract_modules（提取功能模块 + 结构化中间表示）

**触发时机**：生成开始，拿到 PRD 全文后第一步

**输入**：PRD 完整 Markdown 文本

**输出**：`[{name, summary, relevant_text, ui_elements, fields, actions, rules_explicit, states, missing_info}]`

**System Prompt**：
```
你是一个需求分析专家。你的任务是从给定的 PRD 文档中提取所有独立的功能模块，并构建结构化的中间表示。

规则：
1. 仔细阅读 PRD 全文，识别出每个独立的功能模块
2. 只基于 PRD 实际内容提取，不要添加 PRD 中未提及的模块
3. 每个模块需提取以下完整信息：
   - name: 模块简短名称
   - summary: 模块功能一句话概述
   - relevant_text: 从 PRD 中摘录的该模块相关的原始段落（完整摘录，不截断）
   - ui_elements: PRD 中明确提到的 UI 元素列表（按钮、输入框、下拉框、链接等具体名称）
   - fields: 输入字段列表，每项含 name/type/constraints（仅提取 PRD 明确的字段）
   - actions: 用户可执行的操作列表（点击xxx、输入xxx、选择xxx）
   - rules_explicit: PRD 明确声明的业务规则（校验规则、流程规则、权限规则）
   - states: 该模块涉及的状态列表（如有状态流转），无则填 []
   - missing_info: PRD 中该模块缺失的关键信息（如缺少字段约束、缺少异常处理说明），无则填 []

4. 模块粒度适中：不能太粗（整个系统只有一个模块）也不能太细（每个输入框一个模块）
5. 重要：ui_elements 为空时，意味着该模块无法生成可执行的UI操作步骤，后续将被跳过
6. 输出纯 JSON 数组，不要任何额外解释
```

**输出示例**：
```json
[{
  "name": "用户注册",
  "summary": "新用户通过手机号和密码完成账号注册",
  "relevant_text": "用户输入手机号（11位中国大陆手机号，以1开头）和密码（6-20位，必须包含字母和数字）。点击注册按钮...",
  "ui_elements": ["手机号输入框", "密码输入框", "注册按钮", "验证码输入框", "确认按钮"],
  "fields": [
    {"name": "手机号", "type": "string", "length": 11, "format": "中国大陆手机号，以1开头"},
    {"name": "密码", "type": "string", "length": "6-20", "format": "必须包含字母和数字"}
  ],
  "actions": ["输入手机号", "输入密码", "点击注册", "输入验证码", "点击确认"],
  "rules_explicit": [
    "手机号格式错误时提示",
    "手机号已注册时提示'该手机号已注册'",
    "密码不符合格式时提示",
    "验证码60秒后可重发",
    "验证码错误时提示，剩余尝试次数3次",
    "网络异常时提示'网络开小差，请稍后重试'"
  ],
  "states": ["输入手机号", "输入密码", "等待验证码", "输入验证码", "注册完成"],
  "missing_info": ["验证码有效期未明确说明", "注册成功后跳转页面未指定URL"]
}]
```

---

## Skill 2: generate_for_module（按模块生成用例）

**触发时机**：每个模块独立调用

**输入**：`{module_name, module_summary, module_relevant_text}`

**输出**：`[{module, title, precondition, steps, priority, type, notes}]`

**System Prompt**：
```
你是一名资深测试工程师。根据以下单个功能模块的 PRD 描述，生成该模块的全面测试用例。

规则：
1. 严格依据提供的模块描述，绝不添加不存在或臆测的功能
2. 每条用例必须包含完整字段：
   - module: 模块名
   - title: 简明扼要描述测试场景
   - precondition: 测试执行前必须满足的条件（无则填"无"）
   - steps: [{action: 具体操作步骤, expected: 可量化观察的预期结果}]
   - priority: P0(核心流程)/P1(重要功能)/P2(一般场景)/P3(边缘场景)
   - type: 功能测试/异常测试/边界测试/性能测试/安全测试/兼容性测试
   - notes: 补充说明，PRD信息不足时标注"需与产品确认：xxx"

3. 强制覆盖类型：
   - 【正向】至少一条完整的成功操作路径
   - 【异常】网络超时、服务端500、权限不足、重复操作等
   - 【边界】字段长度极值、空值、特殊字符、空格、SQL注入字符等
   - 【状态转换】若涉及状态流转，覆盖所有合法/非法转换

4. 步骤撰写要求：
   - action: 使用具体UI元素名称（如"手机号输入框"而非"输入框"），包含具体测试数据（如"输入'13912345678'"而非"输入正确手机号"）
   - expected: 描述可观察、可量化的结果（如"输入框下方出现红色提示'手机号格式错误'"而非"显示错误提示"）

5. 优先级判定标准：
   - P0: 核心业务主流程，阻断后功能不可用
   - P1: 重要异常处理、核心边界条件
   - P2: 一般边界条件、次要交互
   - P3: 极端边界、罕见场景

6. 输出纯 JSON 数组，不要任何额外解释
```

---

## Skill 3: extract_constraints（提取字段约束）

**触发时机**：所有模块用例生成完成后

**输入**：PRD 完整 Markdown 文本

**输出**：`[{field, type, constraints, module}]`

**System Prompt**：
```
你是一个需求分析专家。从给定的 PRD 文档中提取所有输入字段及其约束条件。

规则：
1. 识别 PRD 中所有需要用户输入的字段（文本框、下拉框、日期选择器、数字输入等）
2. 对每个字段提取其约束：
   - field: 字段名称（PRD中使用的名称）
   - type: 数据类型（string/number/date/enum/phone/email/id_card等）
   - constraints: 详细约束描述（长度范围、格式要求、必填/选填、取值范围、特殊规则）
   - module: 所属模块

3. 严格基于 PRD 原文，不要推测约束。如果 PRD 未明确说明的约束，在 constraints 中标注"PRD未明确"
4. 输出纯 JSON 数组，不要任何额外解释
```

---

## Skill 4: boundary_completion（边界用例补充）

**触发时机**：拿到字段约束后

**输入**：`{constraints: [{field, type, constraints, module}], existing_cases_count: N}`

**输出**：`[{module, title, precondition, steps, priority, type, notes}]`

**System Prompt**：
```
你是一名测试工程师，专注于边界测试和异常测试。根据提供的字段约束列表，为每个有明确约束的字段生成边界用例。

规则：
1. 针对每个字段的每个约束，生成对应的边界用例：
   - 有长度范围 → 测试 min-1, min, max, max+1
   - 有格式要求 → 测试合法格式 + 多种非法格式
   - 必填 → 测试空值/不填
   - 有取值范围 → 测试边界值和越界值
   - 特殊规则 → 测试违反规则的情况

2. 如果约束标注为"PRD未明确"，不生成猜测性边界用例，在输出中注明跳过原因（如"缺少字段xx的约束信息，无法生成边界用例"）
3. 避免与已有用例重复（检查 existing_cases_count 了解已生成数量，关注未覆盖的边界）
4. 步骤必须具体可执行
5. 输出纯 JSON 数组，不要任何额外解释
```

---

## Skill 5: state_transition（状态转换用例）

**触发时机**：边界补充完成后

**输入**：`{prd_text, existing_case_titles: [...]}`

**输出**：`[{module, title, precondition, steps, priority, type, notes}]`

**System Prompt**：
```
你是一名测试工程师，专注于状态转换测试。分析 PRD 中涉及状态流转的业务对象（如订单、申请、任务等），生成状态转换测试用例。

规则：
1. 从 PRD 中识别存在状态变化的业务对象（如：待支付→已支付→已发货→已完成）
2. 画出该对象的状态机：
   - 覆盖所有合法的状态转换路径（正向流程）
   - 覆盖非法的状态转换尝试（如从未支付直接跳到已发货）
3. 每条用例测试一个具体的状态转换
4. 如果 PRD 中没有涉及状态转换的业务，返回空数组 []
5. 输出纯 JSON 数组，不要任何额外解释
```

---

## Skill 6: refine_steps（步骤具体化）

**触发时机**：所有用例生成完成后，去重之前

**输入**：所有已生成用例的 JSON 数组

**输出**：步骤被细化后的完整用例数组

**System Prompt**：
```
你是一名资深测试执行专家。审查并细化以下测试用例的步骤描述。

规则：
1. 检查每条用例的每个步骤，确保：
   - action 包含具体的 UI 元素名称和具体测试数据
   - expected 包含可量化观察的结果描述
2. 模糊描述的修正示例：
   - "输入正确信息" → "在用户名输入框输入'admin'，在密码输入框输入'Test@123'"
   - "显示成功提示" → "页面顶部出现绿色Toast提示'操作成功'，3秒后自动消失"
   - "跳转页面" → "浏览器URL变为 /dashboard，页面标题显示'工作台'"
3. 不要改变用例的数量、顺序和核心测试意图
4. 如果某步骤已经足够具体，保持原样
5. 输出完整的用例 JSON 数组（保持原结构，仅细化 steps）
```

---

## Skill 7: deduplicate（语义去重）

**触发时机**：步骤细化完成后，最终入库前

**输入**：所有用例的 JSON 数组

**输出**：去重后的用例数组

**System Prompt**：
```
你是一名测试用例审核专家。对以下测试用例列表进行语义去重。

规则：
1. 比较每两条用例的测试意图（而非字面表述）
2. 判定为重复的条件（同时满足）：
   - 测试同一个功能点
   - 前置条件相同
   - 测试步骤和预期结果覆盖相同的验证目标
3. 当两条用例重复时，保留步骤更完整、描述更具体的那条
4. 优先级 P0/P1 的用例去重要更谨慎，宁可保留疑似重复也不误删核心用例
5. 输出去重后的完整用例 JSON 数组
```

---

## Skill 8: post_validation（Sanity Checker — 输出后校验）

**触发时机**：去重完成后，最终入库前

**输入**：`{testcases: [...], intermediate_rep: {...}, prd_text: "..."}`

**输出**：`{passed: bool, issues: [{case_id, type, detail, suggestion}], pass_count: int, fail_count: int}`

**说明**：此 Skill **不调用 LLM**，而是后端代码实现的规则校验器。校验不通过时，将 issues 反馈给 Skill 6（refine_steps）进行针对性修正，最多重试 2 次。2 次后仍不通过则终止生成，返回校验错误详情。

**校验规则**：

| 校验项 | 检测逻辑 | 不通过动作 |
|--------|----------|-----------|
| 模糊词检测 | 扫描 expected 字段，匹配正则 `/(正常\|正确\|无误\|成功\|表现正常\|符合预期)(?!.*(提示\|跳转\|URL\|页面\|弹窗\|Toast\|按钮\|输入框\|颜色\|文字\|图标))/` —— 即出现模糊词但无具体界面描述 | 返回具体模糊位置，要求补充可观察结果 |
| 元素来源检测 | 提取 steps 中所有 UI 元素名称，与 intermediate_rep 中所有模块的 `ui_elements` 列表比对 | 未匹配的元素标记为 "PRD未提及的UI元素"，要求修正或标注缺失 |
| 数值合理性 | 边界用例中的测试数值与 `fields[].constraints` 比对（如 PRD 说 6-20 位，测值必须在此范围边界上） | 不在合理范围的数值打回，要求使用 PRD 约束推导的边界值 |
| 步骤可达性 | 检查每条步骤的 action 是否有对应前置状态（如"点击确认"前必须有"已进入该页面"的前置） | 无法从前序步骤到达的步骤打回 |

**实现代码**（详见 [开发规范.md](开发规范.md)）：

```python
# backend/app/services/skill_executor.py

async def post_validation(testcases: list, intermediate_rep: dict, prd_text: str) -> dict:
    """Skill 8: 规则校验器，不调用 LLM"""
    issues = []
    all_ui_elements = set()
    for mod in intermediate_rep.get("modules", []):
        all_ui_elements.update(mod.get("ui_elements", []))
    
    for tc in testcases:
        for step_idx, step in enumerate(tc.get("steps", [])):
            expected = step.get("expected", "")
            action = step.get("action", "")
            
            # 1. 模糊词检测
            vague_match = VAGUE_PATTERN.search(expected)
            if vague_match:
                issues.append({
                    "case_id": tc["case_id"],
                    "step_index": step_idx,
                    "type": "vague_expected",
                    "detail": f"预期结果包含模糊词'{vague_match.group(0)}'，需补充具体界面变化描述",
                    "suggestion": "描述具体的UI变化（如提示文字、页面跳转URL、按钮状态变化）"
                })
            
            # 2. 元素来源检测
            mentioned_elements = extract_ui_elements(action)
            unknown = [e for e in mentioned_elements if not any(e in ue for ue in all_ui_elements)]
            if unknown:
                issues.append({
                    "case_id": tc["case_id"],
                    "step_index": step_idx,
                    "type": "unknown_element",
                    "detail": f"步骤中提到未在PRD中出现的UI元素：{unknown}",
                    "suggestion": "修正为PRD实际提及的UI元素名称，或标注'需与产品确认'"
                })
            
            # 3. 数值合理性 (针对边界用例)
            if tc.get("type") == "边界测试":
                boundary_issues = check_boundary_values(tc, intermediate_rep)
                issues.extend(boundary_issues)
            
            # 4. 步骤可达性
            if step_idx > 0:
                prev_step = tc["steps"][step_idx - 1]
                if not is_reachable(prev_step["expected"], action):
                    issues.append({
                        "case_id": tc["case_id"],
                        "step_index": step_idx,
                        "type": "unreachable_step",
                        "detail": f"步骤'{action}'无法从前一步的预期结果到达",
                        "suggestion": "检查前置条件与步骤顺序是否合理"
                    })
    
    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "pass_count": len(testcases) - len(set(i["case_id"] for i in issues)),
        "fail_count": len(set(i["case_id"] for i in issues))
    }
```

```python
async def generate_testcases(prd_text: str, bot_config: dict) -> dict:
    """
    返回 {"task_id": str, "testcases": list, "stats": dict, "warnings": list}
    每个 Skill 都是一次独立的 LLM API 调用，通过 prompt 工程实现
    """
    llm = LLMClient(bot_config)
    skipped_modules = []
    
    # Step 1: 提取模块 + 结构化中间表示
    intermediate_rep = await llm.chat(
        system=SKILL_PROMPTS["extract_modules"],
        user=f"以下是要分析的PRD文档：\n\n{prd_text}"
    )
    
    # Step 1.5: 需求残缺检查
    valid_modules = []
    for mod in intermediate_rep["modules"]:
        if not mod.get("ui_elements") and not mod.get("actions"):
            skipped_modules.append({
                "module": mod["name"],
                "reason": f"模块'{mod['name']}'无明确UI元素或用户操作，无法生成可执行用例"
            })
        else:
            valid_modules.append(mod)
    
    if not valid_modules:
        return {
            "status": "failed",
            "testcases": [],
            "failure": {
                "reason": "no_actionable_modules",
                "details": [m["reason"] for m in skipped_modules],
                "suggestion": "请补充PRD中的UI交互细节后重新生成"
            }
        }
    
    # Step 2: 逐模块生成用例（可并行）
    all_cases = []
    for mod in valid_modules:
        cases = await llm.chat(
            system=SKILL_PROMPTS["generate_for_module"],
            user=f"模块名：{mod['name']}\n概述：{mod['summary']}\n相关内容：\n{mod['relevant_text']}"
        )
        all_cases.extend(cases)
    
    # Step 3: 提取字段约束
    constraints = await llm.chat(
        system=SKILL_PROMPTS["extract_constraints"],
        user=f"以下是要分析的PRD文档：\n\n{prd_text}"
    )
    
    # Which constraints have explicit values?
    explicit_constraints = [c for c in constraints if c.get("constraints") != "PRD未明确"]
    
    # Step 4: 边界补充（仅针对有明确约束的字段）
    if explicit_constraints:
        boundary_cases = await llm.chat(
            system=SKILL_PROMPTS["boundary_completion"],
            user=f"字段约束（仅含明确约束）：{json.dumps(explicit_constraints, ensure_ascii=False)}\n已有用例数：{len(all_cases)}"
        )
        all_cases.extend(boundary_cases)
    
    # Step 5: 状态转换补充
    state_cases = await llm.chat(
        system=SKILL_PROMPTS["state_transition"],
        user=f"PRD文档：\n{prd_text}\n已有用例标题：{[c['title'] for c in all_cases]}"
    )
    all_cases.extend(state_cases)
    
    # Step 6 + 8 loop: 细化 + 校验（最多重试 2 次）
    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES + 1):
        # Step 6: 步骤细化
        refined = await llm.chat(
            system=SKILL_PROMPTS["refine_steps"],
            user=f"以下用例需要步骤细化：\n{json.dumps(all_cases, ensure_ascii=False)}"
        )
        
        # Step 7: 去重
        deduped = await llm.chat(
            system=SKILL_PROMPTS["deduplicate"],
            user=f"以下用例需要去重审核：\n{json.dumps(refined, ensure_ascii=False)}"
        )
        
        # Step 8: 后处理校验（Sanity Checker，不调用 LLM）
        validation = await post_validation(deduped, intermediate_rep, prd_text)
        
        if validation["passed"]:
            break
        elif attempt < MAX_RETRIES:
            # 打回 Skill 6 重试，注入校验失败信息
            SKILL_PROMPTS["refine_steps"] += f"\n\n上一次校验发现以下问题，请针对性修正：\n{json.dumps(validation['issues'], ensure_ascii=False)}"
            all_cases = deduped  # 以去重后的为基础重试
        else:
            # 重试耗尽，返回部分结果 + 失败详情
            return {
                "status": "partial",
                "testcases": deduped,
                "validation_issues": validation["issues"],
                "warning": f"校验未通过（已重试{MAX_RETRIES}次），以下用例可能存在质量问题"
            }
    
    return {
        "status": "completed",
        "testcases": deduped if "deduped" in dir() else validation.get("testcases", []),
        "stats": {
            "modules_found": len(intermediate_rep["modules"]),
            "modules_skipped": len(skipped_modules),
            "skipped_details": skipped_modules,
            "total_cases": len(deduped)
        }
    }
```

## 关键防臆想机制

| 机制 | 说明 |
|------|------|
| PRD 原文注入 | 每个 Skill 的 user prompt 都包含 PRD 原文或摘录段落，LLM 始终基于原文分析 |
| 结构化中间表示 | Skill 1 提取 ui_elements/fields/actions/rules/states/missing_info，后续 Skills 基于此结构生成，避免脱离 PRD |
| 需求残缺终止 | Skill 1 后检查：无可用模块则立即终止，返回缺失详情，不输出任何用例 |
| "PRD未明确"标注 | 当约束或逻辑不明确时，Skill 被要求标注而非猜测；无明确约束的字段不生成猜测性边界用例 |
| 多轮交叉验证 | extract_modules → generate_for_module → extract_constraints 三层独立分析同一 PRD，互相验证 |
| 语义去重 | Skill 7 去重审查用例质量，过滤跑偏的生成结果 |
| Sanity Checker | Skill 8 规则校验器：模糊词/元素来源/数值合理性/步骤可达性 4 项检查，不通过打回修正（最多 2 次） |
| 低温度参数 | temperature=0.15 减少 LLM 自由发挥空间，保证格式与逻辑一致性 |
