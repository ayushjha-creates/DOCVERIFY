#!/bin/bash
echo "================================================"
echo "  DOCVERIFY AI - Document Authenticity Verifier"
echo "================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

cleanup() {
    echo ""
    echo "Shutting down servers..."
    lsof -i :8000 2>/dev/null | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null
    lsof -i :3000 2>/dev/null | grep LISTEN | awk '{print $2}' | xargs kill -9 2>/dev/null
    echo "Servers stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "[1/4] Cleaning temp files..."
rm -rf "$BACKEND_DIR/temp/"* "$BACKEND_DIR/reports/"*

echo "[2/4] Starting Backend (FastAPI on :8000)..."
cd "$BACKEND_DIR"
python3 main.py &
BACKEND_PID=$!
sleep 2

if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "  ✓ Backend running on http://localhost:8000"
else
    echo "  ✗ Backend failed to start"
    exit 1
fi

echo "[3/4] Starting Frontend (Next.js on :3000)..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!
sleep 5

if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "  ✓ Frontend running on http://localhost:3000"
else
    echo "  ✗ Frontend failed to start"
    exit 1
fi

echo ""
echo "[4/4] Checking API connectivity..."
if curl -s -X POST http://localhost:8000/api/analyze \
  -F "file=@$BACKEND_DIR/sample/sample_certificate.pdf" > /dev/null 2>&1; then
    echo "  ✓ API analysis pipeline working"
else
    echo "  ✗ API test failed"
fi

echo ""
echo "================================================"
echo "  Application is ready!"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "================================================"
echo "  Press Ctrl+C to stop all servers"
echo "================================================"

wait $BACKEND_PID $FRONTEND_PID
