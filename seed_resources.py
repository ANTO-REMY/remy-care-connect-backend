#!/usr/bin/env python3
"""
Seed resources for RemyCareConnect's Resources feature.
Run this after database setup to populate with realistic health resources.
"""
import os
import sys
from datetime import datetime, timezone

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, Resource

def seed_resources():
    app = create_app()
    
    with app.app_context():
        print("🚀 Seeding resources for RemyCareConnect...")
        
        resources_data = [
            # ─── MOTHER RESOURCES (5) ───────────────────────────────────
            {
                "title": "Managing Morning Sickness",
                "description": "Evidence-based tips for reducing nausea during pregnancy. Learn about safe remedies and when to seek medical help.",
                "category": "Pregnancy",
                "target_role": "mother",
                "content_type": "article",
                "url": "https://www.mayoclinic.org/diseases-conditions/morning-sickness/symptoms-causes/syc-20375254",
                "thumbnail": "🤰"
            },
            {
                "title": "Breastfeeding Your Baby",
                "description": "WHO's comprehensive guide to breastfeeding, including positioning, common challenges, and nutritional benefits.",
                "category": "Baby Care",
                "target_role": "mother",
                "content_type": "pdf",
                "url": "https://www.who.int/publications/i/item/9789241550086",
                "thumbnail": "🤱"
            },
            {
                "title": "Postpartum Mental Health",
                "description": "Recognizing signs of postpartum depression and anxiety. Resources for getting help and supporting recovery.",
                "category": "Wellness",
                "target_role": "mother",
                "content_type": "article",
                "url": "https://www.cdc.gov/reproductivehealth/depression/index.htm",
                "thumbnail": "💙"
            },
            {
                "title": "Safe Sleep for Your Baby",
                "description": "UNICEF's guidelines on creating a safe sleep environment to reduce the risk of SIDS and sleep-related deaths.",
                "category": "Baby Care",
                "target_role": "mother",
                "content_type": "video",
                "url": "https://www.unicef.org/parenting/child-care/safe-sleep",
                "thumbnail": "👶"
            },
            {
                "title": "Nutrition During Pregnancy",
                "description": "Essential nutrients for a healthy pregnancy, meal planning tips, and foods to avoid during pregnancy.",
                "category": "Pregnancy",
                "target_role": "mother",
                "content_type": "article",
                "url": "https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
                "thumbnail": "🥗"
            },
            
            # ─── CHW RESOURCES (5) ───────────────────────────────────────
            {
                "title": "Community Health Emergency Response",
                "description": "WHO protocols for CHWs responding to maternal health emergencies in community settings.",
                "category": "Emergency Response",
                "target_role": "chw",
                "content_type": "pdf",
                "url": "https://www.who.int/publications/i/item/9789241548953",
                "thumbnail": "🚨"
            },
            {
                "title": "Maternal Health Field Assessment",
                "description": "Standardized tools and checklists for assessing pregnant women in community health visits.",
                "category": "Field Protocols",
                "target_role": "chw",
                "content_type": "article",
                "url": "https://www.who.int/maternal_child_adolescent/documents/imci_chartbooklet/en/",
                "thumbnail": "📋"
            },
            {
                "title": "Immunization Schedule and Record Keeping",
                "description": "CDC guidelines for maintaining accurate immunization records and following vaccination schedules.",
                "category": "Immunization",
                "target_role": "chw",
                "content_type": "pdf",
                "url": "https://www.cdc.gov/vaccines/schedules/hcp/imz/child-adolescent.html",
                "thumbnail": "💉"
            },
            {
                "title": "Identifying Signs of Preterm Labor",
                "description": "Field guide for CHWs to recognize early warning signs of preterm labor and appropriate referral protocols.",
                "category": "Field Protocols",
                "target_role": "chw",
                "content_type": "video",
                "url": "https://www.who.int/news-room/fact-sheets/detail/preterm-birth",
                "thumbnail": "⚡"
            },
            {
                "title": "Community Health Data Collection",
                "description": "Best practices for collecting and reporting health data in community settings for maternal and child health programs.",
                "category": "Data Management",
                "target_role": "chw",
                "content_type": "article",
                "url": "https://www.who.int/healthinfo/systems/WHO_MBHSS_2010_full_web.pdf",
                "thumbnail": "📊"
            },
            
            # ─── NURSE RESOURCES (5) ─────────────────────────────────────
            {
                "title": "Obstetric Triage Guidelines",
                "description": "Clinical protocols for rapid assessment and prioritization of pregnant patients in emergency and clinic settings.",
                "category": "Triage",
                "target_role": "nurse",
                "content_type": "pdf",
                "url": "https://www.who.int/publications/i/item/managing-complications-in-pregnancy-and-childbirth",
                "thumbnail": "🏥"
            },
            {
                "title": "Medication Safety in Pregnancy",
                "description": "CDC guidelines on safe medication use during pregnancy and lactation, including contraindicated drugs.",
                "category": "Clinical Guidelines",
                "target_role": "nurse",
                "content_type": "article",
                "url": "https://www.cdc.gov/pregnancy/meds/treatingfortwo/index.html",
                "thumbnail": "💊"
            },
            {
                "title": "Postpartum Hemorrhage Management",
                "description": "WHO clinical protocols for prevention and management of postpartum hemorrhage in healthcare facilities.",
                "category": "Emergency Care",
                "target_role": "nurse",
                "content_type": "video",
                "url": "https://www.who.int/publications/i/item/who-recommendation-on-tranexamic-acid-for-the-treatment-of-postpartum-haemorrhage",
                "thumbnail": "⛑️"
            },
            {
                "title": "Antenatal Care Standards",
                "description": "Evidence-based guidelines for providing quality antenatal care, including screening schedules and interventions.",
                "category": "Clinical Guidelines",
                "target_role": "nurse",
                "content_type": "pdf",
                "url": "https://www.who.int/publications/i/item/9789241549912",
                "thumbnail": "🩺"
            },
            {
                "title": "Infection Prevention in Maternity Care",
                "description": "WHO standards for preventing healthcare-associated infections in maternity and newborn care settings.",
                "category": "Clinical Guidelines",
                "target_role": "nurse",
                "content_type": "article",
                "url": "https://www.who.int/publications/i/item/prevention-and-control-of-healthcare-associated-infections-in-maternity-and-newborn-care-settings",
                "thumbnail": "🧼"
            }
        ]
        
        created_count = 0
        skipped_count = 0
        
        for data in resources_data:
            try:
                # Check if resource already exists
                existing = Resource.query.filter_by(
                    title=data["title"], 
                    target_role=data["target_role"]
                ).first()
                
                if existing:
                    print(f"⏭️  Skipping: {data['title']} (already exists)")
                    skipped_count += 1
                    continue
                
                # Create new resource
                resource = Resource(
                    title=data["title"],
                    description=data["description"],
                    category=data["category"],
                    target_role=data["target_role"],
                    content_type=data["content_type"],
                    url=data["url"],
                    thumbnail=data["thumbnail"],
                    created_at=datetime.now(timezone.utc)
                )
                
                db.session.add(resource)
                print(f"✅ Created: {data['title']} ({data['target_role']})")
                created_count += 1
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Failed to create resource '{data['title']}': {str(e)}")
                continue
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n🎉 Resources seeding completed!")
            print(f"📊 Summary:")
            print(f"   ✅ Created: {created_count} resources")
            print(f"   ⏭️  Skipped: {skipped_count} resources (already existed)")
            print(f"\n📚 Resource breakdown:")
            print(f"   👶 Mother resources: 5")
            print(f"   🏥 CHW resources: 5") 
            print(f"   🩺 Nurse resources: 5")
            print(f"\n💡 All resources are from reputable health organizations (WHO, CDC, UNICEF, Mayo Clinic)")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Failed to commit resources: {str(e)}")

if __name__ == "__main__":
    seed_resources()