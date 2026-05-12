---
date: 2026-05-09
type: hotfix
---

# LLM JSON 解析容错修复

## Description

修复 Skill extract_modules 及其他 Skill 输出 JSON 解析失败的问题。LLM 生成的 JSON 常存在未闭合字符串、未转义引号、Markdown 代码块包裹等问题。

实施来自解决方案文档的最优组合方案（方案 1 + 2 + 3 + 4），覆盖以下四种故障模式：

1. **输出截断** — max_tokens 不足导致 JSON 不完整，通过 `finish_reason` 检测并自动以 2x max_tokens 重试
2. **微小格式错误** — 缺少引号、括号不匹配等，通过 `json_repair` 库自动修复
3. **Markdown 包裹** — 输出含 ``` 标记，通过正则剥离后提取
4. **额外非 JSON 文本** — 通过括号匹配算法定位 JSON 块边界

## Affected Files

- `backend/app/services/ai_generator.py`: 核心变更
  - `LLMClient.chat()` 返回值从 `str` 改为 `tuple[str, str]`（content, finish_reason）
  - 新增 `_extract_json()` 方法：剥离 Markdown fences + 括号匹配
  - 重写 `_run_skill()`：json.loads → repair_json → 截断检测(2x max_tokens) → hardened prompt 重试 → 最终 repair_json
- `backend/app/services/skill_prompts.py`: `SKILL_EXTRACT_MODULES` 新增明确的 JSON 格式约束
- `backend/requirements.txt`: 新增 `json_repair>=0.30`

## Notes

- `finish_reason="length"` 是 OpenAI API 的截断信号，DeepSeek API 兼容此行为
- `json_repair` 对于未闭合字符串的处理策略是"以空字符串闭合"，因此截断检测在先更具语义精确性
- 重试上限 2 次，避免无限循环消耗 API 额度
