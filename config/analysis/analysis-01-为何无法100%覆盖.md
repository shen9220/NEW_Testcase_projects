# Analysis 01：为何补全后仍无法 100% 覆盖测试用例

## 分析方法

逐行追踪 `ai_generator.py` (Skill 1-8) → `generation.py` (regenerate) → `skill_executor.py` (validation) 完整链路，在每个节点检查可能丢失模块或用例的位置。

---

## 10 个失败点（Failure Points）

### F1：Skill 1 — 模块提取不完整，且无校验

**位置**：[ai_generator.py:106-113](backend/app/services/ai_generator.py)

```python
intermediate_rep = await self._run_skill(
    "extract_modules", SKILL_EXTRACT_MODULES,
    f"以下是要分析的PRD文档：\n\n{prd_text}"
)
```

**问题**：
- 单次 LLM 调用提取所有模块，依赖 LLM 自身判断力
- PRD 中隐含需求（如"支持导出"散落在非功能描述中）、分散描述（同一模块在多个段落提及但无独立标题）容易被遗漏
- 提取结果**没有与 PRD 标题层级比对**——如果 PRD 有 10 个 H2 标题但 LLM 只提取了 8 个模块，系统完全不知道丢失了 2 个
- 提示词中"只基于 PRD 实际内容提取"过于保守，LLM 可能跳过隐含模块

**后果**：未提取的模块永远不会进入模块列表，后续所有流程都不会为其生成用例。这是**最根本的遗漏来源**。

---

### F2：Skill 2 — 单模块生成失败时无差异化重试

**位置**：[ai_generator.py:138-151](backend/app/services/ai_generator.py)

```python
cases = await self._run_skill(
    "generate_for_module", SKILL_GENERATE_FOR_MODULE,
    mod_input, skill_max_tokens=self.llm.max_tokens
)
if isinstance(cases, list):
    ...
else:
    logger.warning(f"    Failed to generate cases for '{mod['name']}'")
```

**问题**：
- 当 LLM 返回非 list（如 dict、纯文本、空字符串），模块获得 0 条用例
- 只记录 warning，**不立即重试**
- 依赖下游 Skill 2b 补漏

---

### F3：Skill 2b — 重试使用相同参数，确定性失败

**位置**：[ai_generator.py:153-178](backend/app/services/ai_generator.py)

```python
retry_prompt = (
    SKILL_GENERATE_FOR_MODULE
    + "\n\n【重要提醒】上一轮你未给该模块生成任何测试用例。"
    + "请务必至少生成一条P0正向用例，即使信息不完整也必须在notes中标注。"
)
cases = await self._run_skill(
    "generate_for_module", retry_prompt,
    mod_input, skill_max_tokens=self.llm.max_tokens   # ← 相同 temperature (0.15)
)
```

**问题**：
- **temperature 未提高**（仍为 0.15），LLM 在低温下高度确定性 — 相同输入大概率产出相同结果
- Prompt 变化极小（仅追加一行提醒），不足以改变 LLM 行为
- **仅重试一次**——如果第二次也失败，该模块永久无法覆盖
- 未使用"全局上下文增强"（如附加上下文信息），单纯重复请求

**后果**：点击"补全未覆盖模块"按钮时，`_regenerate_modules` 同样使用默认 temperature，陷入同样的确定性失败循环。

---

### F4：Skill 6（refine_steps）— 可能静默丢弃用例

**位置**：[ai_generator.py:219-228](backend/app/services/ai_generator.py)

```python
refined = await self._run_skill("refine_steps", refine_prompt, ...)
if not isinstance(refined, list):
    refined = all_cases   # 保护：非 list 时回退
```

**问题**：
- 当 `refined` 是合法 list 但**缺少部分用例**时（LLM 在 refine 时意外删除了条目），系统不会检测
- 提示词虽声明"不要改变用例的数量"，但 LLM 不保证遵守
- 没有**用例计数校验**：`len(refined)` 应等于 `len(all_cases)`

---

### F5：Skill 7（deduplicate）— 可能误删临界用例

**位置**：[ai_generator.py:231-236](backend/app/services/ai_generator.py)

```python
deduped = await self._run_skill("deduplicate", SKILL_DEDUPLICATE, ...)
if not isinstance(deduped, list):
    deduped = refined
```

**问题**：
- 去重时 LLM 可能判断过于激进，将"相似但测试不同场景"的用例误判为重复并删除
- 同样缺少**丢弃量合理性校验**——如果去重删除了 40% 的用例，明显不正常但无告警

---

### F6：Skill 8（post_validation）— 发现遗漏但不补救

**位置**：[ai_generator.py:238-246](backend/app/services/ai_generator.py)

```python
validation = post_validation(deduped, intermediate_rep, prd_text)
if validation["passed"]:
    break
elif attempt < MAX_RETRIES:
    ...
    all_cases = deduped   # ← 重新 refine+dedup，但不重新生成缺失模块的用例
```

**问题**：
- `post_validation` 已返回 `missing_modules` 列表（我们的上一个修复加了此字段）
- 但 refine→dedup→validate 循环**只处理 validation issues（模糊词、未知元素等），不处理模块缺失**
- 缺失模块的用例从未被重新生成，循环只对已有用例做 polish

---

### F7：regenerate_modules — 重复同样的提取过程

**位置**：[generation.py:197-209](backend/app/routers/generation.py)

```python
# 补全时重新提取模块
intermediate_rep = await generator._run_skill(
    "extract_modules", SKILL_EXTRACT_MODULES,
    f"以下是要分析的PRD文档：\n\n{prd_content}"
)
```

**问题**：
- 补全时**重新运行 extract_modules**，可能得到和首次完全不同的模块列表
- 如果新列表中的模块名称与原始 `uncovered` 列表不匹配，`target_modules` 可能为空
- 如果新提取遗漏了某些模块，这些模块永远不会被覆盖
- **应该使用首次提取的模块数据**（已保存在 `_generation_tasks[task_id]`），而不是重新提取

**位置**：[generation.py:212-221](backend/app/routers/generation.py)

```python
cases = await generator._run_skill(
    "generate_for_module", retry_prompt,
    mod_input, skill_max_tokens=generator.llm.max_tokens   # ← 仍为低温
)
```

**问题**：
- `_regenerate_modules` 调用 `generator._run_skill`，使用的是 generator 的默认参数（temperature=0.15）
- 和 F3 同样的问题：低温 + 相同输入 = 相同失败
- **没有临时提高 temperature 或使用变化过的 prompt**

---

### F8：无模块级状态追踪和失败标记

**问题**：
- 没有持久化记录每个模块的生成状态（`covered` / `failed` / `partial`）
- 用户无法知道哪些模块"真正缺少 PRD 信息" vs "暂时生成失败"
- 连续 3 次失败的模块无限重试，没有"标记为需求缺失并停止"的机制
- 这些"僵尸模块"在补全列表中反复出现，用户点击补全→失败→再次出现

---

### F9：上下文隔离 — 跨模块依赖信息缺失

**位置**：[ai_generator.py:279-300](backend/app/services/ai_generator.py) `_build_module_input`

```python
parts = [
    f"模块名：{mod.get('name', '')}",
    f"概述：{mod.get('summary', '')}",
    ...
    f"PRD原文：{mod.get('relevant_text', '')}",  # ← 仅该模块的片段
]
```

**问题**：
- 每个模块生成时只看到自己的 PRD 片段，看不到**全局角色定义、公共规则、异常处理章节**
- 如果模块 A 依赖模块 B（如"用户管理"依赖"登录认证"），LLM 缺少 B 的上下文
- PRD 中的全局约束（如"所有页面需支持 401 跳转登录页"）不会出现在任何单模块输入中

---

### F10：PRD 超长时被隐式截断

**问题**：
- 整个 PRD 文本直接传给 `extract_modules`，如果 PRD 非常长（如 10 万字符），可能超出模型上下文窗口
- deepseek-chat 支持 128K，但系统 prompt + user message + response 可能接近上限
- LLM 会自行截断或跳过末尾内容，导致 PRD 尾部模块被忽略
- 没有**文本长度告警**或**自动分片策略**

---

## 问题严重度矩阵

| 失败点 | 严重度 | 发生概率 | 导致 100% 无法覆盖？ | 修复难度 |
|--------|--------|----------|---------------------|----------|
| F1 模块提取不完整 | **致命** | 高 | ✅ 是 | 中 |
| F3 重试同参确定性失败 | **致命** | 高 | ✅ 是 | 低 |
| F7 补全重复提取+同温 | **致命** | 高 | ✅ 是 | 低 |
| F8 无模块状态追踪 | **严重** | 中 | 间接导致 | 中 |
| F9 上下文隔离 | **严重** | 中 | 间接导致 | 中 |
| F2 单模块失败无立即重试 | 中等 | 低 | 间接导致 | 低 |
| F4 refine 丢弃用例 | 中等 | 低 | 否 | 低 |
| F5 去重误删 | 中等 | 低 | 否 | 低 |
| F6 校验不补漏 | 轻 | 高 | 间接导致 | 低 |
| F10 PRD 超长截断 | 轻 | 低（大型 PRD） | ✅ 是 | 中 |

---

## 解决方案（6 项，按影响从大到小）

### S1：多轮模块提取 + 完整性校验

**针对**：F1

- 第一次提取：按标题层级识别模块
- 第二次提取：扫描 PRD 中所有动宾短语（"查看xxx"、"导出xxx"、"删除xxx"），补充隐含模块
- 合并两次结果，去重
- 新增：与 PRD 标题数量进行粗略比对，差异 > 20% 时告警
- 在前端增加"模块确认"步骤（可选但推荐）

### S2：补全请求差异化参数

**针对**：F3, F7

- 补全/重试时临时将 `temperature` 从 0.15 提高到 0.35
- 补全 prompt 附加"失败原因"（"该模块在上一次低温生成中返回空结果"）
- 补全/重试改为**最多 3 次**，每次温度递增（0.15 → 0.25 → 0.35）
- `_regenerate_modules` 使用**原始模块数据**而非重新提取（从 `_generation_tasks` 读取）

### S3：模块级状态持久化

**针对**：F8

- 在 `_generation_tasks[task_id]` 中新增 `module_states` 字段：
  ```json
  {
    "登录模块": {"status": "covered", "retries": 0},
    "导出模块": {"status": "failed", "retries": 3, "reason": "PRD信息不足"}
  }
  ```
- `failed` 3 次的模块标记为 `needs_prd_update`，不再重试，前端显示为"需求缺失"
- 前端展示每个模块的生成状态（绿色/黄色/红色图标）

### S4：全局上下文注入

**针对**：F9

- 提取 PRD 中的"全局信息"（角色定义、公共规则、异常处理章节）
- `_build_module_input` 新增全局上下文前缀：
  ```
  【全局信息】
  角色定义：...  公共规则：...
  【当前模块】
  模块名：...  PRD原文：...
  ```

### S5：校验日志增强 + 丢弃检测

**针对**：F4, F5, F6

- Skill 6 后校验 `len(refined) == len(all_cases)`，不一致时告警并回退
- Skill 7 后校验 `len(deduped) >= len(refined) * 0.5`（删除超过 50% 时告警）
- `post_validation` 返回 `missing_modules` 后，不在 refine 循环中处理，而是触发**独立的缺失模块生成流程**

### S6：PRD 长度检测与分片

**针对**：F10

- 在 `generate()` 入口检测 PRD 长度，超过 50000 字符时打印 warning
- 超过 80000 字符时启用**按标题自动分片**策略（不是按字数硬切）
- 每片独立提取模块，最后合并

---

## 实施优先级

| 顺序 | 方案 | 预期效果 |
|------|------|---------|
| 第一批 | S2 + S3 | 补全成功率从 ~30% 提升至 ~80% |
| 第二批 | S1 + S4 | 模块提取完整度 ≥ 95% |
| 第三批 | S5 + S6 | 防丢 + 长 PRD 支持 |

---

## 实施后预期效果

- 单轮生成覆盖率 ≥ 85%
- 点击"补全"一次后覆盖率 ≥ 95%
- 连续失败 3 次的模块自动标记为"需求缺失"，不再无意义重试
- 无法覆盖的模块在 UI 上以警告图标展示，引导用户补充 PRD
