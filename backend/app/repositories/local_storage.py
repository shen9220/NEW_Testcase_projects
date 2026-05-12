import json
import os
from app.config import settings
from app.utils.file_utils import ensure_dir
from app.utils.id_generator import now_iso


class LocalStorage:
    def __init__(self):
        self.data_dir = settings.data_dir
        self.index_file = os.path.join(self.data_dir, "projects_index.json")
        ensure_dir(self.data_dir)
        if not os.path.exists(self.index_file):
            self._write_index([])

    def _read_index(self) -> list:
        with open(self.index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_index(self, data: list):
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def append_to_index(self, project: dict):
        idx = self._read_index()
        idx.insert(0, {
            "task_id": project["task_id"],
            "original_filename": project.get("original_filename", ""),
            "prd_filename": project.get("prd_filename", "prd_content.md"),
            "created_at": project.get("created_at", now_iso()),
            "testcase_count": project.get("testcase_count", 0),
            "status": project.get("status", "processing"),
        })
        self._write_index(idx)

    def update_index(self, task_id: str, updates: dict):
        idx = self._read_index()
        for item in idx:
            if item["task_id"] == task_id:
                item.update(updates)
                break
        self._write_index(idx)

    def get_from_index(self, task_id: str) -> dict | None:
        idx = self._read_index()
        for item in idx:
            if item["task_id"] == task_id:
                return item
        return None

    def remove_from_index(self, task_id: str) -> bool:
        idx = self._read_index()
        new_idx = [item for item in idx if item["task_id"] != task_id]
        if len(new_idx) == len(idx):
            return False
        self._write_index(new_idx)
        return True

    def delete_task_dir(self, task_id: str):
        import shutil
        task_dir = self.get_task_dir(task_id)
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)

    def list_projects(self) -> list:
        return self._read_index()

    def create_task_dir(self, task_id: str):
        task_dir = os.path.join(self.data_dir, task_id)
        export_dir = os.path.join(task_dir, "export")
        ensure_dir(task_dir)
        ensure_dir(export_dir)
        return task_dir

    def get_task_dir(self, task_id: str) -> str:
        return os.path.join(self.data_dir, task_id)

    def save_text(self, task_id: str, filename: str, content: str):
        task_dir = self.get_task_dir(task_id)
        filepath = os.path.join(task_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def read_text(self, task_id: str, filename: str) -> str | None:
        filepath = os.path.join(self.get_task_dir(task_id), filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def save_json(self, task_id: str, filename: str, data):
        task_dir = self.get_task_dir(task_id)
        filepath = os.path.join(task_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    def read_json(self, task_id: str, filename: str) -> list | dict | None:
        filepath = os.path.join(self.get_task_dir(task_id), filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def copy_file(self, task_id: str, src_path: str, filename: str) -> str:
        import shutil
        task_dir = self.get_task_dir(task_id)
        dst = os.path.join(task_dir, filename)
        shutil.copy2(src_path, dst)
        return dst

    def save_binary(self, task_id: str, filename: str, content: bytes) -> str:
        task_dir = self.get_task_dir(task_id)
        filepath = os.path.join(task_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        return filepath

    def append_log(self, message: str, task_id: str = None):
        if task_id:
            log_path = os.path.join(self.get_task_dir(task_id), "log.txt")
        else:
            log_path = os.path.join(self.data_dir, "app.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(message + "\n")

    def clear_logs(self, task_id: str):
        """Clear the local log file for a specific task."""
        log_path = os.path.join(self.get_task_dir(task_id), "log.txt")
        if os.path.exists(log_path):
            os.remove(log_path)

    def clear_all_logs(self):
        """Clear the global app log file."""
        log_path = os.path.join(self.data_dir, "app.log")
        if os.path.exists(log_path):
            os.remove(log_path)

    def list_task_files(self, task_id: str, pattern: str = "*") -> list:
        import glob
        task_dir = self.get_task_dir(task_id)
        return glob.glob(os.path.join(task_dir, pattern))
