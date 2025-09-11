import logging
import re
from flask import Blueprint, request, jsonify, session, url_for
from .models import db, User
from .utils import hash_password, verify_password, create_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/register')
def register():
    # Detect JSON or form
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    fullname = (data.get('fullname') or data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    confirm = data.get('confirm-password', '') or data.get('confirm_password', '')
    student_id = (data.get('student_id') or '').strip()
    role = data.get('role', 'lecturer' if not student_id else 'student')

    errors = []

    # Validations
    if not fullname or not email or not password:
        errors.append('Missing required fields')

    if password != confirm:
        errors.append('Passwords do not match')

    # Email validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if email and not re.match(email_regex, email):
        errors.append('Invalid email format')

    # Password strength validation
    if len(password) < 8:
        errors.append('Password must be at least 8 characters long')
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter')
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter')
    if not re.search(r'\d', password):
        errors.append('Password must contain at least one digit')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Password must contain at least one special character')

    if errors:
        error_msg = ', '.join(errors)
        return jsonify({'error': error_msg}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 400

    # For students, validate student_id if role is student
    if role == 'student' and not student_id:
        return jsonify({'error': 'Student ID is required for student accounts'}), 400

    u = User(fullname=fullname, email=email, phone=None, student_id=student_id or None, role=role, password_hash=hash_password(password))
    db.session.add(u)
    try:
        db.session.commit()
        logging.info(f"[REGISTER] User committed: id={u.id}, email={u.email}, role={role}")
    except Exception as e:
        db.session.rollback()
        logging.error(f"[REGISTER] Commit failed: {str(e)}")
        return jsonify({'error': 'Registration failed due to database error'}), 500
    
    token = create_token(u.id, u.role)

    # Set session for fallback
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    if role == 'student':
        session['student_id'] = u.student_id
    session.permanent = True
    logging.info(f"[REGISTER] Session set for user {u.id}, role {u.role}, full session after: {dict(session)}")

    next_url = url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_dashboard')
    response_data = {'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'message': 'Registration successful'}
    logging.info(f"[REGISTER] Returning response: { {k: v if k != 'token' else f'token_len:{len(v)}' for k,v in response_data.items()} }")
    return jsonify(response_data)

@auth_bp.post('/login')
def login():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    student_id = data.get('student_id', '')

    logging.info(f"[LOGIN] Attempting login with email='{email}', student_id='{student_id}'")

    if not email and not student_id:
        return jsonify({'success': False, 'message': 'Email or Student ID required'}), 400

    # Try email first
    u = None
    if email:
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        u = User.query.filter_by(email=email).first()
    if not u and student_id:
        u = User.query.filter_by(student_id=student_id, role='student').first()
    
    if not u:
        logging.warning(f"[LOGIN] No user found for email='{email}' or student_id='{student_id}'")
        return jsonify({'success': False, 'message': 'User not found'}), 401

    if not verify_password(password, u.password_hash):
        logging.warning(f"[LOGIN] Password mismatch for user {u.id}")
        return jsonify({'success': False, 'message': 'Invalid password'}), 401

    token = create_token(u.id, u.role)

    # Set session for fallback
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    if u.role == 'student':
        session['student_id'] = u.student_id
    session.permanent = True

    logging.info(f"[LOGIN] Session set for user {u.id}, role {u.role}, full session: {dict(session)}")

    next_url = url_for('lecturer_initial_home') if u.role == 'lecturer' else url_for('student_dashboard')
    response_data = {'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'success': True, 'message': 'Logged in successfully'}
    logging.info(f"[LOGIN] Returning response: { {k: v if k != 'token' else f'token_len:{len(v)}' for k,v in response_data.items()} }, session after: {dict(session)}")
    return jsonify(response_data)

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
