from app.repositories.local_storage import LocalStorage
from app.repositories.supabase_client import get_supabase_client
from app.utils.id_generator import now_iso
import logging

logger = logging.getLogger(__name__)


class LogRepository:
    def __init__(self, local: LocalStorage):
        self.local = local

    async def add(self, task_id: str, operation_type: str, detail: str, operator: str = "user"):
        timestamp = now_iso()
        log_line = f"[{timestamp}] [{operation_type}] {detail}"
        self.local.append_log(log_line, task_id)
        if task_id:
            self.local.append_log(log_line, None)  # Also global log
        try:
            client = get_supabase_client()
            if client:
                proj_id = None
                if task_id:
                    proj = client.table("projects").select("id").eq("task_id", task_id).execute()
                    if proj.data:
                        proj_id = proj.data[0]["id"]
                client.table("logs").insert({
                    "project_id": proj_id,
                    "task_id": task_id or None,
                    "operation_type": operation_type,
                    "detail": detail,
                    "operator": operator,
                }).execute()
        except Exception as e:
            logger.warning(f"Supabase log failed: {e}")

    async def get_by_task(self, task_id: str, page: int = 1, page_size: int = 50,
                          operation_type: str = "") -> dict:
        try:
            client = get_supabase_client()
            if client:
                query = client.table("logs").select("*", count="exact").eq("task_id", task_id)
                if operation_type:
                    query = query.eq("operation_type", operation_type)
                result = query.order("created_at", desc=True) \
                    .range((page - 1) * page_size, page * page_size - 1).execute()
                return {"items": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}
        except Exception:
            pass
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    async def get_all(self, page: int = 1, page_size: int = 50,
                      operation_type: str = "") -> dict:
        try:
            client = get_supabase_client()
            if client:
                query = client.table("logs").select("*", count="exact")
                if operation_type:
                    query = query.eq("operation_type", operation_type)
                result = query.order("created_at", desc=True) \
                    .range((page - 1) * page_size, page * page_size - 1).execute()
                return {"items": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}
        except Exception:
            pass
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    async def clear_by_task(self, task_id: str) -> int:
        """Clear all logs for a specific task. Returns number deleted."""
        deleted = 0
        try:
            client = get_supabase_client()
            if client:
                result = client.table("logs").delete().eq("task_id", task_id).execute()
                deleted = len(result.data) if result.data else 0
        except Exception as e:
            logger.warning(f"Supabase clear logs for task {task_id} failed: {e}")
        # Also clear local log file
        self.local.clear_logs(task_id)
        return deleted

    async def clear_all(self) -> int:
        """Clear all logs globally. Returns number deleted."""
        deleted = 0
        try:
            client = get_supabase_client()
            if client:
                result = client.table("logs").delete().neq("task_id", "__never__").execute()
                deleted = len(result.data) if result.data else 0
        except Exception as e:
            logger.warning(f"Supabase clear all logs failed: {e}")
        self.local.clear_all_logs()
        return deleted
