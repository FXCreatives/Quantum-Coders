import os
from datetime import datetime, timedelta
from functools import wraps
import math
import jwt
from flask import request, jsonify, current_app
from passlib.hash import bcrypt

JWT_EXPIRES_MIN = int(os.getenv('JWT_EXPIRES_MIN', '43200'))  # 30 days by default

# Password helpers

def hash_password(pw: str) -> str:
    return bcrypt.hash(pw)

def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.verify(pw, hashed)

# JWT helpers

def create_token(user_id: int, role: str):
    payload = {
        'sub': user_id,
        'role': role,
        'exp': datetime.utcnow() + current_app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def decode_token(token: str):
    return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])


def auth_required(roles=None):
    from functools import wraps
    from flask_jwt_extended import jwt_required, get_jwt_identity
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user_id = get_jwt_identity()
            from .models import User
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 401
            request.user_id = user_id
            request.user_role = user.role
            if roles and request.user_role not in roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# Haversine distance in meters

def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
