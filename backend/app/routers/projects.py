import logging
from fastapi import APIRouter, HTTPException
from app.repositories.local_storage import LocalStorage
from app.repositories.project_repo import ProjectRepository
from app.services.log_service import log_operation

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)
_local = LocalStorage()
_project_repo = ProjectRepository(_local)


@router.get("")
async def list_projects(page: int = 1, page_size: int = 20,
                         search: str = "", status: str = ""):
    """List all project/task history with optional search and status filter."""
    result = await _project_repo.list_all(page, page_size, search=search, status=status)
    return {"code": 200, "data": result, "message": "success"}


@router.delete("/{task_id}")
async def delete_project(task_id: str):
    """Delete a project and all associated data."""
    project = await _project_repo.get_by_task_id(task_id)
    if not project:
        raise HTTPException(status_code=404, detail="任务不存在")
    await _project_repo.delete(task_id)
    await log_operation(task_id, "delete", f"删除任务：{task_id}")
    logger.info(f"Deleted project: {task_id}")
    return {"code": 200, "data": {"task_id": task_id}, "message": "已删除"}
