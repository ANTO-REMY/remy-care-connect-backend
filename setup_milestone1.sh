#!/bin/bash
# Milestone 1: Health Facilities Setup Script
# Automates database setup and data seeding

set -e  # Exit on error

echo "=================================================="
echo "🏥 Milestone 1: Health Facilities Setup"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Database configuration
DB_NAME="${DB_NAME:-remyafya}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "📋 Configuration:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Host: $DB_HOST:$DB_PORT"
echo ""

# Step 1: Check PostgreSQL connection
echo "🔍 Step 1: Checking PostgreSQL connection..."
if psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "SELECT 1;" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ PostgreSQL connection successful${NC}"
else
    echo -e "${RED}❌ Cannot connect to PostgreSQL${NC}"
    echo "Please check your database credentials and ensure PostgreSQL is running."
    exit 1
fi
echo ""

# Step 2: Enable PostGIS extension
echo "🗺️  Step 2: Enabling PostGIS extension..."
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;" > /dev/null 2>&1
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" > /dev/null 2>&1

# Verify PostGIS
POSTGIS_VERSION=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT PostGIS_Version();" 2>/dev/null | xargs)
if [ -n "$POSTGIS_VERSION" ]; then
    echo -e "${GREEN}✅ PostGIS enabled: $POSTGIS_VERSION${NC}"
else
    echo -e "${RED}❌ PostGIS extension not available${NC}"
    echo "Please install PostGIS for your PostgreSQL version."
    exit 1
fi
echo ""

# Step 3: Run migrations
echo "📦 Step 3: Running database migrations..."

if [ -f "migrations/037_create_health_facilities.sql" ]; then
    echo "  Running 037_create_health_facilities.sql..."
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -f migrations/037_create_health_facilities.sql > /dev/null 2>&1
    echo -e "${GREEN}  ✅ Health facilities table created${NC}"
else
    echo -e "${RED}  ❌ Migration file not found: 037_create_health_facilities.sql${NC}"
    exit 1
fi

if [ -f "migrations/038_create_facility_issues.sql" ]; then
    echo "  Running 038_create_facility_issues.sql..."
    psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -f migrations/038_create_facility_issues.sql > /dev/null 2>&1
    echo -e "${GREEN}  ✅ Facility issues table created${NC}"
else
    echo -e "${RED}  ❌ Migration file not found: 038_create_facility_issues.sql${NC}"
    exit 1
fi
echo ""

# Step 4: Check for GeoJSON file
echo "📂 Step 4: Checking for GeoJSON data file..."
GEOJSON_PATH="${GEOJSON_PATH:-$HOME/Downloads/hotosm_ken_health_facilities_points_geojson/hotosm_ken_health_facilities_points_geojson.geojson}"

if [ -f "$GEOJSON_PATH" ]; then
    echo -e "${GREEN}✅ GeoJSON file found: $GEOJSON_PATH${NC}"
else
    echo -e "${YELLOW}⚠️  GeoJSON file not found at default location${NC}"
    echo "Please provide the path to the GeoJSON file:"
    read -p "Path: " CUSTOM_PATH
    if [ -f "$CUSTOM_PATH" ]; then
        GEOJSON_PATH="$CUSTOM_PATH"
        echo -e "${GREEN}✅ Using: $GEOJSON_PATH${NC}"
    else
        echo -e "${RED}❌ File not found: $CUSTOM_PATH${NC}"
        exit 1
    fi
fi
echo ""

# Step 5: Seed facilities data
echo "🌱 Step 5: Seeding health facilities data..."
echo "This may take a few minutes..."
echo ""

if [ -f "seed_health_facilities.py" ]; then
    python seed_health_facilities.py "$GEOJSON_PATH"
    
    # Check if seeding was successful
    FACILITY_COUNT=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM health_facilities;" 2>/dev/null | xargs)
    
    if [ "$FACILITY_COUNT" -gt 0 ]; then
        echo ""
        echo -e "${GREEN}✅ Successfully seeded $FACILITY_COUNT facilities${NC}"
    else
        echo -e "${RED}❌ Seeding failed - no facilities in database${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Seeding script not found: seed_health_facilities.py${NC}"
    exit 1
fi
echo ""

# Step 6: Verify setup
echo "🔍 Step 6: Verifying setup..."

# Check tables exist
TABLES=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('health_facilities', 'facility_issues');" 2>/dev/null | xargs)

if [ "$TABLES" -eq 2 ]; then
    echo -e "${GREEN}✅ All tables created successfully${NC}"
else
    echo -e "${RED}❌ Some tables are missing${NC}"
    exit 1
fi

# Check indexes
INDEXES=$(psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'health_facilities';" 2>/dev/null | xargs)
echo -e "${GREEN}✅ $INDEXES indexes created on health_facilities${NC}"

echo ""
echo "=================================================="
echo -e "${GREEN}🎉 Milestone 1 Setup Complete!${NC}"
echo "=================================================="
echo ""
echo "📊 Summary:"
echo "  • PostGIS enabled"
echo "  • Database tables created"
echo "  • $FACILITY_COUNT facilities loaded"
echo "  • Geospatial indexes created"
echo ""
echo "🚀 Next steps:"
echo "  1. Start the backend server: python wsgi.py"
echo "  2. Test API endpoints (see MILESTONE_1_SETUP_GUIDE.md)"
echo "  3. Proceed to Milestone 2 (Mother Dashboard UI)"
echo ""
echo "📚 Documentation:"
echo "  • Milestone Tracker: HEALTH_FACILITIES_MILESTONES.md"
echo ""
