---
date: 2026-05-11
type: optimization
---

# 测试用例生成速度优化

## Description

针对测试用例生成流程耗时长、无进度反馈、无法取消等问题，实施三阶段优化方案。

### Phase 1: Hotfix（进度 + 取消 + 超时）

**进度回调机制**
- `AIGenerator.generate()` 新增 `progress_callback` 参数，9 个进度上报节点
- `_run_generation()` 传入回调函数，实时更新 `_generation_tasks[task_id]["progress"]`
- 前端 Steps 组件从静态（永远卡在第 1 步）变为实时推进
- 进度详情展示当前模块名称和进度（如"模块 3/7: 用户管理"）

**取消生成端点**
- 新增 `POST /api/v1/generation/{task_id}/cancel`
- 通过 `asyncio.Event` 信号机制在 Skill 之间检查取消标志
- 取消后保存已生成的部分结果，状态标记为 `partial`
- 前端新增红色"取消生成"按钮（仅在生成中可见）

**服务端超时保护**
- `_run_generation()` 包裹 `asyncio.wait_for(timeout=600s)`
- 超时后保存部分结果，避免全部丢失
- 新增 `GenerationCancelledError` 异常类型

### Phase 2: Feature（性能优化）

**并行化模块生成**
- Skill 2 从串行 for 循环改为 `asyncio.gather()` + `asyncio.Semaphore(3)`
- 5 模块从 5×30s=150s 降至 ceil(5/3)×30s=60s（**节省 60%**）
- 单个模块失败不影响其他（`return_exceptions=True`）

**并行化 Skill 3 + 5**
- 约束提取和状态转换并行执行（两者仅依赖 PRD 文本，互不依赖）
- `asyncio.gather()` 同时发起两个 LLM 调用

**Skill 5 条件化**
- 检查 PRD 是否包含状态转换关键词（状态/流转/审批/驳回等）
- 无状态关键词的 PRD 直接跳过 Skill 5，节省 1 次 LLM 调用

**PRD 模块提取缓存**
- 对 PRD 内容做 SHA256 hash，缓存模块提取结果 24 小时
- 相同 PRD 再次生成时直接复用，跳过 Skill 1（节省 2 次 LLM 调用）

### Phase 3: UX Enhancement

**前端实时进度**
- Steps 组件使用后端推送的动态 skill_name
- 进度详情文字展示当前处理的模块

## Affected Files

| 文件 | 变更 |
|------|------|
| `backend/app/services/ai_generator.py` | 新增 `progress_callback`/`cancellation_event` 参数；并行化 Skill 2；并行化 Skill 3+5；Skill 5 条件化；PRD hash 缓存；新增 `SKILL_LABELS`、`STATE_TRANSITION_KEYWORDS`、`GenerationCancelledError` |
| `backend/app/routers/generation.py` | 新增 `POST /cancel` 端点；`_run_generation` 增加 `progress_callback`、`asyncio.wait_for` 超时、`GenerationCancelledError` 处理 |
| `frontend/src/services/generationService.ts` | 新增 `cancelGeneration` API 函数 |
| `frontend/src/pages/Workbench.tsx` | 新增取消按钮；Steps 动态名称/详情；处理 cancelled 状态 |
| `config/optimize/optimize03-generation-speed.md` | **新建** 根因分析与方案文档 |

## Notes

- Semaphore(3) 限流防止 DeepSeek API 并发超限
- 缓存使用进程内 dict，服务重启后失效（可后续升级为文件/Redis 持久化）
- 取消信号在每个 Skill 边界检查，如果当前 Skill 正在执行 LLM 调用，需等待该调用完成后才响应取消
- 相关需求文档：`config/optimize/optimize02.md` 第 12 项

## Expected Improvements

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 典型 5 模块生成时间 | ~4-5 分钟 | ~1.5-2 分钟 |
| LLM 调用次数 | 11 次 | 6-7 次 |
| 进度更新 | 0 次 | 每模块/每 Skill 实时更新 |
| 可取消 | 不支持 | 支持 |
| 超时保护 | 无 | 10 分钟硬超时 |
