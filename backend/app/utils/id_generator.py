import re
import uuid
from datetime import datetime


def generate_task_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def generate_case_id(index: int) -> str:
    return f"tc-{index + 1:03d}"


def generate_uuid() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now().isoformat()
