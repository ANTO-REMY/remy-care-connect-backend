from flask import Blueprint, jsonify
from models import db, EducationalMaterial

bp = Blueprint('materials', __name__)

@bp.route('/educational_material/<int:material_id>', methods=['GET'])
def get_material(material_id):
    material = EducationalMaterial.query.get(material_id)
    if not material:
        return jsonify({"error": "Educational material not found."}), 404
    return jsonify({
        "id": material.id,
        "title": material.title,
        "content": material.content,
        "file_url": material.file_url,
        "category": material.category,
        "audience": material.audience
    }), 200
