from flask import Blueprint, jsonify, request, g
import random
from datetime import datetime

from auth_utils import require_auth
from models import DietaryRecommendation

bp = Blueprint("nutrition", __name__)


def serialize_recommendation(record: DietaryRecommendation) -> dict:
    return {
        "id": record.id,
        "source_id": record.source_id,
        "title": record.title,
        "swahili_name": record.swahili_name,
        "description": record.description or record.content,
        "target_group": record.target_group,
        "target_groups": record.target_groups or [],
        "trimester_tags": record.trimester_tags or [],
        "meal_type": record.meal_type,
        "meal_time": record.meal_time,
        "key_nutrients": record.key_nutrients or [],
        "health_benefits": record.health_benefits or [],
        "preparation_tips": record.preparation_tips,
        "cautions": record.cautions or [],
        "nutrition_highlight": record.nutrition_highlight,
        "portion_guide": record.portion_guide,
        "image_suggestion": record.image_suggestion,
        "tags": record.tags or [],
        "calories": record.calories,
        "is_featured": record.is_featured,
        "source_name": record.source_name,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@bp.route("/nutrition/recommendations", methods=["GET"])
@require_auth
def list_recommendations():
    target_group = request.args.get("target_group")
    meal_type = request.args.get("meal_type")
    trimester = request.args.get("trimester")
    limit = request.args.get("limit", type=int) or 6
    limit = max(1, min(limit, 24))
    is_daily_plan = request.args.get("daily_plan", "false").lower() == "true"

    base_query = DietaryRecommendation.query.filter_by(is_active=True)

    if target_group:
        base_query = base_query.filter(DietaryRecommendation.target_groups.contains([target_group]))

    if trimester:
        base_query = base_query.filter(DietaryRecommendation.trimester_tags.contains([trimester]))

    if is_daily_plan:
        # Pseudo-randomize 4 specific meals using today's date + user.id as a deterministic seed
        user_id = g.current_user.id if hasattr(g, 'current_user') else 0
        seed = datetime.today().toordinal() + user_id
        rng = random.Random(seed)
        
        daily_meals = []
        for m_type in ["breakfast", "lunch", "snack", "dinner"]:
            q = base_query.filter(DietaryRecommendation.meal_type == m_type)
            records = q.all()
            if not records:
                # Fallback gracefully if strict filters yielded zero results for this meal type
                records = DietaryRecommendation.query.filter_by(is_active=True, meal_type=m_type).all()
            
            if records:
                daily_meals.append(rng.choice(records))
                
        return jsonify([serialize_recommendation(rec) for rec in daily_meals])

    else:
        if meal_type:
            base_query = base_query.filter(DietaryRecommendation.meal_type == meal_type)

        base_query = base_query.order_by(
            DietaryRecommendation.is_featured.desc(),
            DietaryRecommendation.updated_at.desc(),
            DietaryRecommendation.title.asc(),
        )

        records = base_query.limit(limit).all()
        return jsonify([serialize_recommendation(rec) for rec in records])
