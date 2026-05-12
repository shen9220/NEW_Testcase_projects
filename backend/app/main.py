import time
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.routers import documents, generation, testcases, export, logs, projects

logger = logging.getLogger("request")

# ── Unified error type codes (aligned with config/md/PRD-errors.md) ──
ERROR_TYPES = {
    "JSON_PARSE_ERROR": "AI 返回内容解析失败",
    "LLM_TIMEOUT": "AI 服务响应超时",
    "LLM_UNAUTHORIZED": "AI API Key 无效",
    "LLM_CONTEXT_OVERFLOW": "PRD 内容超出模型上下文限制",
    "LLM_OUTPUT_TRUNCATED": "AI 输出被截断",
    "LLM_CONTENT_FILTERED": "内容被安全审核拦截",
    "NO_MODULES_EXTRACTED": "未能从 PRD 提取到功能模块",
    "PARTIAL_COVERAGE": "部分模块未生成用例",
    "PRD_EMPTY": "PRD 内容为空",
    "PRD_TOO_SHORT": "PRD 内容过短，无法提取功能模块",
    "UNSUPPORTED_FILE_TYPE": "不支持的文件格式",
    "FILE_TOO_LARGE": "文件大小超过限制",
    "FILE_READ_ERROR": "文件读取失败",
    "STORAGE_ERROR": "数据存储失败",
    "INTERNAL_ERROR": "服务器内部错误",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    os.makedirs(settings.data_dir, exist_ok=True)
    yield


app = FastAPI(
    title="AI Testcase Generator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request with method, path, status, and duration."""
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        f"{request.method} {request.url.path} → {response.status_code} "
        f"({duration_ms:.0f}ms)"
    )
    return response


# ── Global exception handlers ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return standardized error response."""
    error_type = "INTERNAL_ERROR"
    suggestion = "请重试，如持续出现请联系管理员"

    exc_name = type(exc).__name__
    exc_msg = str(exc)

    if "JSONDecodeError" in exc_name or "json" in exc_msg.lower():
        error_type = "JSON_PARSE_ERROR"
        suggestion = "AI 返回格式异常，请重试或检查 PRD 内容"
    elif "TimeoutError" in exc_name or "timeout" in exc_msg.lower():
        error_type = "LLM_TIMEOUT"
        suggestion = "AI 服务响应超时，请稍后重试"
    elif "Unauthorized" in exc_name or "401" in exc_msg:
        error_type = "LLM_UNAUTHORIZED"
        suggestion = "AI API Key 无效，请检查配置"
    elif "context" in exc_msg.lower() and "length" in exc_msg.lower():
        error_type = "LLM_CONTEXT_OVERFLOW"
        suggestion = "PRD 内容过长，请精简后重试"
    elif "AttributeError" in exc_name:
        error_type = "INTERNAL_ERROR"
        suggestion = "数据处理异常，请检查 PRD 格式或重试"

    logger.error(f"Unhandled {error_type}: {exc}\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "data": None,
            "message": ERROR_TYPES.get(error_type, "服务器内部错误"),
            "error_type": error_type,
            "detail": exc_msg[:500],
            "suggestion": suggestion,
        },
    )


# Health check
@app.get("/api/v1/health")
async def health_check():
    from app.repositories.supabase_client import get_supabase_client
    supabase_ok = False
    try:
        client = get_supabase_client()
        if client:
            await client.table("projects").select("id", count="exact").limit(1).execute()
            supabase_ok = True
    except Exception:
        pass
    return {
        "code": 200,
        "data": {
            "backend": "ok",
            "supabase": "connected" if supabase_ok else "disconnected",
            "storage_mode": "dual" if supabase_ok else "local_only",
        },
        "message": "success",
    }


# Register routers
app.include_router(documents.router, prefix="/api/v1")
app.include_router(generation.router, prefix="/api/v1")
app.include_router(testcases.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
