#!/bin/bash
# Clean cache files and prepare for fresh Docker build

echo "🧹 Cleaning Python cache files..."

# Remove Python cache directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

# Remove virtual environment (if exists)
if [ -d ".venv" ]; then
    echo "Removing .venv directory..."
    rm -rf .venv
fi

# Remove test cache
if [ -d ".pytest_cache" ]; then
    rm -rf .pytest_cache
fi

# Remove coverage files
rm -f .coverage 2>/dev/null || true
if [ -d "htmlcov" ]; then
    rm -rf htmlcov
fi

# Remove log files
rm -f *.log 2>/dev/null || true

# Stop and remove Docker containers and volumes
echo "🐳 Cleaning Docker containers and volumes..."
docker-compose down -v 2>/dev/null || true

# Remove Docker images (optional - uncomment if needed)
# docker rmi remy-care-connect-backend_backend 2>/dev/null || true

echo "✅ Cleanup complete! Ready for fresh build."
echo ""
echo "📋 Next steps:"
echo "  1. docker-compose up --build -d"
echo "  2. docker-compose exec backend python init_db.py"
echo ""
