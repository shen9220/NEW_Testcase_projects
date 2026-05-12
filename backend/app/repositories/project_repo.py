from app.repositories.local_storage import LocalStorage
from app.repositories.supabase_client import get_supabase_client
from app.utils.id_generator import now_iso
import logging

logger = logging.getLogger(__name__)


class ProjectRepository:
    def __init__(self, local: LocalStorage):
        self.local = local

    async def create(self, task_id: str, original_filename: str, prd_content: str) -> dict:
        project = {
            "task_id": task_id,
            "original_filename": original_filename,
            "prd_content": prd_content,
            "status": "processing",
            "testcase_count": 0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        # Local write (sync, guaranteed)
        self.local.append_to_index(project)
        self.local.create_task_dir(task_id)
        self.local.save_text(task_id, "prd_content.md", prd_content)
        # Supabase write (best-effort)
        try:
            client = get_supabase_client()
            if client:
                client.table("projects").insert({
                    "task_id": task_id,
                    "original_filename": original_filename,
                    "prd_content": prd_content,
                    "status": "processing",
                    "testcase_count": 0,
                }).execute()
        except Exception as e:
            logger.warning(f"Supabase project create failed: {e}")
        return project

    async def get_by_task_id(self, task_id: str) -> dict | None:
        try:
            client = get_supabase_client()
            if client:
                result = client.table("projects").select("*").eq("task_id", task_id).execute()
                if result.data:
                    return result.data[0]
        except Exception:
            pass
        return self.local.get_from_index(task_id)

    async def update_status(self, task_id: str, status: str, testcase_count: int = 0):
        self.local.update_index(task_id, {"status": status, "testcase_count": testcase_count})
        try:
            client = get_supabase_client()
            if client:
                client.table("projects").update({
                    "status": status,
                    "testcase_count": testcase_count,
                    "updated_at": now_iso(),
                }).eq("task_id", task_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update failed: {e}")

    async def delete(self, task_id: str) -> bool:
        """Delete a project and all associated data."""
        # Remove from local storage
        self.local.remove_from_index(task_id)
        self.local.delete_task_dir(task_id)
        # Remove from Supabase (best-effort)
        try:
            client = get_supabase_client()
            if client:
                client.table("projects").delete().eq("task_id", task_id).execute()
                client.table("testcases").delete().eq("task_id", task_id).execute()
        except Exception as e:
            logger.warning(f"Supabase delete failed for {task_id}: {e}")
        return True

    async def list_all(self, page: int = 1, page_size: int = 20,
                       search: str = "", status: str = "") -> dict:
        all_items = self.local.list_projects()
        # Apply filters
        if search:
            search_lower = search.lower()
            all_items = [
                item for item in all_items
                if search_lower in item.get("original_filename", "").lower()
                or search_lower in item.get("task_id", "").lower()
            ]
        if status:
            all_items = [item for item in all_items if item.get("status") == status]
        total = len(all_items)
        start = (page - 1) * page_size
        end = start + page_size
        return {"items": all_items[start:end], "total": total, "page": page, "page_size": page_size}
