import os
from datetime import datetime, timedelta
from functools import wraps
import math
import jwt
from flask import request, jsonify, current_app, url_for
from passlib.hash import bcrypt
from flask_socketio import emit
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message

JWT_EXPIRES_MIN = int(os.getenv('JWT_EXPIRES_MIN', '43200'))  # 30 days by default

# Password helpers

# Verification token helpers
def get_verification_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='tapin-verify')

def create_verification_token(email, role):
    s = get_verification_serializer()
    return s.dumps({'email': email, 'role': role})

def verify_verification_token(token, max_age=86400):  # 24 hours
    s = get_verification_serializer()
    try:
        return True, s.loads(token, max_age=max_age)
    except Exception as e:
        current_app.logger.error(f"[VERIFY] Token error: {str(e)}")
        return False, {'error': 'invalid'}

def send_verification_email(email, role, token):
    try:
        verify_url = url_for('auth.verify_email', token=token, _external=True)
        msg = Message(
            subject="TapIn Email Verification",
            recipients=[email],
            body=f"Click the link to verify your email:\n{verify_url}\nValid for 24 hours."
        )
        mail = current_app.extensions['mail']
        mail.send(msg)
        current_app.logger.info(f"[EMAIL] Sent verification link to {email} -> {verify_url}")
        return True
    except Exception as e:
        current_app.logger.error(f"[EMAIL] Failed to send verification email to {email}: {str(e)}")
        return False

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

def broadcast_check_in(class_id, student):
    emit('student_checked_in', {
        'name': student['name'],
        'student_id': student['student_id'],
        'check_in_time': student['check_in_time']
    }, room=str(class_id))
