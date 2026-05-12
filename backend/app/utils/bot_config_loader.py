"""Load bot configuration from YAML, resolving environment variable placeholders."""
import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_var(match: re.Match) -> str:
    var_name = match.group(1)
    value = os.environ.get(f"COZE_{var_name}")
    if value:
        return value
    return os.environ.get(var_name, "")


def _resolve_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_VAR_PATTERN.sub(_resolve_env_var, value)
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item) for item in value]
    return value


def load_bot_config(bot_name: str = "testcase_generator") -> Dict[str, Any]:
    config_path = Path(__file__).resolve().parents[2] / "ai_engine" / "bot_config.yaml"

    with open(config_path, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    bots = raw_config.get("bots", {})
    if bot_name not in bots:
        raise KeyError(
            f"Bot '{bot_name}' not found in {config_path}. "
            f"Available: {list(bots.keys())}"
        )

    return _resolve_placeholders(bots[bot_name])
