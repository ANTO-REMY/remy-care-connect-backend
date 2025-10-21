@echo off
REM Clean cache files and prepare for fresh Docker build

echo 🧹 Cleaning Python cache files...

REM Remove Python cache directories
if exist __pycache__ rmdir /s /q __pycache__
if exist routes\__pycache__ rmdir /s /q routes\__pycache__

REM Remove Python compiled files
del /s /q *.pyc 2>nul
del /s /q *.pyo 2>nul

REM Remove virtual environment (if exists)
if exist .venv rmdir /s /q .venv

REM Remove test cache
if exist .pytest_cache rmdir /s /q .pytest_cache

REM Remove coverage files
del /q .coverage 2>nul
if exist htmlcov rmdir /s /q htmlcov

REM Remove log files
del /q *.log 2>nul

REM Stop and remove Docker containers and volumes
echo 🐳 Cleaning Docker containers and volumes...
docker-compose down -v 2>nul

REM Remove Docker images (optional - uncomment if needed)
REM docker rmi remy-care-connect-backend_backend 2>nul

echo ✅ Cleanup complete! Ready for fresh build.
echo.
echo 📋 Next steps:
echo   1. docker-compose up --build -d
echo   2. docker-compose exec backend python init_db.py
echo.

pause
