#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# ── 0. 端口冲突预防：清理占用目标端口的旧进程 ──
kill_port_process() {
  local port=$1
  local label=$2
  local pids=$(lsof -iTCP:$port -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "⚠ 端口 $port 已被占用 ($label)，正在终止旧进程: $pids"
    kill -9 $pids 2>/dev/null || true
    sleep 1
    # 二次确认
    if lsof -iTCP:$port -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "❌ 端口 $port 无法释放，请手动检查"
      exit 1
    fi
    echo "✓ 端口 $port 已释放"
  fi
}

kill_port_process 8000 "后端"
kill_port_process 5173 "前端"

cleanup() {
  echo ""
  echo "正在关闭服务..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  echo "已关闭"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── 1. 查找后端可用端口 ──
find_free_port() {
  local port=$1
  while [ $port -lt $(($1 + 20)) ]; do
    if ! lsof -iTCP:$port -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo $port
      return
    fi
    port=$((port + 1))
  done
  echo ""
}

BACKEND_PORT=$(find_free_port 8000)
if [ -z "$BACKEND_PORT" ]; then
  echo "错误：8000-8019 范围内无可用端口"
  exit 1
fi

# ── 2. 启动后端 ──
echo "═══════════════════════════════════"
echo "  启动后端 (端口 $BACKEND_PORT)..."
echo "═══════════════════════════════════"

cd "$BACKEND_DIR"
source venv/bin/activate 2>/dev/null || true
python -c "import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=$BACKEND_PORT, log_level='warning')" &
BACKEND_PID=$!

# 等待后端就绪
echo -n "  等待后端就绪"
for i in $(seq 1 30); do
  if curl -s "http://localhost:$BACKEND_PORT/api/v1/health" >/dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 0.5
done
echo ""

# ── 3. 启动前端 ──
echo "═══════════════════════════════════"
echo "  启动前端..."
echo "═══════════════════════════════════"

cd "$FRONTEND_DIR"
VITE_BACKEND_PORT=$BACKEND_PORT npm run dev -- --host 2>&1 &
FRONTEND_PID=$!

# 等待前端就绪，从输出中提取实际端口
FRONTEND_PORT=""
echo -n "  等待前端就绪"
for i in $(seq 1 30); do
  FRONTEND_PORT=$(lsof -iTCP -sTCP:LISTEN -t -p $FRONTEND_PID 2>/dev/null | head -1 | xargs lsof -p 2>/dev/null | grep LISTEN | grep -o 'localhost:[0-9]*' | grep -o '[0-9]*$' | head -1)
  if [ -n "$FRONTEND_PORT" ]; then
    echo " ✓"
    break
  fi
  sleep 0.5
  echo -n "."
done
echo ""

FRONTEND_URL="http://localhost:${FRONTEND_PORT:-5173}"

echo ""
echo "═══════════════════════════════════"
echo "  系统已启动"
echo "═══════════════════════════════════"
echo ""
echo "  前端地址:  $FRONTEND_URL"
echo "  后端地址:  http://localhost:$BACKEND_PORT"
echo "  API 文档:  http://localhost:$BACKEND_PORT/docs"
echo ""
echo "  按 Ctrl+C 关闭所有服务"
echo "═══════════════════════════════════"

# 自动打开浏览器
sleep 0.5
open "$FRONTEND_URL" 2>/dev/null || true

# 等待任意子进程退出或 Ctrl+C
wait
