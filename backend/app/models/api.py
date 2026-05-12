from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ApiResponse(BaseModel):
    code: int = 200
    data: Optional[dict | list] = None
    message: str = "success"


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
