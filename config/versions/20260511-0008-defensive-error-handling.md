---
date: 2026-05-11
type: hotfix
---

# Bug Fix: 'str' object has no attribute 'get' + 综合错误处理加固

## Description

### Bug 修复

**问题**：生成测试用例时报 `'str' object has no attribute 'get'`。

**根因**：LLM 返回的模块列表可能包含纯字符串（如 `{"modules": ["用户管理", "权限管理"]}`），而后续代码假定每个模块都是 dict 并调用 `.get("name")`。

**修复**：
1. 新增 `AIGenerator._normalize_module()` / `_normalize_modules()` 静态方法，在模块提取后统一将字符串模块转换为 `{"name": "..."}` 结构
2. 在 `check_module_availability()` 中增加 `isinstance(mod, str)` 防御检查
3. 在 `_build_module_input()` 中增加入参类型防御
4. 在并行生成的 `_generate_one_module()` 中增加防御检查

### 综合错误处理加固（基于 `config/md/PRD-errors.md`）

**统一错误响应中间件**
- `main.py` 新增全局 `exception_handler`，捕获所有未处理异常
- 返回标准化错误响应：`{code, message, error_type, detail, suggestion}`
- 定义 14 种标准错误类型码（`JSON_PARSE_ERROR`、`LLM_TIMEOUT` 等）

**PRD 内容预校验**
- 新增 `AIGenerator.validate_prd()` 静态方法
- 在 `generate()` 开始时校验：非空、不少于 50 字符、包含功能描述结构
- 校验失败立即返回标准化错误，不浪费 LLM 调用

**文件上传校验**
- 新增文件扩展名白名单：`.md` / `.docx` / `.pdf` / `.txt`
- 新增 10MB 文件大小上限检查（读取后立即校验）
- 新增空文件检测
- 新增解析后内容为空的检测

**JSON 解析防御**
- `_extract_json()` 改进：优先匹配 `{...}` 对象，再匹配 `[...]` 数组
- `_run_skill()` 已有 json_repair + 重试机制，保持不变

## Affected Files

| 文件 | 变更 |
|------|------|
| `backend/app/services/ai_generator.py` | 新增 `validate_prd()`、`_normalize_module()`、`_normalize_modules()`；`_extract_json()` 改进；`generate()` 增加 PRD 校验；多处防御检查 |
| `backend/app/services/skill_executor.py` | `check_module_availability()` 增加字符串模块防御 |
| `backend/app/main.py` | 新增全局 `exception_handler`、`ERROR_TYPES` 字典 |
| `backend/app/routers/documents.py` | 新增文件类型/大小/空文件校验；新增空内容检测 |
| `config/md/PRD 处理与测试用例生成常见错误及综合解决方案.md` | 用户提供的错误清单参考文档 |

## Notes

- 模块标准化在所有入口点（提取后、校验、构建输入、并行生成）都做了防御，确保任何路径都不会再出现字符串当作 dict 的问题
- 全局异常处理器会根据异常类型名称和消息关键词自动分类，前端可据此展示不同 UI
- 参考文档：`config/md/PRD 处理与测试用例生成常见错误及综合解决方案.md`
