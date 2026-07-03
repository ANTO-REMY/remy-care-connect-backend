@echo off
REM Milestone 1: Health Facilities Setup Script (Windows)
REM Automates database setup and data seeding

echo ==================================================
echo 🏥 Milestone 1: Health Facilities Setup
echo ==================================================
echo.

REM Database configuration
set DB_NAME=remyafya
set DB_USER=postgres
set DB_HOST=localhost
set DB_PORT=5432

echo 📋 Configuration:
echo   Database: %DB_NAME%
echo   User: %DB_USER%
echo   Host: %DB_HOST%:%DB_PORT%
echo.

REM Step 1: Check PostgreSQL connection
echo 🔍 Step 1: Checking PostgreSQL connection...
psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -c "SELECT 1;" >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ PostgreSQL connection successful
) else (
    echo ❌ Cannot connect to PostgreSQL
    echo Please check your database credentials and ensure PostgreSQL is running.
    exit /b 1
)
echo.

REM Step 2: Enable PostGIS extension
echo 🗺️  Step 2: Enabling PostGIS extension...
psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -c "CREATE EXTENSION IF NOT EXISTS postgis;" >nul 2>&1
psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" >nul 2>&1

REM Verify PostGIS
psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -t -c "SELECT PostGIS_Version();" >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ PostGIS enabled
) else (
    echo ❌ PostGIS extension not available
    echo Please install PostGIS for your PostgreSQL version.
    exit /b 1
)
echo.

REM Step 3: Run migrations
echo 📦 Step 3: Running database migrations...

if exist "migrations\037_create_health_facilities.sql" (
    echo   Running 037_create_health_facilities.sql...
    psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -f migrations\037_create_health_facilities.sql >nul 2>&1
    echo   ✅ Health facilities table created
) else (
    echo   ❌ Migration file not found: 037_create_health_facilities.sql
    exit /b 1
)

if exist "migrations\038_create_facility_issues.sql" (
    echo   Running 038_create_facility_issues.sql...
    psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -f migrations\038_create_facility_issues.sql >nul 2>&1
    echo   ✅ Facility issues table created
) else (
    echo   ❌ Migration file not found: 038_create_facility_issues.sql
    exit /b 1
)
echo.

REM Step 4: Check for GeoJSON file
echo 📂 Step 4: Checking for GeoJSON data file...
set GEOJSON_PATH=%USERPROFILE%\Downloads\hotosm_ken_health_facilities_points_geojson\hotosm_ken_health_facilities_points_geojson.geojson

if exist "%GEOJSON_PATH%" (
    echo ✅ GeoJSON file found
) else (
    echo ⚠️  GeoJSON file not found at default location
    echo Please provide the full path to the GeoJSON file:
    set /p GEOJSON_PATH="Path: "
    if not exist "%GEOJSON_PATH%" (
        echo ❌ File not found: %GEOJSON_PATH%
        exit /b 1
    )
)
echo.

REM Step 5: Seed facilities data
echo 🌱 Step 5: Seeding health facilities data...
echo This may take a few minutes...
echo.

if exist "seed_health_facilities.py" (
    python seed_health_facilities.py "%GEOJSON_PATH%"
    
    if %errorlevel% equ 0 (
        echo.
        echo ✅ Seeding completed successfully
    ) else (
        echo ❌ Seeding failed
        exit /b 1
    )
) else (
    echo ❌ Seeding script not found: seed_health_facilities.py
    exit /b 1
)
echo.

REM Step 6: Verify setup
echo 🔍 Step 6: Verifying setup...

REM Check facility count
for /f %%i in ('psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -t -c "SELECT COUNT(*) FROM health_facilities;" 2^>nul') do set FACILITY_COUNT=%%i

if %FACILITY_COUNT% gtr 0 (
    echo ✅ %FACILITY_COUNT% facilities in database
) else (
    echo ❌ No facilities found in database
    exit /b 1
)

echo.
echo ==================================================
echo 🎉 Milestone 1 Setup Complete!
echo ==================================================
echo.
echo 📊 Summary:
echo   • PostGIS enabled
echo   • Database tables created
echo   • %FACILITY_COUNT% facilities loaded
echo   • Geospatial indexes created
echo.
echo 🚀 Next steps:
echo   1. Start the backend server: python wsgi.py
echo   2. Test API endpoints (see MILESTONE_1_SETUP_GUIDE.md)
echo   3. Proceed to Milestone 2 (Mother Dashboard UI)
echo.
echo 📚 Documentation:
echo   • Milestone Tracker: HEALTH_FACILITIES_MILESTONES.md
echo.

pause
