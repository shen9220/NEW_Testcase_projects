import json
from app.repositories.local_storage import LocalStorage
from app.repositories.supabase_client import get_supabase_client
from app.utils.id_generator import now_iso
import logging

logger = logging.getLogger(__name__)


class TestcaseRepository:
    def __init__(self, local: LocalStorage):
        self.local = local

    async def save_batch(self, task_id: str, testcases: list, project_uuid: str = ""):
        """Save all test cases for a task."""
        self.local.save_json(task_id, "testcases.json", testcases)
        try:
            client = get_supabase_client()
            if client and project_uuid:
                rows = []
                for tc in testcases:
                    rows.append({
                        "project_id": project_uuid,
                        "case_id": tc.get("case_id", ""),
                        "module": tc.get("module", ""),
                        "title": tc.get("title", ""),
                        "precondition": tc.get("precondition", ""),
                        "steps": json.dumps(tc.get("steps", []), ensure_ascii=False),
                        "priority": tc.get("priority", "P2"),
                        "type": tc.get("type", "功能测试"),
                        "tags": json.dumps(tc.get("tags", []), ensure_ascii=False),
                        "notes": tc.get("notes", ""),
                        "is_deleted": tc.get("is_deleted", False),
                    })
                client.table("testcases").insert(rows).execute()
        except Exception as e:
            logger.warning(f"Supabase batch save failed: {e}")

    async def get_by_task(self, task_id: str, page: int = 1, page_size: int = 20,
                          module: str = "", priority: str = "", type_: str = "",
                          keyword: str = "") -> dict:
        try:
            client = get_supabase_client()
            if client:
                project_result = client.table("projects").select("id").eq("task_id", task_id).execute()
                if not project_result.data:
                    return {"items": [], "total": 0, "page": page, "page_size": page_size}
                project_id = project_result.data[0]["id"]
                query = client.table("testcases").select("*", count="exact") \
                    .eq("project_id", project_id) \
                    .eq("is_deleted", False)
                if module:
                    query = query.eq("module", module)
                if priority:
                    query = query.eq("priority", priority)
                if type_:
                    query = query.eq("type", type_)
                if keyword:
                    query = query.or_(f"title.ilike.%{keyword}%,module.ilike.%{keyword}%")
                result = query.order("case_id").range(
                    (page - 1) * page_size, page * page_size - 1
                ).execute()
                items = []
                for row in (result.data or []):
                    items.append(self._row_to_dict(row))
                return {"items": items, "total": result.count or 0, "page": page, "page_size": page_size}
        except Exception:
            pass
        # Fallback local
        data = self.local.read_json(task_id, "testcases.json") or []
        filtered = [tc for tc in data if not tc.get("is_deleted")]
        if module:
            filtered = [tc for tc in filtered if tc.get("module") == module]
        if priority:
            filtered = [tc for tc in filtered if tc.get("priority") == priority]
        if type_:
            filtered = [tc for tc in filtered if tc.get("type") == type_]
        if keyword:
            filtered = [tc for tc in filtered
                        if keyword.lower() in tc.get("title", "").lower()
                        or keyword.lower() in tc.get("module", "").lower()]
        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        return {"items": filtered[start:end], "total": total, "page": page, "page_size": page_size}

    async def get_by_case_id(self, task_id: str, case_id: str) -> dict | None:
        try:
            client = get_supabase_client()
            if client:
                proj = client.table("projects").select("id").eq("task_id", task_id).execute()
                if proj.data:
                    result = client.table("testcases").select("*") \
                        .eq("project_id", proj.data[0]["id"]) \
                        .eq("case_id", case_id).execute()
                    if result.data:
                        return self._row_to_dict(result.data[0])
        except Exception:
            pass
        data = self.local.read_json(task_id, "testcases.json") or []
        for tc in data:
            if tc.get("case_id") == case_id:
                return tc
        return None

    async def update(self, task_id: str, case_id: str, updates: dict) -> dict | None:
        updates["updated_at"] = now_iso()
        # Local update
        data = self.local.read_json(task_id, "testcases.json") or []
        updated_case = None
        for tc in data:
            if tc.get("case_id") == case_id:
                tc.update(updates)
                updated_case = tc
                break
        if updated_case:
            self.local.save_json(task_id, "testcases.json", data)
        # Supabase update
        try:
            client = get_supabase_client()
            if client:
                proj = client.table("projects").select("id").eq("task_id", task_id).execute()
                if proj.data:
                    supabase_updates = {k: v for k, v in updates.items() if k != "id"}
                    if "steps" in supabase_updates:
                        supabase_updates["steps"] = json.dumps(supabase_updates["steps"], ensure_ascii=False)
                    if "tags" in supabase_updates:
                        supabase_updates["tags"] = json.dumps(supabase_updates["tags"], ensure_ascii=False)
                    client.table("testcases").update(supabase_updates) \
                        .eq("project_id", proj.data[0]["id"]) \
                        .eq("case_id", case_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update failed: {e}")
        return updated_case

    async def soft_delete(self, task_id: str, case_id: str) -> bool:
        return await self.update(task_id, case_id, {"is_deleted": True}) is not None

    async def batch_soft_delete(self, task_id: str, case_ids: list[str]) -> int:
        count = 0
        data = self.local.read_json(task_id, "testcases.json") or []
        for tc in data:
            if tc.get("case_id") in case_ids:
                tc["is_deleted"] = True
                tc["updated_at"] = now_iso()
                count += 1
        self.local.save_json(task_id, "testcases.json", data)
        try:
            client = get_supabase_client()
            if client:
                proj = client.table("projects").select("id").eq("task_id", task_id).execute()
                if proj.data:
                    client.table("testcases").update({"is_deleted": True}) \
                        .eq("project_id", proj.data[0]["id"]) \
                        .in_("case_id", case_ids).execute()
        except Exception as e:
            logger.warning(f"Supabase batch delete failed: {e}")
        return count

    async def get_all_by_task(self, task_id: str) -> list:
        data = self.local.read_json(task_id, "testcases.json") or []
        return [tc for tc in data if not tc.get("is_deleted")]

    def _row_to_dict(self, row: dict) -> dict:
        steps = row.get("steps", [])
        if isinstance(steps, str):
            steps = json.loads(steps)
        tags = row.get("tags", [])
        if isinstance(tags, str):
            tags = json.loads(tags)
        return {
            "id": row.get("id", ""),
            "case_id": row.get("case_id", ""),
            "module": row.get("module", ""),
            "title": row.get("title", ""),
            "precondition": row.get("precondition", ""),
            "steps": steps,
            "priority": row.get("priority", "P2"),
            "type": row.get("type", "功能测试"),
            "tags": tags,
            "notes": row.get("notes", ""),
            "is_deleted": row.get("is_deleted", False),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
