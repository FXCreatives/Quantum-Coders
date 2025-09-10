# routes_auth.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from .models import User, db
import os
import logging

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    auth_header = request.headers.get('Authorization')
    logging.info(f"[AUTH/ME] Request with auth header: {auth_header[:50]}..." if auth_header else "[AUTH/ME] No auth header")
    try:
        user_id = get_jwt_identity()
        logging.info(f"[AUTH/ME] Successfully decoded JWT for user_id: {user_id}")
    except Exception as e:
        logging.error(f"[AUTH/ME] JWT decode failed: {str(e)}")
        raise
    user = User.query.get(user_id)
    if not user:
        logging.warning(f"[AUTH/ME] User {user_id} not found")
        return jsonify({"error":"User not found"}), 404
    logging.info(f"[AUTH/ME] Returning profile for user {user_id}: {user.fullname}")
    return jsonify({
        "fullname": user.fullname,
        "email": user.email,
        "phone": user.phone,
        "avatar_url": user.avatar_url if hasattr(user,'avatar_url') else None
    })

@auth_bp.route("/avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    user_id = get_jwt_identity()
    file = request.files.get("avatar")
    if not file:
        return jsonify({"error": "No file"}), 400
    # Save file to static folder
    filename = f"avatar_{user_id}.png"
    path = os.path.join("static", "avatars", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file.save(path)
    user = User.query.get(user_id)
    user.avatar_url = f"/static/avatars/{filename}"
    db.session.commit()
    return jsonify({"success": True, "avatar_url": user.avatar_url})

@auth_bp.route("/avatar", methods=["DELETE"])
@jwt_required()
def delete_avatar():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if hasattr(user, "avatar_url") and user.avatar_url:
        try: os.remove(user.avatar_url.lstrip("/"))
        except: pass
        user.avatar_url = None
        db.session.commit()
    return jsonify({"success": True})
