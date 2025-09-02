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
        'exp': datetime.utcnow() + timedelta(minutes=JWT_EXPIRES_MIN)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def decode_token(token: str):
    return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])


def auth_required(roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Authorization header missing'}), 401
            token = auth_header.split(' ', 1)[1]
            try:
                payload = decode_token(token)
            except Exception:
                return jsonify({'error': 'Invalid/expired token'}), 401

            if roles and payload.get('role') not in roles:
                return jsonify({'error': 'Forbidden'}), 403

            request.user_id = payload.get('sub')
            request.user_role = payload.get('role')
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
