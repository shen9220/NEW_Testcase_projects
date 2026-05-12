---
date: 2026-05-09
type: hotfix
---

# 修复 LLM API 持续超时 — 重试 + 自动 Fallback

## Description

上一版修复（`20260509-0001`）将 `bot_config.yaml` 配置加载并传入 `AsyncOpenAI`，超时从 SDK 默认 5s 提升到 10s，但问题仍然存在。

**深层根因**：通过抓取 `httpcore` 调试日志发现，TCP 连接 `api.openai.com:443` 完全无法建立（`ConnectTimeout`）。这是网络层面的阻断（特定网络环境下 OpenAI API 不可达），并非超时参数过短的问题。单纯增大超时值是无效的。

**修复策略**：

### 1. 连接超时提升至 30s
`connect=10.0` → `connect=30.0`，给慢速网络更多时间。

### 2. 自动重试（指数退避）
`LLMClient.chat()` 中捕获 `APITimeoutError` 和 `APIConnectionError`，最多重试 3 次，退避间隔 1s → 2s。

### 3. 自动 Fallback 到 DeepSeek
主 Bot（OpenAI）连续 3 次超时后，自动加载 `testcase_generator_deepseek` 配置（`api.deepseek.com`），切换客户端重试。DeepSeek API 在中国大陆可直接访问。

Fallback 切换流程：
```
OpenAI (gpt-4o-mini) 超时 ×3
  → 1s backoff → 2s backoff
  → 加载 testcase_generator_deepseek 配置
  → 重建 AsyncOpenAI (base_url → api.deepseek.com)
  → 重试 LLM 调用
  → 仍然失败 → 抛出明确的网络诊断错误
```

### 4. 更好的错误信息
失败时明确提示：「请检查网络连接或配置 VPN/代理」，而非只显示 "Request timed out"。

### 5. AIGenerationError 不重复包装
`_run_skill` 中 `AIGenerationError` 直接 `raise` 透传，不再加 `"Skill xxx 执行失败:"` 前缀，避免信息冗余。

## Affected Files

- `backend/app/services/ai_generator.py`: **修改** `LLMClient` 类和 `AIGenerator._run_skill`
  - `LLMClient.__init__`：新增 `fallback_bot_name` 参数，预加载 fallback 配置
  - `LLMClient._init_client`：`connect=30.0`，提取为独立方法
  - `LLMClient._switch_to_fallback`：**新增** — 动态切换到备用 Bot
  - `LLMClient.chat`：**重写** — 3 次重试 + 指数退避 + 自动 fallback
  - `AIGenerator._run_skill`：`AIGenerationError` 直接透传

## Notes

- Fallback Bot 需要有效的 API Key（`.env` 中 `COZE_DEEPSEEK_API_KEY` 需取消注释并填入真实 key）
- 如果 Fallback 也失败，会抛出包含两个 Bot 名称的详细错误
- 主 Bot 恢复后（如网络恢复），下次生成任务会重新从主 Bot 开始尝试
- `_run_skill` 对 `AIGenerationError` 的处理改为透传，避免错误信息层层包裹
