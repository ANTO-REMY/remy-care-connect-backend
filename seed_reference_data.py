#!/usr/bin/env python3
"""
Seed stable reference data used across environments.
"""

from seed_dietary_recommendations import seed_dietary_recommendations
from seed_resources import seed_resources


def seed_reference_data():
    print("Starting reference data seeding...")
    seed_dietary_recommendations()
    seed_resources()
    print("Reference data seeding complete.")


if __name__ == "__main__":
    seed_reference_data()
