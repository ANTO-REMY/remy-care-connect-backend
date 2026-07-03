#!/usr/bin/env python3
"""
One-time Nairobi administrative location enrichment for health facilities.

Expected local boundary files:
  remy-care-connect-backend/data/boundaries/nairobi_wards.geojson
  remy-care-connect-backend/data/boundaries/nairobi_subcounties.geojson

Usage:
  python enrich_health_facilities_admin_locations.py --dry-run
  python enrich_health_facilities_admin_locations.py --commit
  python enrich_health_facilities_admin_locations.py --commit --force
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from app import create_app, db
from models import HealthFacility, SubCounty, Ward


POINT_REGEX = re.compile(r"POINT\(([^ ]+) ([^ ]+)\)")
DEFAULT_STATUS = "manual_review"
VALID_STATUSES = {
    "matched_ward",
    "matched_subcounty_only",
    "missing_coordinates",
    "invalid_coordinates",
    "possible_swapped_coordinates",
    "outside_nairobi",
    "manual_review",
}

WARD_NAME_KEYS = (
    "ward_name",
    "ward",
    "name",
    "ward_nam",
    "wardname",
)
SUBCOUNTY_NAME_KEYS = (
    "subcounty_name",
    "sub_county_name",
    "constituency",
    "constituen",
    "subcounty",
    "sub_county",
    "name",
)


@dataclass
class BoundaryFeature:
    name: str
    subcounty_name: str | None
    geometry: BaseGeometry
    prepared: object


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_boundary_dir = script_dir / "data" / "boundaries"

    parser = argparse.ArgumentParser(description="Enrich facility ward/sub-county from local Nairobi polygons")
    parser.add_argument("--wards", type=Path, default=default_boundary_dir / "nairobi_wards.geojson")
    parser.add_argument("--subcounties", type=Path, default=default_boundary_dir / "nairobi_subcounties.geojson")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting")
    parser.add_argument("--force", action="store_true", help="Recompute rows even when already enriched")
    parser.add_argument("--limit", type=int, help="Optional limit for smoke testing")
    return parser.parse_args()


def parse_wkt_point(geometry_wkt: str | None):
    if not geometry_wkt:
        return None

    match = POINT_REGEX.search(geometry_wkt)
    if not match:
        return None

    try:
        lng = float(match.group(1))
        lat = float(match.group(2))
    except (TypeError, ValueError):
        return None

    return lat, lng


def _normalize_name(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _first_present(properties: dict, keys: tuple[str, ...]) -> str | None:
    lowered = {str(key).lower(): value for key, value in properties.items()}
    for key in keys:
        value = properties.get(key)
        if value is None:
            value = lowered.get(key.lower())
        normalized = _normalize_name(value)
        if normalized:
            return normalized
    return None


def _load_feature_collection(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Boundary file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"Boundary file must be a FeatureCollection: {path}")
    return payload


def _repair_geometry(geom: BaseGeometry) -> BaseGeometry:
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def load_ward_boundaries(path: Path) -> list[BoundaryFeature]:
    payload = _load_feature_collection(path)
    features: list[BoundaryFeature] = []

    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not geometry:
            continue

        ward_name = _first_present(props, WARD_NAME_KEYS)
        subcounty_name = _first_present(props, tuple(k for k in SUBCOUNTY_NAME_KEYS if k != "name")) or _first_present(props, ("const_nam",))
        if not ward_name:
            continue

        geom = _repair_geometry(shape(geometry))
        if geom.is_empty:
            continue

        features.append(
            BoundaryFeature(
                name=ward_name,
                subcounty_name=_normalize_name(subcounty_name),
                geometry=geom,
                prepared=prep(geom),
            )
        )

    if not features:
        raise ValueError(f"No usable ward polygons found in: {path}")
    return features


def load_subcounty_boundaries(path: Path) -> list[BoundaryFeature]:
    payload = _load_feature_collection(path)
    features: list[BoundaryFeature] = []

    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        if not geometry:
            continue

        subcounty_name = _first_present(props, SUBCOUNTY_NAME_KEYS)
        if not subcounty_name:
            continue

        geom = _repair_geometry(shape(geometry))
        if geom.is_empty:
            continue

        features.append(
            BoundaryFeature(
                name=subcounty_name,
                subcounty_name=subcounty_name,
                geometry=geom,
                prepared=prep(geom),
            )
        )

    if not features:
        raise ValueError(f"No usable sub-county polygons found in: {path}")
    return features


def _canonical_subcounty_name(name: str | None, known_subcounties: dict[str, str]) -> str | None:
    normalized = (name or "").strip().lower()
    return known_subcounties.get(normalized) or _normalize_name(name)


def _canonical_ward_name(name: str | None, known_wards: dict[tuple[str, str], str], subcounty_name: str | None) -> str | None:
    ward_name = _normalize_name(name)
    sub_name = _normalize_name(subcounty_name)
    if not ward_name:
        return None
    if not sub_name:
        return ward_name
    return known_wards.get((sub_name.strip().lower(), ward_name.strip().lower())) or ward_name


def _is_lat_valid(lat: float) -> bool:
    return math.isfinite(lat) and -90.0 <= lat <= 90.0


def _is_lng_valid(lng: float) -> bool:
    return math.isfinite(lng) and -180.0 <= lng <= 180.0


def _locate_boundary(point: Point, boundaries: list[BoundaryFeature]) -> BoundaryFeature | None:
    for boundary in boundaries:
        if boundary.prepared.covers(point):
            return boundary
    return None


def classify_facility(
    facility: HealthFacility,
    wards: list[BoundaryFeature],
    subcounties: list[BoundaryFeature],
    known_subcounties: dict[str, str],
    known_wards: dict[tuple[str, str], str],
) -> dict[str, str | None]:
    coords = parse_wkt_point(facility.geometry)
    if not coords:
        return {
            "subcounty_name": None,
            "ward_name": None,
            "location_match_status": "missing_coordinates",
            "location_match_method": "geometry_missing_or_unparseable",
        }

    lat, lng = coords
    if not (_is_lat_valid(lat) and _is_lng_valid(lng)):
        return {
            "subcounty_name": None,
            "ward_name": None,
            "location_match_status": "invalid_coordinates",
            "location_match_method": "coordinates_out_of_range",
        }

    point = Point(lng, lat)
    ward_boundary = _locate_boundary(point, wards)
    if ward_boundary:
        subcounty_name = _canonical_subcounty_name(ward_boundary.subcounty_name, known_subcounties)
        ward_name = _canonical_ward_name(ward_boundary.name, known_wards, subcounty_name)
        return {
            "subcounty_name": subcounty_name,
            "ward_name": ward_name,
            "location_match_status": "matched_ward",
            "location_match_method": "ward_polygon_covers_point",
        }

    subcounty_boundary = _locate_boundary(point, subcounties)
    if subcounty_boundary:
        subcounty_name = _canonical_subcounty_name(subcounty_boundary.name, known_subcounties)
        return {
            "subcounty_name": subcounty_name,
            "ward_name": None,
            "location_match_status": "matched_subcounty_only",
            "location_match_method": "subcounty_polygon_covers_point",
        }

    swapped_point = Point(lat, lng)
    if _is_lat_valid(lng) and _is_lng_valid(lat):
        swapped_ward = _locate_boundary(swapped_point, wards)
        swapped_subcounty = _locate_boundary(swapped_point, subcounties)
        if swapped_ward or swapped_subcounty:
            return {
                "subcounty_name": None,
                "ward_name": None,
                "location_match_status": "possible_swapped_coordinates",
                "location_match_method": "swapped_coordinates_match_nairobi_boundary",
            }

    return {
        "subcounty_name": None,
        "ward_name": None,
        "location_match_status": "outside_nairobi",
        "location_match_method": "no_boundary_contains_point",
    }


def run_enrichment(args: argparse.Namespace) -> None:
    wards = load_ward_boundaries(args.wards.resolve())
    subcounties = load_subcounty_boundaries(args.subcounties.resolve())

    app = create_app()
    with app.app_context():
        known_subcounties = {
            (subcounty.name or "").strip().lower(): subcounty.name
            for subcounty in SubCounty.query.all()
            if subcounty.name
        }
        known_wards = {}
        for ward in Ward.query.all():
            subcounty_name = ward.sub_county.name if ward.sub_county else None
            if ward.name and subcounty_name:
                known_wards[((subcounty_name.strip().lower()), (ward.name.strip().lower()))] = ward.name

        query = HealthFacility.query.order_by(HealthFacility.id)
        if not args.force:
            query = query.filter(
                (HealthFacility.location_match_status.is_(None))
                | (HealthFacility.location_match_status == DEFAULT_STATUS)
            )
        if args.limit:
            query = query.limit(args.limit)

        facilities = query.all()
        counts = {status: 0 for status in VALID_STATUSES}

        for facility in facilities:
            outcome = classify_facility(facility, wards, subcounties, known_subcounties, known_wards)
            facility.subcounty_name = outcome["subcounty_name"]
            facility.ward_name = outcome["ward_name"]
            facility.location_match_status = outcome["location_match_status"] or DEFAULT_STATUS
            facility.location_match_method = outcome["location_match_method"]
            facility.location_matched_at = datetime.now(timezone.utc)
            counts[facility.location_match_status] = counts.get(facility.location_match_status, 0) + 1

        print(f"Facilities evaluated: {len(facilities)}")
        for status in sorted(counts):
            print(f"{status}: {counts[status]}")
        print(f"Mode: {'COMMIT' if args.commit and not args.dry_run else 'DRY RUN'}")

        if args.commit and not args.dry_run:
            db.session.commit()
            print("Changes committed.")
        else:
            db.session.rollback()
            print("Dry run complete. No changes persisted.")


def main() -> None:
    args = parse_args()
    run_enrichment(args)


if __name__ == "__main__":
    main()
