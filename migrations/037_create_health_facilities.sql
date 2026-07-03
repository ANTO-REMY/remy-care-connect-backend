-- Migration 037: Create health_facilities table with PostGIS geospatial support
-- Purpose: Store Kenya health facilities from OpenStreetMap dataset
-- Date: 2026-04-14

-- Enable PostGIS extension if not already enabled
CREATE EXTENSION IF NOT EXISTS postgis;

-- Health Facilities table
CREATE TABLE IF NOT EXISTS health_facilities (
    id SERIAL PRIMARY KEY,
    osm_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    
    -- Facility type classification
    amenity VARCHAR(50),                           -- pharmacy, clinic, hospital, dentist, blood_bank
    healthcare VARCHAR(255),                       -- clinic, pharmacy, hospital, laboratory (semicolon-separated, can be long)
    healthcare_specialities TEXT[] DEFAULT '{}',   -- {maternity, gynaecology, paediatrics}
    operator_type VARCHAR(50),                     -- private, government, religious, ngo, cbo
    
    -- Location information
    city VARCHAR(100),
    address TEXT,
    geometry GEOGRAPHY(POINT, 4326) NOT NULL,      -- PostGIS geography type (lat/lng)
    
    -- Verification status
    verified BOOLEAN DEFAULT FALSE,                -- Facility verified by admin or staff
    verified_by BIGINT REFERENCES users(id),       -- User who verified (facility manager)
    verified_at TIMESTAMP,
    
    -- Extensible metadata (renamed to facility_metadata to avoid SQL reserved keywords)
    facility_metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- Geospatial index for distance queries (critical for performance)
CREATE INDEX idx_hf_geom ON health_facilities USING GIST(geometry);

-- Standard indexes
CREATE INDEX idx_hf_osm_id ON health_facilities(osm_id);
CREATE INDEX idx_hf_amenity ON health_facilities(amenity);
CREATE INDEX idx_hf_healthcare ON health_facilities(healthcare);
CREATE INDEX idx_hf_verified ON health_facilities(verified);
CREATE INDEX idx_hf_city ON health_facilities(city);
CREATE INDEX idx_hf_operator_type ON health_facilities(operator_type);

-- Full-text search index on facility name
CREATE INDEX idx_hf_name_trgm ON health_facilities USING gin(name gin_trgm_ops);

-- Enable trigram extension for fuzzy name search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Comments for documentation
COMMENT ON TABLE health_facilities IS 'Kenya health facilities from OpenStreetMap dataset';
COMMENT ON COLUMN health_facilities.osm_id IS 'OpenStreetMap unique identifier';
COMMENT ON COLUMN health_facilities.geometry IS 'PostGIS geography point (SRID 4326 - WGS84)';
COMMENT ON COLUMN health_facilities.facility_metadata IS 'Extensible JSON field for hours, contact info, etc.';
