import logging
from app.repositories.log_repo import LogRepository
from app.repositories.local_storage import LocalStorage

logger = logging.getLogger(__name__)

# Singleton instances
_local = LocalStorage()
log_repo = LogRepository(_local)


async def log_operation(task_id: str, operation_type: str, detail: str, operator: str = "user"):
    """Record an operation log."""
    await log_repo.add(task_id, operation_type, detail, operator)
