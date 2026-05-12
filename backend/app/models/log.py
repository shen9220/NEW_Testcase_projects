from pydantic import BaseModel
from datetime import datetime


class LogEntry(BaseModel):
    id: str = ""
    task_id: str = ""
    operation_type: str = ""
    detail: str = ""
    operator: str = "user"
    created_at: str = ""
