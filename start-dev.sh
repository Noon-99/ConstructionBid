#!/bin/bash
# Quick start script for Phase 6.1 development

echo "Starting Construction Bid AI Development Servers..."
echo ""

# Start backend in background
echo "Starting backend on port 8000..."
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 2

# Start frontend
echo "Starting frontend on port 3000..."
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Servers starting..."
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo ""
echo "Logs:"
echo "   Backend:  tail -f backend.log"
echo "   Frontend: tail -f frontend.log"
echo ""
echo "To stop: kill $BACKEND_PID $FRONTEND_PID"






