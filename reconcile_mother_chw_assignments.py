#!/usr/bin/env python3
"""
Repair mother-CHW assignments using ward-based automatic matching.

Usage:
  python reconcile_mother_chw_assignments.py --dry-run
  python reconcile_mother_chw_assignments.py --commit
"""

from __future__ import annotations

import argparse

from sqlalchemy import func

from app import create_app, db
from assignment_utils import ASSIGNMENT_METHOD_AUTO_WARD_MATCH, assign_mother_if_possible
from models import Mother
from models_standard import MotherCHWAssignment


def parse_args():
    parser = argparse.ArgumentParser(description="Repair mother-CHW assignments from ward-based rules")
    parser.add_argument("--commit", action="store_true", help="Persist assignment repairs")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting")
    parser.add_argument("--limit", type=int, help="Optional limit for smoke testing")
    return parser.parse_args()


def get_duplicate_active_mothers():
    return (
        db.session.query(MotherCHWAssignment.mother_id, func.count(MotherCHWAssignment.id))
        .filter(MotherCHWAssignment.status == 'active')
        .group_by(MotherCHWAssignment.mother_id)
        .having(func.count(MotherCHWAssignment.id) > 1)
        .all()
    )


def main():
    args = parse_args()
    app = create_app()

    with app.app_context():
        active_mother_ids_subquery = (
            db.session.query(MotherCHWAssignment.mother_id)
            .filter(MotherCHWAssignment.status == 'active')
        )
        query = (
            Mother.query
            .filter(Mother.ward_id.isnot(None))
            .filter(~Mother.id.in_(active_mother_ids_subquery))
            .order_by(Mother.created_at.asc(), Mother.id.asc())
        )
        if args.limit:
            query = query.limit(args.limit)

        unassigned_mothers = query.all()
        created = 0
        still_unassigned = 0

        for mother in unassigned_mothers:
            assignment, changed = assign_mother_if_possible(
                mother.id,
                assignment_method=ASSIGNMENT_METHOD_AUTO_WARD_MATCH,
            )
            if changed and assignment:
                created += 1
            else:
                still_unassigned += 1

        duplicate_active = get_duplicate_active_mothers()

        print(f"Unassigned mothers scanned: {len(unassigned_mothers)}")
        print(f"Assignments created/reactivated: {created}")
        print(f"Still unassigned: {still_unassigned}")
        print(f"Mothers with duplicate active assignments: {len(duplicate_active)}")

        if args.commit and not args.dry_run:
            db.session.commit()
            print("Changes committed.")
        else:
            db.session.rollback()
            print("Dry run complete. No changes persisted.")


if __name__ == "__main__":
    main()
