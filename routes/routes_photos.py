import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from werkzeug.utils import secure_filename
from models import db, User, ProfilePhoto
from auth_utils import require_auth, get_current_user
from datetime import datetime, timezone

bp = Blueprint('photos', __name__)

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _upload_dir() -> str:
    upload_dir = os.path.join(current_app.root_path, 'uploads', 'profile_photos')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


# ------------------------------------------------------------------
# POST /api/v1/profile/photo  — upload / replace profile photo
# ------------------------------------------------------------------
@bp.route('/profile/photo', methods=['POST'])
@require_auth
def upload_profile_photo():
    """Upload or replace the current user's profile photo."""
    user = get_current_user()

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo file provided. Use field name: photo'}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not _allowed(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: jpg, jpeg, png, webp'}), 400

    # Read and check size
    file_bytes = file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return jsonify({'error': 'File too large. Maximum size is 5 MB'}), 413

    # Generate a unique safe filename
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    unique_name = f"user_{user.id}_{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(_upload_dir(), unique_name)

    # Save to disk
    with open(save_path, 'wb') as f:
        f.write(file_bytes)

    file_url = f'/api/v1/profile/photo/file/{unique_name}'

    try:
        # Deactivate existing active photo(s) for this user
        ProfilePhoto.query.filter_by(user_id=user.id, is_active=True).update({'is_active': False})

        # Create new record
        photo = ProfilePhoto(
            user_id=user.id,
            role=user.role,
            file_name=secure_filename(file.filename),
            file_url=file_url,
            mime_type=file.mimetype or f'image/{ext}',
            file_size=len(file_bytes),
            is_active=True,
            uploaded_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.session.add(photo)
        db.session.commit()

        return jsonify({
            'message': 'Profile photo uploaded successfully',
            'photo_id': photo.id,
            'file_url': file_url,
            'file_name': photo.file_name,
            'file_size': photo.file_size,
            'mime_type': photo.mime_type,
            'uploaded_at': photo.uploaded_at.isoformat()
        }), 201

    except Exception as e:
        db.session.rollback()
        # Clean up saved file on error
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({'error': str(e)}), 500


# ------------------------------------------------------------------
# GET /api/v1/profile/photo  — get current user's active photo info
# ------------------------------------------------------------------
@bp.route('/profile/photo', methods=['GET'])
@require_auth
def get_my_profile_photo():
    """Get the current user's active profile photo."""
    user = get_current_user()
    photo = ProfilePhoto.query.filter_by(user_id=user.id, is_active=True).first()
    if not photo:
        return jsonify({'error': 'No profile photo found'}), 404

    return jsonify({
        'photo_id': photo.id,
        'user_id': photo.user_id,
        'role': photo.role,
        'file_url': photo.file_url,
        'file_name': photo.file_name,
        'file_size': photo.file_size,
        'mime_type': photo.mime_type,
        'uploaded_at': photo.uploaded_at.isoformat()
    }), 200


# ------------------------------------------------------------------
# GET /api/v1/profile/photo/<user_id>  — get any user's active photo
# ------------------------------------------------------------------
@bp.route('/profile/photo/<int:target_user_id>', methods=['GET'])
@require_auth
def get_user_profile_photo(target_user_id):
    """Get any user's active profile photo (for CHW/Nurse to view mother photos)."""
    photo = ProfilePhoto.query.filter_by(user_id=target_user_id, is_active=True).first()
    if not photo:
        return jsonify({'error': 'No profile photo found for this user'}), 404

    return jsonify({
        'photo_id': photo.id,
        'user_id': photo.user_id,
        'role': photo.role,
        'file_url': photo.file_url,
        'file_name': photo.file_name,
        'file_size': photo.file_size,
        'mime_type': photo.mime_type,
        'uploaded_at': photo.uploaded_at.isoformat()
    }), 200


# ------------------------------------------------------------------
# GET /api/v1/profile/photo/file/<filename>  — serve the actual image
# ------------------------------------------------------------------
@bp.route('/profile/photo/file/<filename>', methods=['GET'])
def serve_profile_photo(filename):
    """Serve the actual image file (no auth — URL contains a UUID)."""
    safe_name = secure_filename(filename)
    return send_from_directory(_upload_dir(), safe_name)


# ------------------------------------------------------------------
# DELETE /api/v1/profile/photo  — remove current user's active photo
# ------------------------------------------------------------------
@bp.route('/profile/photo', methods=['DELETE'])
@require_auth
def delete_profile_photo():
    """Delete (deactivate) the current user's active profile photo."""
    user = get_current_user()
    photo = ProfilePhoto.query.filter_by(user_id=user.id, is_active=True).first()
    if not photo:
        return jsonify({'error': 'No active profile photo to delete'}), 404

    photo.is_active = False
    photo.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Profile photo removed successfully'}), 200
