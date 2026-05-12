#!/usr/bin/env bash
# Quick diagnostics: check port conflicts, process health, and optionally fix issues.
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$ROOT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo "═══════════════════════════════════"
echo "  服务诊断 — $(date '+%H:%M:%S')"
echo "═══════════════════════════════════"
echo ""

# Check backend port 8000
echo -n "后端端口 8000: "
BACKEND_PIDS=$(lsof -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$BACKEND_PIDS" ]; then
  BACKEND_CMD=$(ps -p $(echo "$BACKEND_PIDS" | head -1) -o command= 2>/dev/null || echo "unknown")
  echo -e "${GREEN}运行中${NC} (PID: $(echo $BACKEND_PIDS | tr '\n' ' '))"
  echo "  进程: $BACKEND_CMD"
  # Check if it responds
  if curl -s -o /dev/null -w '' "http://localhost:8000/api/v1/health" 2>/dev/null; then
    echo -e "  状态: ${GREEN}健康 ✓${NC}"
  else
    echo -e "  状态: ${RED}无响应 ✗${NC} — 建议重启"
  fi
else
  echo -e "${RED}未运行${NC}"
fi

echo ""

# Check frontend port 5173
echo -n "前端端口 5173: "
FRONTEND_PIDS=$(lsof -iTCP:5173 -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$FRONTEND_PIDS" ]; then
  FRONTEND_CMD=$(ps -p $(echo "$FRONTEND_PIDS" | head -1) -o command= 2>/dev/null || echo "unknown")
  echo -e "${GREEN}运行中${NC} (PID: $(echo $FRONTEND_PIDS | tr '\n' ' '))"
  echo "  进程: $FRONTEND_CMD"
  if curl -s -o /dev/null -w '' "http://localhost:5173/" 2>/dev/null; then
    echo -e "  状态: ${GREEN}健康 ✓${NC}"
  else
    echo -e "  状态: ${RED}无响应 ✗${NC} — 建议重启"
  fi
else
  echo -e "${RED}未运行${NC}"
fi

echo ""

# Check for duplicate Vite processes (exclude npm wrapper — only count node processes)
VITE_NODE_COUNT=$(pgrep -f "node.*vite" 2>/dev/null | wc -l | tr -d ' ')
if [ "$VITE_NODE_COUNT" -gt 1 ]; then
  echo -e "${YELLOW}⚠ 发现 $VITE_NODE_COUNT 个 Vite node 进程（可能有僵尸）${NC}"
  pgrep -fl "node.*vite" 2>/dev/null | while read line; do
    echo "  $line"
  done
fi

# Check for zombie backends (running but not responding)
BACKEND_LISTEN=$(lsof -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null || true)
BACKEND_RESPONDING=false
if [ -n "$BACKEND_LISTEN" ]; then
  curl -s -o /dev/null "http://localhost:8000/api/v1/health" 2>/dev/null && BACKEND_RESPONDING=true || true
fi

# Check for port conflicts on auxiliary ports (multiple LISTEN on same port)
for PORT in 5174 5175; do
  PORT_PIDS=$(lsof -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | wc -l | tr -d ' ')
  if [ "$PORT_PIDS" -gt 0 ]; then
    echo -e "${RED}⚠ 备用端口 $PORT 被占用（${PORT_PIDS}个进程），可能有僵尸 Vite${NC}"
  fi
done

echo ""
echo "═══════════════════════════════════"

# Offer fix if issues found
HAS_ISSUES=false
if [ "$VITE_NODE_COUNT" -gt 1 ]; then
  HAS_ISSUES=true
fi
if [ -n "$(lsof -iTCP:5174 -sTCP:LISTEN -t 2>/dev/null)" ]; then
  HAS_ISSUES=true
fi
if [ -n "$BACKEND_LISTEN" ] && [ "$BACKEND_RESPONDING" = false ]; then
  HAS_ISSUES=true
  echo -e "${RED}⚠ 后端进程运行中但无响应（僵尸进程），建议重启${NC}"
fi

if [ "$HAS_ISSUES" = true ]; then
  echo ""
  echo -e "${YELLOW}发现问题。运行以下命令修复:${NC}"
  echo "  bash $(dirname "$0")/doctor.sh --fix"
  echo ""
fi

# Handle --fix flag
if [ "$1" = "--fix" ]; then
  echo "正在修复..."
  # Kill all Vite processes
  VITE_PIDS=$(pgrep -f "node.*vite" 2>/dev/null || true)
  if [ -n "$VITE_PIDS" ]; then
    echo "终止 Vite 进程: $VITE_PIDS"
    kill -9 $VITE_PIDS 2>/dev/null || true
  fi
  # Kill backend Python processes on 8000
  BACKEND_PIDS=$(lsof -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$BACKEND_PIDS" ]; then
    echo "终止后端进程: $BACKEND_PIDS"
    kill -9 $BACKEND_PIDS 2>/dev/null || true
  fi
  sleep 1
  echo "✓ 已清理。请重新运行 start.sh 启动服务。"
fi
