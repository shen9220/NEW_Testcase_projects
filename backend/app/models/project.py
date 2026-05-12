from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    document_id: str
    task_id: str
    original_filename: str
    prd_content: str
    file_size: int = 0


class DocumentRawRequest(BaseModel):
    content: str
    title: str = "手动输入"


class GenerationStartRequest(BaseModel):
    task_id: str


class GenerationStatus(BaseModel):
    task_id: str
    status: str  # processing / completed / failed / partial
    progress: Optional[dict] = None
    testcase_count: int = 0
    stats: Optional[dict] = None
    failure: Optional[dict] = None
    validation_issues: Optional[list] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None


class ProjectInfo(BaseModel):
    task_id: str
    original_filename: str
    testcase_count: int = 0
    status: str = "processing"
    created_at: str = ""
