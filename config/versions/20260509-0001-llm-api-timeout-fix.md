---
date: 2026-05-09
type: hotfix
---

# 修复 LLM API 超时 — bot_config.yaml 配置生效

## Description

AI 生成测试用例时报错 `Skill extract_modules 执行失败: LLM API 调用失败: Request timed out`。

**根因**：`backend/ai_engine/bot_config.yaml` 定义了 `request_timeout: 120`，但没有任何 Python 代码加载该 YAML 文件（死配置）。`LLMClient.__init__` 创建 `AsyncOpenAI` 时未传递 `timeout` 参数，SDK 内部使用默认值 `httpx.Timeout(timeout=600.0, connect=5.0)`。**5 秒连接超时**在网络访问 OpenAI API 较慢时直接触发超时。

此外 `model`、`temperature`、`max_tokens`、`base_url` 在 YAML 和代码中重复定义，YAML 中的值被忽略。

**修复**：
1. 新建 `backend/app/utils/bot_config_loader.py`，加载 YAML 并解析 `${ENV_VAR}` 占位符
2. 修改 `LLMClient.__init__` 调用 `load_bot_config()`，配置 `httpx.Timeout(timeout=120.0, connect=10.0)`
3. `api_key` 三级回退：YAML → `settings.openai_api_key` → `os.getenv`
4. `model`/`temperature`/`max_tokens` 优先从 YAML 读取

**超时策略**：
| 参数 | 修复前 | 修复后 |
|------|--------|--------|
| 连接超时 | 5s（SDK 默认） | 10s |
| 请求总超时 | 600s（SDK 默认） | 120s（YAML 配置） |

## Affected Files

- `backend/app/utils/bot_config_loader.py`: **新建** — YAML 配置加载器，正则解析 `${ENV_VAR}` 占位符（先查 `COZE_{VAR}` 适配 pydantic-settings 前缀，再查 `{VAR}`）
- `backend/app/services/ai_generator.py`: **修改** — `LLMClient.__init__` 加载 YAML 配置，传入 httpx.Timeout，api_key/model/temperature/max_tokens 从 YAML 读取
- `backend/requirements.txt`: **修改** — 添加 `pyyaml>=6.0` 显式依赖（之前仅作为传递依赖存在）

## Notes

- `bot_config.yaml` 加载失败（文件缺失/YAML 格式错误/bot 名不存在）时不崩溃，warn 并 fallback 到硬编码默认值
- `${ENV_VAR}` 解析先尝试 `COZE_{VAR}`（匹配 `.env` 的 `COZE_` 前缀），再尝试 `{VAR}` 裸名
- `LLMClient` 的 `bot_name` 参数默认为 `"testcase_generator"`，可传 `"testcase_generator_deepseek"` 切换到 DeepSeek
