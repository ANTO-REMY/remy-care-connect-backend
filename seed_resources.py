#!/usr/bin/env python3
"""
Seed resources for RemyCareConnect's Resources feature.
Run this after database setup to populate or refresh stable resource data.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, Resource


def _resource_seed_data():
    return [
        {
            "title": "Managing Morning Sickness",
            "description": "Evidence-based tips for reducing nausea during pregnancy. Learn about safe remedies and when to seek medical help.",
            "category": "Pregnancy",
            "target_role": "mother",
            "content_type": "article",
            "url": "https://www.mayoclinic.org/diseases-conditions/morning-sickness/symptoms-causes/syc-20375254",
            "thumbnail": "🤰",
        },
        {
            "title": "Breastfeeding Your Baby",
            "description": "WHO's comprehensive guide to breastfeeding, including positioning, common challenges, and nutritional benefits.",
            "category": "Baby Care",
            "target_role": "mother",
            "content_type": "pdf",
            "url": "https://www.who.int/publications/i/item/9789241550086",
            "thumbnail": "🤱",
        },
        {
            "title": "Postpartum Mental Health",
            "description": "Recognizing signs of postpartum depression and anxiety. Resources for getting help and supporting recovery.",
            "category": "Wellness",
            "target_role": "mother",
            "content_type": "article",
            "url": "https://www.cdc.gov/reproductivehealth/depression/index.htm",
            "thumbnail": "💙",
        },
        {
            "title": "Safe Sleep for Your Baby",
            "description": "UNICEF's guidelines on creating a safe sleep environment to reduce the risk of SIDS and sleep-related deaths.",
            "category": "Baby Care",
            "target_role": "mother",
            "content_type": "video",
            "url": "https://www.unicef.org/parenting/child-care/safe-sleep",
            "thumbnail": "👶",
        },
        {
            "title": "Nutrition During Pregnancy",
            "description": "Essential nutrients for a healthy pregnancy, meal planning tips, and foods to avoid during pregnancy.",
            "category": "Pregnancy",
            "target_role": "mother",
            "content_type": "article",
            "url": "https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
            "thumbnail": "🥗",
        },
        {
            "title": "Community Health Emergency Response",
            "description": "WHO protocols for CHWs responding to maternal health emergencies in community settings.",
            "category": "Emergency Response",
            "target_role": "chw",
            "content_type": "pdf",
            "url": "https://www.who.int/publications/i/item/9789241548953",
            "thumbnail": "🚨",
        },
        {
            "title": "Maternal Health Field Assessment",
            "description": "Standardized tools and checklists for assessing pregnant women in community health visits.",
            "category": "Field Protocols",
            "target_role": "chw",
            "content_type": "article",
            "url": "https://www.who.int/maternal_child_adolescent/documents/imci_chartbooklet/en/",
            "thumbnail": "📋",
        },
        {
            "title": "Immunization Schedule and Record Keeping",
            "description": "CDC guidelines for maintaining accurate immunization records and following vaccination schedules.",
            "category": "Immunization",
            "target_role": "chw",
            "content_type": "pdf",
            "url": "https://www.cdc.gov/vaccines/schedules/hcp/imz/child-adolescent.html",
            "thumbnail": "💉",
        },
        {
            "title": "Identifying Signs of Preterm Labor",
            "description": "Field guide for CHWs to recognize early warning signs of preterm labor and appropriate referral protocols.",
            "category": "Field Protocols",
            "target_role": "chw",
            "content_type": "video",
            "url": "https://www.who.int/news-room/fact-sheets/detail/preterm-birth",
            "thumbnail": "⚡",
        },
        {
            "title": "Community Health Data Collection",
            "description": "Best practices for collecting and reporting health data in community settings for maternal and child health programs.",
            "category": "Data Management",
            "target_role": "chw",
            "content_type": "article",
            "url": "https://www.who.int/healthinfo/systems/WHO_MBHSS_2010_full_web.pdf",
            "thumbnail": "📊",
        },
        {
            "title": "Obstetric Triage Guidelines",
            "description": "Clinical protocols for rapid assessment and prioritization of pregnant patients in emergency and clinic settings.",
            "category": "Triage",
            "target_role": "nurse",
            "content_type": "pdf",
            "url": "https://www.who.int/publications/i/item/managing-complications-in-pregnancy-and-childbirth",
            "thumbnail": "🏥",
        },
        {
            "title": "Medication Safety in Pregnancy",
            "description": "CDC guidelines on safe medication use during pregnancy and lactation, including contraindicated drugs.",
            "category": "Clinical Guidelines",
            "target_role": "nurse",
            "content_type": "article",
            "url": "https://www.cdc.gov/pregnancy/meds/treatingfortwo/index.html",
            "thumbnail": "💊",
        },
        {
            "title": "Postpartum Hemorrhage Management",
            "description": "WHO clinical protocols for prevention and management of postpartum hemorrhage in healthcare facilities.",
            "category": "Emergency Care",
            "target_role": "nurse",
            "content_type": "video",
            "url": "https://www.who.int/publications/i/item/who-recommendation-on-tranexamic-acid-for-the-treatment-of-postpartum-haemorrhage",
            "thumbnail": "⛑️",
        },
        {
            "title": "Antenatal Care Standards",
            "description": "Evidence-based guidelines for providing quality antenatal care, including screening schedules and interventions.",
            "category": "Clinical Guidelines",
            "target_role": "nurse",
            "content_type": "pdf",
            "url": "https://www.who.int/publications/i/item/9789241549912",
            "thumbnail": "🩺",
        },
        {
            "title": "Infection Prevention in Maternity Care",
            "description": "WHO standards for preventing healthcare-associated infections in maternity and newborn care settings.",
            "category": "Clinical Guidelines",
            "target_role": "nurse",
            "content_type": "article",
            "url": "https://www.who.int/publications/i/item/prevention-and-control-of-healthcare-associated-infections-in-maternity-and-newborn-care-settings",
            "thumbnail": "🧼",
        },
    ]


def seed_resources():
    app = create_app()

    with app.app_context():
        print("Seeding resources for RemyCareConnect...")

        created_count = 0
        updated_count = 0

        for data in _resource_seed_data():
            try:
                now = datetime.now(timezone.utc)
                resource = Resource.query.filter_by(
                    title=data["title"],
                    target_role=data["target_role"],
                ).first()

                if resource is None:
                    resource = Resource(
                        title=data["title"],
                        target_role=data["target_role"],
                        created_at=now,
                    )
                    created_count += 1
                    action = "Created"
                else:
                    updated_count += 1
                    action = "Updated"

                resource.description = data["description"]
                resource.category = data["category"]
                resource.content_type = data["content_type"]
                resource.url = data["url"]
                resource.thumbnail = data["thumbnail"]

                db.session.add(resource)
                print(f"{action}: {data['title']} ({data['target_role']})")
            except Exception as e:
                db.session.rollback()
                print(f"Failed to upsert resource '{data['title']}': {e}")
                continue

        try:
            db.session.commit()
            print("\nResources seeding completed.")
            print(f"Created: {created_count}")
            print(f"Updated: {updated_count}")
        except Exception as e:
            db.session.rollback()
            print(f"Failed to commit resources: {e}")


if __name__ == "__main__":
    seed_resources()
