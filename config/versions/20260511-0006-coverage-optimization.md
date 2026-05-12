---
date: 2026-05-11
type: optimization
---

# 测试用例覆盖率优化 — 6项修复

## Description
针对"补全后仍无法100%覆盖测试用例"问题，实施 analysis-01 中 6 项最优方案的组合修复，打破"模块提取不完整 → 低温确定性重试失败 → 补全再次失败"的恶性循环。

## Affected Files

- `backend/app/services/ai_generator.py`: S1 双轮模块提取、S2 温度递增重试、S3 模块状态追踪、S4 全局上下文注入、S5 丢弃检测
- `backend/app/services/skill_executor.py`: S5 模糊词从阻断降级为警告
- `backend/app/routers/generation.py`: F7 补全复用存储模块数据 + 温度递增
- `frontend/src/types/index.ts`: GenerationStats 新增 module_states 字段
- `frontend/src/pages/Workbench.tsx`: 模块状态可视化（needs_prd_update 红色标记）

## Notes

- S2 温度递增策略：首次生成 0.15 → 第一次重试 0.25 → 第二次重试 0.35；补全请求 0.35 → 0.5
- S3 模块生命周期：covered → failed → needs_prd_update（3次失败后标记，前端显示红色警告）
- S4 全局上下文从 PRD 中正则提取：角色定义、公共规则、异常处理、认证要求
- S5 丢弃阈值：refine 改变数量时回退；dedup 删除超过 50% 时回退
- F7 将首次提取的模块数据存入 _generation_tasks，补全时直接复用，不再重新提取
