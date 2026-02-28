#!/bin/bash
# start.sh - Helper script to start Founder OS infrastructure and API

echo "🚀 Starting Founder OS Infrastructure..."

# 1. Start Docker services (PostgreSQL + Redis)
echo "📦 Starting PostgreSQL and Redis via Docker Compose..."
docker compose up -d

# Wait a few seconds for DB to initialize just in case
sleep 3

# 2. Start the FastAPI backend
echo "⚡ Starting the FastAPI server..."
cd apps/api
source .venv/bin/activate
echo "API is now running on http://localhost:8000"
echo "Press Ctrl+C to stop the server."

uvicorn app.main:app --reload --port 8000
