# routes_profile.py
import os
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from .models import db, User

profile_bp = Blueprint("profile", __name__, url_prefix="/api/auth")

# Directory to store avatars
AVATAR_DIR = os.path.join(os.getcwd(), "static", "uploads", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -----------------------
# Get profile
# -----------------------
@profile_bp.route("/me", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    avatar_url = f"/static/uploads/avatars/{user.avatar}" if user.avatar else None
    return jsonify({
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "avatar": avatar_url
    })

# -----------------------
# Upload avatar
# -----------------------
@profile_bp.route("/avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    if "avatar" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["avatar"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    filename = secure_filename(f"user_{user.id}_{file.filename}")
    filepath = os.path.join(AVATAR_DIR, filename)
    file.save(filepath)

    # Delete old avatar if exists
    if user.avatar and user.avatar != filename:
        old_path = os.path.join(AVATAR_DIR, user.avatar)
        if os.path.exists(old_path):
            os.remove(old_path)

    user.avatar = filename
    db.session.commit()

    return jsonify({"success": True, "avatar": f"/static/uploads/avatars/{filename}"})

# -----------------------
# Remove avatar
# -----------------------
@profile_bp.route("/avatar", methods=["DELETE"])
@jwt_required()
def remove_avatar():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    if user.avatar:
        path = os.path.join(AVATAR_DIR, user.avatar)
        if os.path.exists(path):
            os.remove(path)
        user.avatar = None
        db.session.commit()

    return jsonify({"success": True})


# -----------------------
# Update profile
# -----------------------
@profile_bp.route("/update-profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    # Update basic info
    if "name" in data:
        user.name = data["name"]
    if "email" in data:
        user.email = data["email"]
    if "phone" in data:
        user.phone = data["phone"]

    # Update password if provided
    if "password" in data and data["password"]:
        # Assuming User model has set_password method
        user.set_password(data["password"])

    db.session.commit()

    return jsonify({"success": True, "message": "Profile updated successfully"})
