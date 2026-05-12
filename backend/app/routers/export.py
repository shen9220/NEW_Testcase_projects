import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services.export_service import generate_excel, generate_xmind
from app.services.log_service import log_operation
from app.repositories.local_storage import LocalStorage
from app.repositories.testcase_repo import TestcaseRepository

router = APIRouter(prefix="/export", tags=["export"])
_local = LocalStorage()
_testcase_repo = TestcaseRepository(_local)


@router.get("/excel")
async def export_excel(task_id: str, module: str = ""):
    """Export test cases as Excel file, optionally filtered by module."""
    all_cases = await _testcase_repo.get_all_by_task(task_id)
    testcases = [c for c in all_cases if not module or c.get("module") == module]
    if not testcases:
        raise HTTPException(status_code=404, detail="没有可导出的用例")

    filepath = generate_excel(testcases, task_id, module)
    suffix = f"_{module}" if module else ""
    filename = f"testcases_{task_id}{suffix}.xlsx"
    await log_operation(task_id, "export", f"导出Excel：{filename}（{len(testcases)}条用例）")
    return FileResponse(filepath, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/xmind")
async def export_xmind(task_id: str, module: str = ""):
    """Export test cases as XMind file, optionally filtered by module."""
    all_cases = await _testcase_repo.get_all_by_task(task_id)
    testcases = [c for c in all_cases if not module or c.get("module") == module]
    if not testcases:
        raise HTTPException(status_code=404, detail="没有可导出的用例")

    filepath = generate_xmind(testcases, task_id, module)
    suffix = f"_{module}" if module else ""
    filename = f"testcases_{task_id}{suffix}.xmind"
    await log_operation(task_id, "export", f"导出XMind：{filename}（{len(testcases)}条用例）")
    return FileResponse(filepath, filename=filename, media_type="application/octet-stream")
