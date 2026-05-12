---
date: 2026-05-11
type: feature
---

# optimize02 小版本迭代 — 7 项 UX 优化

## Description

基于 `config/optimize/optimize02.md` 实施剩余未完成的优化项。

### 1. 日志展示区（Item 6）

- 生成过程中每 2s 轮询拉取操作日志
- 左侧面板新增"生成日志"卡片，实时滚动显示最新日志条目
- 日志格式：`[时间] 操作详情`

### 2. 模块单条重试（Item 7）

- **后端**：新增 `POST /api/v1/generation/{task_id}/regenerate-module/{module_name}` 端点
- 未覆盖模块 Tag 内嵌"重试"按钮（带旋转动画），点击仅重新生成该模块
- 多个未覆盖模块时仍保留"全部补全"按钮

### 3. 模块状态展示区（Item 8）

- 已有：模块覆盖率进度条 + `module_states` 状态区分（covered / failed / needs_prd_update）
- 本次增强：未覆盖模块支持逐条重试，实时显示重试状态

### 4. 全局上下文展示区（Item 9）

- 生成中/完成后在左侧面板展示从 PRD 提取的全局上下文
- 包括：角色定义、公共规则、异常处理（正则提取，不额外调用 LLM）

### 5. 历史任务删除（Item 13）

- **后端**：新增 `DELETE /api/v1/projects/{task_id}` 端点
- **存储层**：`LocalStorage` 新增 `remove_from_index()` 和 `delete_task_dir()`
- **前端**：每个历史任务项增加删除按钮（Popconfirm 二次确认）
- 删除后自动清理本地文件（含测试用例数据）

### 6. 历史任务搜索（Item 14）

- **后端**：`GET /projects` 新增 `search` 参数，按文件名和任务 ID 模糊匹配
- **前端**：搜索框（支持回车触发），带清除按钮

### 7. 历史任务筛选（Item 15）

- **后端**：`GET /projects` 新增 `status` 参数
- **前端**：状态下拉筛选（完成/部分完成/失败/处理中）

## Affected Files

| 文件 | 变更 |
|------|------|
| `backend/app/repositories/local_storage.py` | 新增 `remove_from_index()`、`delete_task_dir()` |
| `backend/app/repositories/project_repo.py` | 新增 `delete()`；`list_all()` 增加 search/status 参数 |
| `backend/app/routers/projects.py` | 新增 `DELETE /{task_id}`；`GET /` 增加 search/status 参数 |
| `backend/app/routers/generation.py` | 新增 `POST /{task_id}/regenerate-module/{module_name}` + `_regenerate_single_module()` |
| `frontend/src/services/projectService.ts` | 新增 `deleteProject`；`listProjects` 增加 search/status 参数 |
| `frontend/src/services/generationService.ts` | 新增 `regenerateSingleModule` |
| `frontend/src/components/HistoryPanel.tsx` | 重写：增加删除按钮、搜索框、状态筛选 |
| `frontend/src/pages/Workbench.tsx` | 新增日志面板、全局上下文卡片、模块单条重试按钮、`regenerateSingleModule` 导入 |

## Notes

- 模块单条重试用温度 0.35→0.5 重试（比首次生成的 0.15 高），打破确定性
- 日志面板通过已有的 `POST /logs/action` 端点记录的操作日志展示
- 全局上下文使用纯正则提取，无需额外 LLM 调用
- 删除操作同时清理本地文件目录和索引
- 相关需求文档：`config/optimize/optimize02.md`
