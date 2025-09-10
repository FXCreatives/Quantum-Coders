import logging
from flask import Blueprint, request, jsonify
from .models import db, User
from .utils import hash_password, verify_password, create_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/register')
def register():
    logging.debug(f"Register request method: {request.method}")
    logging.debug(f"Register request headers: {dict(request.headers)}")
    logging.debug(f"Register request data: {request.get_data(as_text=True)}")
    try:
        data = request.form
        logging.debug(f"Parsed form data: {dict(data)}")
    except Exception as e:
        logging.error(f"Failed to parse form: {e}")
        return jsonify({'error': 'Invalid form data'}), 400
    
    fullname = data.get('fullname') or data.get('name')  # Support both field names
    email = data.get('email')
    phone = None  # Not in form
    student_id = data.get('student_id')
    role = data.get('role')  # 'lecturer' or 'student'
    password = data.get('password')
    confirm_password = data.get('confirm_password') or data.get('confirm-password')

    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    if role not in ('lecturer', 'student'):
        return jsonify({'error': 'Invalid role'}), 400

    if not all([fullname, email, password]):
        return jsonify({'error': 'Missing fields'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    u = User(fullname=fullname, email=email, phone=phone, student_id=student_id, role=role, password_hash=hash_password(password))
    db.session.add(u)
    db.session.commit()

    token = create_token(u.id, u.role)
    return jsonify({'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}}), 201

@auth_bp.post('/login')
def login():
    logging.debug(f"Login request method: {request.method}")
    logging.debug(f"Login request headers: {dict(request.headers)}")
    logging.debug(f"Login request data: {request.get_data(as_text=True)}")
    try:
        data = request.form
        logging.debug(f"Parsed form data: {dict(data)}")
    except Exception as e:
        logging.error(f"Failed to parse form: {e}")
        return jsonify({'error': 'Invalid form data'}), 400
    email = data.get('email')
    password = data.get('password')
    student_id = data.get('student_id')

    # Try email first
    u = User.query.filter_by(email=email).first()
    if not u and student_id:
        u = User.query.filter_by(student_id=student_id, role='student').first()
    
    if not u or not verify_password(password, u.password_hash):
        return jsonify({'error': 'Invalid credentials'}), 401

    token = create_token(u.id, u.role)
    return jsonify({'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}})

@auth_bp.get('/me')
@auth_bp.put('/me')
def me():
    logging.debug(f"Me request method: {request.method}")
    logging.debug(f"Me request headers: {dict(request.headers)}")
    from .utils import auth_required
    if request.method == 'GET':
        @auth_required()
        def _get():
            u = User.query.get(request.user_id)
            return jsonify({'id': u.id, 'fullname': u.fullname, 'email': u.email, 'phone': u.phone, 'role': u.role, 'student_id': u.student_id})
        return _get()
    else:
        @auth_required()
        def _put():
            data = request.get_json(force=True)
            u = User.query.get(request.user_id)
            u.fullname = data.get('fullname') or data.get('name', u.fullname)  # Support both field names
            u.phone = data.get('phone', u.phone)
            u.student_id = data.get('student_id', u.student_id)
            db.session.commit()
            return jsonify({'message': 'Profile updated'})
        return _put()
