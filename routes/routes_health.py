from flask import Blueprint, jsonify

bp = Blueprint('health', __name__)

@bp.route('/health', methods=['GET'])
def healthcheck():
    return jsonify({"status": "ok"}), 200
