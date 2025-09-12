import logging
import re
from flask import Blueprint, request, jsonify, session, url_for, flash
from .models import db, User
from .utils import hash_password, verify_password, create_token, send_verification_email, create_verification_token

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/register')
def register():
    logging.info("[REGISTER] Request received")
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

    logging.info(f"[REGISTER] Parsed data: fullname={fullname}, email={email}, role={role}, student_id={student_id}")

    errors = []

    # Validations
    if not fullname or not email or not password:
        errors.append('Missing required fields')
        logging.warning(f"[REGISTER] Missing required fields: fullname={bool(fullname)}, email={bool(email)}, password={bool(password)}")

    if password != confirm:
        errors.append('Passwords do not match')
        logging.warning(f"[REGISTER] Passwords do not match for email={email}")

    # Email validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if email and not re.match(email_regex, email):
        errors.append('Invalid email format')
        logging.warning(f"[REGISTER] Invalid email format: {email}")

    # Password strength validation
    if len(password) < 8:
        errors.append('Password must be at least 8 characters long')
        logging.warning(f"[REGISTER] Password too short: length={len(password)} for email={email}")
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter')
        logging.warning(f"[REGISTER] No uppercase in password for email={email}")
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter')
        logging.warning(f"[REGISTER] No lowercase in password for email={email}")
    if not re.search(r'\d', password):
        errors.append('Password must contain at least one digit')
        logging.warning(f"[REGISTER] No digit in password for email={email}")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Password must contain at least one special character')
        logging.warning(f"[REGISTER] No special char in password for email={email}")

    if errors:
        error_msg = ', '.join(errors)
        logging.warning(f"[REGISTER] Validation errors for email={email}: {error_msg}")
        return jsonify({'error': error_msg}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        logging.warning(f"[REGISTER] Email already registered: {email}")
        return jsonify({'error': 'Email already registered'}), 400

    # For students, validate student_id if role is student
    if role == 'student' and not student_id:
        logging.warning(f"[REGISTER] Missing student_id for student role: email={email}")
        return jsonify({'error': 'Student ID is required for student accounts'}), 400

    u = User(fullname=fullname, email=email, phone=None, student_id=student_id or None, role=role, is_verified=False, password_hash=hash_password(password))
    db.session.add(u)
    try:
        db.session.commit()
        logging.info(f"[REGISTER] User committed: id={u.id}, email={u.email}, role={role}, verified=False")
    except Exception as e:
        db.session.rollback()
        logging.error(f"[REGISTER] Commit failed: {str(e)}", exc_info=True)
        return jsonify({'error': 'Registration failed due to database error'}), 500
    
    # Send verification email
    try:
        verification_token = create_verification_token(u.email, u.role)
        logging.info(f"[REGISTER] Verification token created for {u.email}")
    except Exception as e:
        logging.error(f"[REGISTER] Failed to create verification token for {u.email}: {str(e)}", exc_info=True)
        verification_token = None

    if verification_token and send_verification_email(u.email, u.role, verification_token):
        logging.info(f"[REGISTER] Verification email sent to {u.email}")
    else:
        logging.warning(f"[REGISTER] Failed to send verification email to {u.email}")

    next_url = url_for('account')
    response_data = {'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'message': 'Registration successful. Please check your email to verify your account.'}
    logging.info(f"[REGISTER] Returning response: {response_data}")
    return jsonify(response_data)

@auth_bp.post('/login')
def login():
    logging.info("[LOGIN] Request received")
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    student_id = data.get('student_id', '')

    logging.info(f"[LOGIN] Attempting login with email='{email}', student_id='{student_id}'")

    if not email and not student_id:
        logging.warning("[LOGIN] No email or student_id provided")
        return jsonify({'success': False, 'message': 'Email or Student ID required'}), 400

    # Try email first
    u = None
    if email:
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            logging.warning(f"[LOGIN] Invalid email format: {email}")
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        u = User.query.filter_by(email=email).first()
        logging.info(f"[LOGIN] Queried user by email: {email}, found={u is not None}")
    if not u and student_id:
        u = User.query.filter_by(student_id=student_id, role='student').first()
        logging.info(f"[LOGIN] Queried user by student_id: {student_id}, found={u is not None}")
    
    if not u:
        logging.warning(f"[LOGIN] No user found for email='{email}' or student_id='{student_id}'")
        return jsonify({'success': False, 'message': 'User not found'}), 401

    if not verify_password(password, u.password_hash):
        logging.warning(f"[LOGIN] Password mismatch for user {u.id} (email={u.email})")
        return jsonify({'success': False, 'message': 'Invalid password'}), 401

    if not u.is_verified:
        logging.warning(f"[LOGIN] User {u.id} (email={u.email}) not verified")
        return jsonify({'success': False, 'message': 'Please verify your email before logging in.'}), 401

    try:
        token = create_token(u.id, u.role)
        logging.info(f"[LOGIN] Token created for user {u.id}")
    except Exception as e:
        logging.error(f"[LOGIN] Failed to create token for user {u.id}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to generate session token'}), 500

    # Set session for fallback
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    session['is_verified'] = u.is_verified
    if u.role == 'student':
        session['student_id'] = u.student_id
    session.permanent = True

    logging.info(f"[LOGIN] Session set for user {u.id}, role {u.role}, verified={u.is_verified}, full session: {dict(session)}")

    next_url = url_for('lecturer_initial_home') if u.role == 'lecturer' else url_for('student_dashboard')
    response_data = {'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id, 'is_verified': u.is_verified}, 'redirect_url': next_url, 'success': True, 'message': 'Logged in successfully'}
    logging.info(f"[LOGIN] Returning response: { {k: v if k != 'token' else f'token_len:{len(v)}' for k,v in response_data.items()} }, session after: {dict(session)}")
    return jsonify(response_data)

@auth_bp.route('/verify/<token>')
def verify_email(token):
    from .utils import verify_verification_token
    valid, payload = verify_verification_token(token)
    if valid:
        email = payload.get('email')
        role = payload.get('role')
        user = User.query.filter_by(email=email, role=role).first()
        if user and not user.is_verified:
            user.is_verified = True
            db.session.commit()
            flash('Email verified successfully. You can now log in.', 'success')
            next_url = url_for('lecturer_login_page') if role == 'lecturer' else url_for('student_login_page')
            return redirect(next_url)
        else:
            flash('Invalid verification link or already verified.', 'error')
            return redirect(url_for('account'))
    else:
        flash('Verification link expired or invalid.', 'error')
        return redirect(url_for('account'))

@auth_bp.post('/resend')
def resend_verification():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = (data.get('email') or '').strip().lower()
    role = data.get('role', 'lecturer')

    if not email or not role:
        return jsonify({'error': 'Email and role are required'}), 400

    # Email validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        return jsonify({'error': 'Invalid email format'}), 400

    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if user.is_verified:
        return jsonify({'error': 'Account already verified'}), 400

    verification_token = create_verification_token(email, role)
    if send_verification_email(email, role, verification_token):
        logging.info(f"[RESEND] Verification email resent to {email}")
        return jsonify({'message': 'Verification email resent successfully'}), 200
    else:
        return jsonify({'error': 'Failed to send verification email'}), 500


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
            return jsonify({'id': u.id, 'fullname': u.fullname, 'email': u.email, 'phone': u.phone, 'role': u.role, 'student_id': u.student_id, 'is_verified': u.is_verified})
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
