from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.repositories.local_storage import LocalStorage
from app.repositories.log_repo import LogRepository
from app.services.log_service import log_operation

router = APIRouter(prefix="/logs", tags=["logs"])
_local = LocalStorage()
_log_repo = LogRepository(_local)


class FrontendActionLog(BaseModel):
    task_id: str = ""
    operation_type: str  # click, upload, generate, delete, export, view, edit
    detail: str
    operator: str = "user"


@router.post("/action")
async def log_frontend_action(action: FrontendActionLog):
    """Record a frontend user action (click, upload, etc.)."""
    await log_operation(
        action.task_id, action.operation_type, action.detail, action.operator
    )
    return {"code": 200, "data": None, "message": "action logged"}


@router.get("")
async def get_task_logs(task_id: str = "", page: int = 1, page_size: int = 50,
                        operation_type: str = ""):
    """Get logs for a specific task."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    result = await _log_repo.get_by_task(task_id, page, page_size, operation_type)
    return {"code": 200, "data": result, "message": "success"}


@router.get("/all")
async def get_all_logs(page: int = 1, page_size: int = 50,
                       operation_type: str = ""):
    """Get all global logs."""
    result = await _log_repo.get_all(page, page_size, operation_type)
    return {"code": 200, "data": result, "message": "success"}


@router.delete("")
async def clear_task_logs(task_id: str = ""):
    """Clear logs for a specific task."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    deleted = await _log_repo.clear_by_task(task_id)
    await log_operation(task_id, "delete", f"清除任务日志：{task_id}（{deleted}条）")
    return {"code": 200, "data": {"deleted": deleted}, "message": f"任务 {task_id} 日志已清除"}


@router.delete("/all")
async def clear_all_logs():
    """Clear all global logs."""
    deleted = await _log_repo.clear_all()
    return {"code": 200, "data": {"deleted": deleted}, "message": f"全部日志已清除（{deleted}条）"}
