#!/usr/bin/env python3
"""
Approve a single CHW facility submission and link it to a health facility.

Usage :
  python approve_chw_facility_submission.py --submission-id 1
  python approve_chw_facility_submission.py --submission-id 1 --dry-run
  python approve_chw_facility_submission.py --submission-id 1 --lat -1.2921 --lng 36.8219
  python approve_chw_facility_submission.py --submission-id 1 --link-to-existing-facility-id 884
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from typing import Any, cast

from app import create_app, db
from models import CHW, CHWFacilitySubmission, HealthFacility


PLACEHOLDER_LAT = -1.2921
PLACEHOLDER_LNG = 36.8219
POINT_REGEX = re.compile(r"POINT\(([^ ]+) ([^ ]+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Approve one pending CHW facility submission into health_facilities"
    )
    parser.add_argument("--submission-id", type=int, required=True, help="chw_facility_submissions.id")
    parser.add_argument("--commit", action="store_true", help="Persist changes explicitly. The script also commits by default unless --dry-run is provided.")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting")
    parser.add_argument("--name", help="Optional override for the facility name")
    parser.add_argument("--link-to-existing-facility-id", type=int, help="Resolve the submission to an existing health_facilities.id")
    parser.add_argument("--osm-id", type=int, help="Optional OSM id. If omitted, a unique negative placeholder is generated.")
    parser.add_argument("--lat", type=float, help="Latitude for the facility point")
    parser.add_argument("--lng", type=float, help="Longitude for the facility point")
    parser.add_argument("--geometry-wkt", help="Optional full geometry WKT, e.g. SRID=4326;POINT(36.8219 -1.2921)")
    parser.add_argument("--amenity", help="Facility amenity value")
    parser.add_argument("--healthcare", help="Facility healthcare value")
    parser.add_argument("--speciality", action="append", dest="specialities", help="Repeatable healthcare speciality value")
    parser.add_argument("--operator-type", help="Facility operator type")
    parser.add_argument("--city", help="Facility city")
    parser.add_argument("--address", help="Facility address")
    parser.add_argument("--phone", help="Facility phone")
    parser.add_argument("--email", help="Facility email")
    parser.add_argument("--hours-text", help="Facility operating hours text")
    parser.add_argument("--verified", action="store_true", help="Mark the created facility as verified")
    parser.add_argument("--allow-name-duplicate", action="store_true", help="Allow creating a new facility even if one with the same normalized name already exists in the same sub-county")
    return parser.parse_args()


def should_commit(args: argparse.Namespace) -> bool:
    return not args.dry_run


def normalize_facility_name(value: str | None) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_geometry_wkt(geometry_wkt: str | None) -> tuple[float | None, float | None]:
    if not geometry_wkt:
        return None, None

    match = POINT_REGEX.search(geometry_wkt)
    if not match:
        return None, None

    try:
        lng = float(match.group(1))
        lat = float(match.group(2))
    except (TypeError, ValueError):
        return None, None

    return lat, lng


def build_geometry_wkt(args: argparse.Namespace) -> tuple[str, bool, float, float]:
    if args.geometry_wkt:
        lat, lng = parse_geometry_wkt(args.geometry_wkt)
        if lat is None or lng is None:
            raise ValueError("Invalid --geometry-wkt. Expected something like SRID=4326;POINT(36.8219 -1.2921)")
        return args.geometry_wkt, False, lat, lng

    if (args.lat is None) ^ (args.lng is None):
        raise ValueError("Provide both --lat and --lng together")

    if args.lat is not None and args.lng is not None:
        return f"SRID=4326;POINT({args.lng} {args.lat})", False, args.lat, args.lng

    return (
        f"SRID=4326;POINT({PLACEHOLDER_LNG} {PLACEHOLDER_LAT})",
        True,
        PLACEHOLDER_LAT,
        PLACEHOLDER_LNG,
    )


def generate_placeholder_osm_id() -> int:
    candidate = -int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    while HealthFacility.query.filter_by(osm_id=candidate).first():
        candidate -= 1
    return candidate


def find_same_subcounty_name_match(submission: CHWFacilitySubmission, normalized_name: str) -> HealthFacility | None:
    if not normalized_name:
        return None

    facilities = (
        HealthFacility.query
        .filter(HealthFacility.inferred_sub_county_id == submission.sub_county_id)
        .all()
    )
    for facility in facilities:
        if normalize_facility_name(facility.name) == normalized_name:
            return facility
    return None


def build_metadata(
    submission: CHWFacilitySubmission,
    args: argparse.Namespace,
    used_placeholder_osm: bool,
    used_placeholder_geometry: bool,
    lat: float,
    lng: float,
) -> dict:
    return {
        "source": "chw_submission_manual_approval",
        "submission_id": submission.id,
        "submission_status_before_approval": submission.status,
        "submitted_facility_name": submission.facility_name,
        "submitted_by_user_id": submission.submitted_by_user_id,
        "submitted_chw_id": submission.chw_id,
        "submitted_ward_id": submission.ward_id,
        "submitted_sub_county_id": submission.sub_county_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "used_placeholder_osm_id": used_placeholder_osm,
        "used_placeholder_geometry": used_placeholder_geometry,
        "placeholder_geometry_coordinates": {
            "lat": lat,
            "lng": lng,
        } if used_placeholder_geometry else None,
        "manual_inputs": {
            "amenity": args.amenity,
            "healthcare": args.healthcare,
            "specialities": args.specialities or [],
            "operator_type": args.operator_type,
            "city": args.city,
            "address": args.address,
            "phone": args.phone,
            "email": args.email,
            "hours_text": args.hours_text,
            "verified": args.verified,
        },
    }


def print_submission_summary(submission: CHWFacilitySubmission) -> None:
    print(f"Submission ID: {submission.id}")
    print(f"Status: {submission.status}")
    print(f"Submitted facility: {submission.facility_name}")
    print(f"CHW ID: {submission.chw_id}")
    print(f"Ward: {submission.ward.name if submission.ward else submission.ward_id}")
    print(f"Sub-county: {submission.sub_county.name if submission.sub_county else submission.sub_county_id}")


def print_execution_mode(commit_changes: bool) -> None:
    print(f"Mode: {'commit' if commit_changes else 'dry-run'}")


def approve_with_existing_facility(submission: CHWFacilitySubmission, facility: HealthFacility) -> None:
    submission.status = "approved"
    submission.matched_health_facility_id = facility.id

    chw = cast(Any, submission.chw)
    if not chw and submission.chw_id:
        chw = cast(Any, db.session.get(CHW, submission.chw_id))
    if not chw:
        chw = cast(Any, (
            CHW.query
            .filter(CHW.pending_facility_submission_id == submission.id)
            .first()
        ))

    if chw:
        chw.linked_facility_id = facility.id
        chw.pending_facility_submission_id = None


def build_new_facility(
    submission: CHWFacilitySubmission,
    args: argparse.Namespace,
) -> HealthFacility:
    facility_name = (args.name or submission.facility_name or "").strip()
    if not facility_name:
        raise ValueError("Facility name cannot be empty")

    normalized_name = normalize_facility_name(facility_name)
    existing_name_match = find_same_subcounty_name_match(submission, normalized_name)

    geometry_wkt, used_placeholder_geometry, lat, lng = build_geometry_wkt(args)
    osm_id = args.osm_id if args.osm_id is not None else generate_placeholder_osm_id()
    used_placeholder_osm = args.osm_id is None

    if HealthFacility.query.filter_by(osm_id=osm_id).first():
        raise ValueError(f"osm_id {osm_id} already exists in health_facilities")

    facility = HealthFacility()
    facility.osm_id = osm_id
    facility.name = facility_name
    facility.amenity = args.amenity
    facility.healthcare = args.healthcare
    facility.healthcare_specialities = args.specialities or []
    facility.operator_type = args.operator_type
    facility.city = args.city
    facility.address = args.address
    facility.geometry = geometry_wkt
    facility.inferred_ward_id = submission.ward_id
    facility.inferred_sub_county_id = submission.sub_county_id
    facility.inference_source = "chw_submission_manual_approval"
    facility.inference_confidence = 1.0
    facility.location_quality_status = "unknown"
    facility.subcounty_name = submission.sub_county.name if submission.sub_county else None
    facility.ward_name = submission.ward.name if submission.ward else None
    facility.location_match_status = "manual_review"
    facility.location_match_method = "chw_submission_manual_approval"
    facility.location_matched_at = datetime.now(timezone.utc)
    facility.is_in_nairobi = True
    facility.nairobi_scope_source = "chw_submission_manual_approval"
    facility.near_nairobi_boundary = False
    facility.verified = args.verified
    facility.verified_at = datetime.now(timezone.utc) if args.verified else None
    facility.phone = args.phone
    facility.email = args.email
    facility.hours_text = args.hours_text
    facility.facility_metadata = build_metadata(
        submission=submission,
        args=args,
        used_placeholder_osm=used_placeholder_osm,
        used_placeholder_geometry=used_placeholder_geometry,
        lat=lat,
        lng=lng,
    )
    if existing_name_match:
        facility.facility_metadata["possible_existing_name_match"] = {
            "facility_id": existing_name_match.id,
            "facility_name": existing_name_match.name,
        }
    return facility


def main() -> None:
    args = parse_args()
    commit_changes = should_commit(args)
    app = create_app()

    with app.app_context():
        submission = (
            CHWFacilitySubmission.query
            .filter(CHWFacilitySubmission.id == args.submission_id)
            .first()
        )
        if not submission:
            raise SystemExit(f"Submission {args.submission_id} was not found")

        if submission.status != "pending":
            raise SystemExit(
                f"Submission {submission.id} is {submission.status!r}. "
                "This script only approves pending submissions."
            )

        print_submission_summary(submission)
        print_execution_mode(commit_changes)

        chw = submission.chw
        if chw and chw.linked_facility_id:
            linked = db.session.get(HealthFacility, chw.linked_facility_id)
            raise SystemExit(
                f"CHW {chw.id} already has linked_facility_id={chw.linked_facility_id} "
                f"({linked.name if linked else 'unknown'}). Resolve that link before approving this submission."
            )

        facility: HealthFacility | None = None
        created_new_facility = False

        try:
            if args.link_to_existing_facility_id:
                facility = db.session.get(HealthFacility, args.link_to_existing_facility_id)
                if not facility:
                    raise ValueError(
                        f"Existing facility {args.link_to_existing_facility_id} was not found"
                )
                approve_with_existing_facility(submission, facility)
            else:
                facility = build_new_facility(submission, args)
                db.session.add(facility)
                db.session.flush()
                created_new_facility = True
                approve_with_existing_facility(submission, facility)

            db.session.flush()

            print("")
            print("Approval preview:")
            print(f"Resolved facility ID: {facility.id}")
            print(f"Resolved facility name: {facility.name}")
            print(f"Created new facility: {'yes' if created_new_facility else 'no'}")
            print(f"Submission new status: {submission.status}")
            print(f"Submission matched_health_facility_id: {submission.matched_health_facility_id}")
            if chw:
                print(f"CHW linked_facility_id: {chw.linked_facility_id}")
                print(f"CHW pending_facility_submission_id: {chw.pending_facility_submission_id}")

            if commit_changes:
                db.session.commit()
                print("")
                print("Changes committed.")
            else:
                db.session.rollback()
                print("")
                print("Dry run complete. No changes persisted.")

        except Exception as exc:
            db.session.rollback()
            raise SystemExit(f"Approval failed: {exc}") from exc


if __name__ == "__main__":
    main()
