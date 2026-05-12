from fastapi import APIRouter, HTTPException
from app.models.testcase import TestCaseUpdate, BatchDeleteRequest
from app.services.log_service import log_operation
from app.repositories.local_storage import LocalStorage
from app.repositories.testcase_repo import TestcaseRepository

router = APIRouter(prefix="/testcases", tags=["testcases"])
_local = LocalStorage()
_testcase_repo = TestcaseRepository(_local)


@router.get("")
async def list_testcases(task_id: str = "", page: int = 1, page_size: int = 20,
                         module: str = "", priority: str = "", type_: str = "", keyword: str = ""):
    """Paginated list of test cases with optional filters."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    result = await _testcase_repo.get_by_task(
        task_id, page, page_size, module=module, priority=priority, type_=type_, keyword=keyword
    )
    return {"code": 200, "data": result, "message": "success"}


@router.get("/{case_id}")
async def get_testcase(case_id: str, task_id: str = ""):
    """Get a single test case detail."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    tc = await _testcase_repo.get_by_case_id(task_id, case_id)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    return {"code": 200, "data": tc, "message": "success"}


@router.put("/{case_id}")
async def update_testcase(case_id: str, updates: TestCaseUpdate, task_id: str = ""):
    """Update a test case."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    update_dict = updates.model_dump(exclude_unset=True)
    result = await _testcase_repo.update(task_id, case_id, update_dict)
    if not result:
        raise HTTPException(status_code=404, detail="用例不存在")
    await log_operation(task_id, "edit", f"编辑用例：{case_id} - {result.get('title', '')}")
    return {"code": 200, "data": result, "message": "用例已更新"}


@router.delete("/{case_id}")
async def delete_testcase(case_id: str, task_id: str = ""):
    """Soft delete a test case."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    ok = await _testcase_repo.soft_delete(task_id, case_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用例不存在")
    await log_operation(task_id, "delete", f"删除用例：{case_id}")
    return {"code": 200, "data": {"case_id": case_id, "is_deleted": True}, "message": "用例已删除（逻辑删除）"}


@router.post("/batch-delete")
async def batch_delete_testcases(req: BatchDeleteRequest, task_id: str = ""):
    """Batch soft delete test cases."""
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id 参数必填")
    count = await _testcase_repo.batch_soft_delete(task_id, req.case_ids)
    await log_operation(task_id, "batch_delete", f"批量删除{count}条用例：{', '.join(req.case_ids[:5])}...")
    return {"code": 200, "data": {"deleted_count": count, "deleted_ids": req.case_ids}, "message": f"已批量删除{count}条用例"}
