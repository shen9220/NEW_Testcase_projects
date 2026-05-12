import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.parser import parse_upload, parse_markdown_text, DocumentParseError
from app.services.log_service import log_operation
from app.repositories.local_storage import LocalStorage
from app.repositories.project_repo import ProjectRepository
from app.utils.file_utils import sanitize_filename
from app.utils.id_generator import generate_task_id
from app.models.project import DocumentUploadResponse, DocumentRawRequest

router = APIRouter(prefix="/documents", tags=["documents"])
_local = LocalStorage()
_project_repo = ProjectRepository(_local)


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".md", ".markdown", ".docx", ".pdf", ".txt"}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and parse a PRD file."""
    # Validate file extension
    _, ext = os.path.splitext(file.filename or "")
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext or '未知'}，仅支持 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and validate file size
    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大 ({len(raw_bytes) / 1024 / 1024:.1f}MB)，限制 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB",
        )
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="文件为空，请检查文件内容")

    # Reset file cursor for parser
    await file.seek(0)

    try:
        filename, markdown, raw_bytes = await parse_upload(file)
    except DocumentParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)[:200]}")

    if not markdown or not markdown.strip():
        raise HTTPException(status_code=422, detail="文件解析后内容为空，请确认文件包含可提取的文本")

    task_id = generate_task_id()
    safe_name = sanitize_filename(os.path.splitext(filename)[0])
    task_id_full = f"{task_id}-{safe_name}"
    ext = os.path.splitext(filename)[1]

    # Save locally
    await _project_repo.create(task_id_full, filename, markdown)
    _local.create_task_dir(task_id_full)
    _local.save_binary(task_id_full, f"original{ext}", raw_bytes)
    _local.save_text(task_id_full, "prd_content.md", markdown)

    await log_operation(task_id_full, "upload", f"上传文件：{filename} (task_id: {task_id_full})")

    return {
        "code": 200,
        "data": {
            "document_id": task_id_full,
            "task_id": task_id_full,
            "original_filename": filename,
            "prd_content": markdown,
            "file_size": len(raw_bytes),
        },
        "message": "success",
    }


@router.post("/raw")
async def submit_raw_text(req: DocumentRawRequest):
    """Submit manually entered PRD text."""
    try:
        parse_markdown_text(req.content)
    except DocumentParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    task_id = generate_task_id()
    safe_name = sanitize_filename(req.title or "手动输入")
    task_id_full = f"{task_id}-{safe_name}"

    await _project_repo.create(task_id_full, f"{safe_name}.md", req.content)
    _local.create_task_dir(task_id_full)
    _local.save_text(task_id_full, "prd_content.md", req.content)

    await log_operation(task_id_full, "upload", f"手动输入PRD：{req.title} (task_id: {task_id_full})")

    return {
        "code": 200,
        "data": {
            "document_id": task_id_full,
            "task_id": task_id_full,
            "original_filename": f"{safe_name}.md",
            "prd_content": req.content,
            "file_size": len(req.content.encode("utf-8")),
        },
        "message": "success",
    }


@router.get("/{task_id}/content")
async def get_document_content(task_id: str):
    """Get the parsed markdown content of a document."""
    project = await _project_repo.get_by_task_id(task_id)
    if not project:
        prd_content = _local.read_text(task_id, "prd_content.md")
        if not prd_content:
            raise HTTPException(status_code=404, detail="文档不存在")
        return {
            "code": 200,
            "data": {"task_id": task_id, "original_filename": "", "prd_content": prd_content, "created_at": ""},
            "message": "success",
        }
    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "original_filename": project.get("original_filename", ""),
            "prd_content": project.get("prd_content", ""),
            "created_at": project.get("created_at", ""),
        },
        "message": "success",
    }
