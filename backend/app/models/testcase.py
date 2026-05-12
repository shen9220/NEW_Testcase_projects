from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TestStep(BaseModel):
    action: str
    expected: str


class TestCase(BaseModel):
    id: str = ""
    case_id: str = ""
    module: str = ""
    title: str = ""
    precondition: str = ""
    steps: list[TestStep] = []
    priority: str = "P2"
    type: str = "功能测试"
    tags: list[str] = []
    notes: str = ""
    is_deleted: bool = False
    created_at: str = ""
    updated_at: str = ""


class TestCaseUpdate(BaseModel):
    module: Optional[str] = None
    title: Optional[str] = None
    precondition: Optional[str] = None
    steps: Optional[list[TestStep]] = None
    priority: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class BatchDeleteRequest(BaseModel):
    case_ids: list[str]
