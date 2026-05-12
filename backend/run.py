"""Start the backend server with automatic port finding."""
import socket
import sys
import uvicorn

BASE_PORT = 8000
MAX_ATTEMPTS = 20


def find_free_port(start: int = BASE_PORT, max_attempts: int = MAX_ATTEMPTS) -> int:
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    print(f"错误：{start}-{start + max_attempts} 范围内无可用端口")
    sys.exit(1)


if __name__ == "__main__":
    port = find_free_port()
    if port != BASE_PORT:
        print(f"端口 {BASE_PORT} 已被占用，自动切换至端口 {port}")
    print(f"后端启动地址: http://localhost:{port}")
    print(f"健康检查:     http://localhost:{port}/api/v1/health\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True)
