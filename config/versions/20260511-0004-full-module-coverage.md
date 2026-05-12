---
date: 2026-05-11
type: feature
---

# 确保测试用例覆盖完整 PRD — 防止模块遗漏

## Description

修复测试用例生成只能覆盖 PRD 部分内容的问题。实施"模块分治，分批生成"策略 + 消除信息不足即跳过逻辑 + 输出完整性交叉校验。

### 核心改动

1. **消除模块跳过（skill_executor.py）**
   - `check_module_availability` 不再跳过任何模块，所有模块均参与生成
   - 信息不完整的模块标记为 warnings 而非 skipped，生成带有 notes 标注的基础用例

2. **模块覆盖交叉校验（ai_generator.py）**
   - 生成完所有模块后，比对：提取的模块总数 vs 实际有 testcase 的模块数
   - 缺失模块自动以更强约束的 prompt 重试生成
   - `post_validation` 新增 `missing_modules` 检测

3. **丰富模块级用户输入（ai_generator.py `_build_module_input`）**
   - 传递全部提取字段：ui_elements、fields、actions、rules_explicit、states、missing_info
   - 无 UI 元素时明确告知 LLM 根据业务规则推断

4. **提升容量（bot_config.yaml）**
   - max_tokens: 4096 → 8192
   - request_timeout: 120s → 300s

5. **强化 Prompt（skill_prompts.py）**
   - `SKILL_GENERATE_FOR_MODULE`：严禁跳过模块，信息不足时在 notes 标注而非跳过
   - 最少一条 P0 正向用例的硬性要求

## Affected Files

- `backend/ai_engine/bot_config.yaml`: max_tokens 和 request_timeout 翻倍
- `backend/app/services/skill_executor.py`: `check_module_availability` 不再跳过模块；`post_validation` 新增缺失模块检测
- `backend/app/services/skill_prompts.py`: `SKILL_GENERATE_FOR_MODULE` 增加反跳过规则和 notes 标注指引
- `backend/app/services/ai_generator.py`: 新增 `_build_module_input`、模块覆盖交叉校验、缺失模块自动重试

## Notes

- 去除了原 "no_actionable_modules" 的提前失败路径 — 现在只要有模块提取出来就生成用例
- 统计字段从 `modules_skipped` 改为 `modules_with_warnings` + `modules_covered` + `modules_uncovered`
