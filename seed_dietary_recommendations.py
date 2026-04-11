import json
from datetime import datetime, timezone
from pathlib import Path

from app import create_app, db
from models import DietaryRecommendation


MEAL_TIME_DEFAULTS = {
    "breakfast": "7:00 AM",
    "snack": "10:00 AM",
    "lunch": "1:00 PM",
    "dinner": "7:00 PM",
}

MEAL_CALORIES_ESTIMATE = {
    "breakfast": 350,
    "snack": 220,
    "lunch": 480,
    "dinner": 520,
}

DATA_PATH = Path(__file__).parent / "data" / "kenyan_pregnancy_food_recommendations.json"


def seed_dietary_recommendations():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Nutrition data file not found at {DATA_PATH}")

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    recommendations = payload.get("recommendations", [])

    app = create_app()
    with app.app_context():
        created = 0
        updated = 0

        for item in recommendations:
            now = datetime.now(timezone.utc)
            source_id = item.get("id")
            if not source_id:
                continue

            record = DietaryRecommendation.query.filter_by(source_id=source_id).first()
            if record is None:
                record = DietaryRecommendation()
                record.source_id = source_id
                record.title = item.get("name", "Nutrition Recommendation")
                record.content = item.get("description", "")
                record.created_at = now
                is_new = True
            else:
                is_new = False

            record.title = item.get("name", record.title)
            record.swahili_name = item.get("swahili_name")
            record.content = item.get("description", record.content)
            record.description = item.get("description")
            record.target_group = (item.get("target_groups") or [None])[0]
            record.target_groups = item.get("target_groups", [])
            record.trimester_tags = item.get("trimester_tags", [])
            record.meal_type = item.get("meal_type")
            record.meal_time = item.get("meal_time") or MEAL_TIME_DEFAULTS.get(item.get("meal_type"), "12:00 PM")
            record.key_nutrients = item.get("key_nutrients", [])
            record.health_benefits = item.get("health_benefits", [])
            record.preparation_tips = item.get("preparation_tips")
            record.cautions = item.get("cautions", [])
            record.nutrition_highlight = item.get("nutrition_highlight")
            record.portion_guide = item.get("portion_guide")
            record.image_suggestion = item.get("image_suggestion")
            record.tags = item.get("tags", [])
            record.calories = item.get("calories") or MEAL_CALORIES_ESTIMATE.get(item.get("meal_type"))
            record.is_featured = "general_all_trimesters" in (item.get("target_groups") or [])
            record.source_name = metadata.get("title", "Kenyan Pregnancy Nutrition Recommendations")
            record.updated_at = now
            if record.created_at is None:
                record.created_at = now

            db.session.add(record)
            created += 1 if is_new else 0
            updated += 0 if is_new else 1

        db.session.commit()
        print(f"Dietary recommendations seeding complete. Created: {created}, Updated: {updated}")


if __name__ == "__main__":
    seed_dietary_recommendations()
