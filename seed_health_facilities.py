#!/usr/bin/env python3
"""
Health Facilities Seeding Script
Loads Kenya health facilities from OpenStreetMap GeoJSON dataset into PostgreSQL
"""

import json
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from models import HealthFacility


def parse_specialities(speciality_string):
    """Parse healthcare:speciality field from OSM data"""
    if not speciality_string or speciality_string == 'null':
        return []
    
    # Split by semicolon and clean up
    specialities = [s.strip() for s in str(speciality_string).split(';') if s.strip()]
    return specialities


def normalize_operator_type(operator_type):
    """Normalize operator:type field"""
    if not operator_type or operator_type == 'null':
        return 'unknown'
    
    operator_type = str(operator_type).lower().strip()
    
    # Map variations to standard types
    mapping = {
        'private': 'private',
        'government': 'government',
        'public': 'government',
        'religious': 'religious',
        'faith_based_organization': 'religious',
        'ngo': 'ngo',
        'cbo': 'cbo',
        'community': 'cbo'
    }
    
    return mapping.get(operator_type, 'unknown')


def seed_facilities(geojson_path=None):
    """
    Load health facilities from GeoJSON file into database
    
    Args:
        geojson_path: Path to GeoJSON file. If None, uses default path.
    """
    app = create_app()
    
    with app.app_context():
        # Default path to GeoJSON file
        if not geojson_path:
            geojson_path = os.path.join(
                os.path.expanduser('~'),
                'Downloads',
                'hotosm_ken_health_facilities_points_geojson',
                'hotosm_ken_health_facilities_points_geojson.geojson'
            )
        
        # Check if file exists
        if not os.path.exists(geojson_path):
            print(f"ERROR: GeoJSON file not found at: {geojson_path}")
            print("\nPlease provide the correct path as an argument:")
            print(f"  python seed_health_facilities.py /path/to/file.geojson")
            return

        print(f"Loading GeoJSON from: {geojson_path}")

        # Load GeoJSON data
        try:
            with open(geojson_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"ERROR loading GeoJSON file: {e}")
            return

        features = data.get('features', [])
        total_features = len(features)

        print(f"Found {total_features} facilities in dataset")
        print("Starting import...\n")
        
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        for idx, feature in enumerate(features, 1):
            try:
                props = feature.get('properties', {})
                geometry = feature.get('geometry', {})
                coords = geometry.get('coordinates', [])
                
                # Validate required fields
                osm_id = props.get('osm_id')
                name = props.get('name')
                
                if not osm_id:
                    print(f"WARNING: Skipping feature {idx}: Missing osm_id")
                    skipped_count += 1
                    continue

                if not name or name == 'null':
                    name = f"Facility {osm_id}"

                if not coords or len(coords) < 2:
                    print(f"WARNING: Skipping {name}: Invalid coordinates")
                    skipped_count += 1
                    continue
                
                # Check if facility already exists
                existing = HealthFacility.query.filter_by(osm_id=osm_id).first()
                if existing:
                    skipped_count += 1
                    if idx % 100 == 0:
                        print(f"[{idx}/{total_features}] Skipped (exists): {name}")
                    continue
                
                # Parse specialities
                specialities = parse_specialities(props.get('healthcare:speciality'))
                
                # Normalize operator type
                operator_type = normalize_operator_type(props.get('operator:type'))
                
                # Create PostGIS geometry string (WKT format)
                lng, lat = coords[0], coords[1]
                geometry_wkt = f"SRID=4326;POINT({lng} {lat})"
                
                # Create facility record
                facility = HealthFacility()
                facility.osm_id = osm_id
                facility.name = name
                facility.amenity = props.get('amenity')
                facility.healthcare = props.get('healthcare')
                facility.healthcare_specialities = specialities
                facility.operator_type = operator_type
                facility.city = props.get('addr:city')
                facility.address = props.get('addr:full')
                facility.geometry = geometry_wkt
                facility.verified = False
                facility.facility_metadata = {
                    'source': 'OpenStreetMap',
                    'osm_type': props.get('osm_type'),
                    'name_en': props.get('name:en'),
                    'name_sw': props.get('name:sw')
                }
                facility.created_at = datetime.now(timezone.utc)

                db.session.add(facility)
                created_count += 1
                
                # Progress update every 100 facilities
                if idx % 100 == 0:
                    print(f"[{idx}/{total_features}] Created: {name}")
                    db.session.commit()

            except Exception as e:
                error_count += 1
                print(f"ERROR processing facility {idx}: {e}")
                db.session.rollback()
                continue

        # Final commit
        try:
            db.session.commit()
        except Exception as e:
            print(f"ERROR committing final batch: {e}")
            db.session.rollback()

        # Summary
        print("\n" + "="*60)
        print("SEEDING COMPLETE!")
        print("="*60)
        print(f"Total facilities in dataset: {total_features}")
        print(f"Created: {created_count}")
        print(f"Skipped (already exist): {skipped_count}")
        print(f"Errors: {error_count}")
        print("="*60)

        # Verify database count
        total_in_db = HealthFacility.query.count()
        print(f"\nTotal facilities in database: {total_in_db}")

        # Show sample facilities by type
        print("\nSample breakdown by amenity:")
        amenity_counts = db.session.query(
            HealthFacility.amenity,
            db.func.count(HealthFacility.id)
        ).group_by(HealthFacility.amenity).order_by(db.func.count(HealthFacility.id).desc()).limit(10).all()
        
        for amenity, count in amenity_counts:
            amenity_name = amenity or 'Unknown'
            print(f"  {amenity_name}: {count}")


if __name__ == '__main__':
    # Allow custom path as command-line argument
    geojson_path = sys.argv[1] if len(sys.argv) > 1 else None
    seed_facilities(geojson_path)
