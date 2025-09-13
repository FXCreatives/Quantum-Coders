import logging
import re
from flask import Blueprint, request, jsonify, session, url_for, flash, redirect, render_template
from .models import db, User
from .utils import hash_password, verify_password, create_token, send_verification_email, create_verification_token, send_password_reset_email, create_reset_token, verify_reset_token

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
    
    # Set session for unverified access
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    session['is_verified'] = u.is_verified
    if u.role == 'student':
        session['student_id'] = u.student_id
    session.permanent = True
    logging.info(f"[REGISTER] Session set for user {u.id}, role {u.role}, verified={u.is_verified}")

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

    next_url = url_for('lecturer_initial_home') if u.role == 'lecturer' else url_for('student_initial_home')
    if request.is_json:
        response_data = {'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'message': 'Registration successful. Please check your email to verify your account.'}
        logging.info(f"[REGISTER] Returning JSON response: {response_data}")
        return jsonify(response_data)
    else:
        flash('Registration successful. Please check your email to verify your account.', 'success')
        logging.info(f"[REGISTER] Redirecting to {next_url} for form submission")
        return redirect(next_url)

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
        logging.info(f"[LOGIN DEBUG] Executing query for email (lowercased): '{email}'")
        u = User.query.filter_by(email=email).first()
        user_count = User.query.filter_by(email=email).count()
        logging.info(f"[LOGIN] Queried user by email: '{email}', found={u is not None}, total users with this email={user_count}")
        if u:
            logging.info(f"[LOGIN DEBUG] Found user details: id={u.id}, role={u.role}, verified={u.is_verified}, email_in_db='{u.email}'")
    if not u and student_id:
        logging.info(f"[LOGIN DEBUG] Executing query for student_id: '{student_id}' (role='student')")
        u = User.query.filter_by(student_id=student_id, role='student').first()
        sid_count = User.query.filter_by(student_id=student_id, role='student').count()
        logging.info(f"[LOGIN] Queried user by student_id: '{student_id}', found={u is not None}, total students with this ID={sid_count}")
        if u:
            logging.info(f"[LOGIN DEBUG] Found student details: id={u.id}, email='{u.email}', verified={u.is_verified}")
    
    if not u:
        logging.warning(f"[LOGIN] No user found for email='{email}' or student_id='{student_id}'")
        return jsonify({'success': False, 'message': 'User not found'}), 401

    if not verify_password(password, u.password_hash):
        logging.warning(f"[LOGIN] Password mismatch for user {u.id} (email={u.email})")
        return jsonify({'success': False, 'message': 'Invalid password'}), 401

    # Allow unverified login; decorators will handle redirects
    logging.info(f"[LOGIN] User {u.id} (email={u.email}) login allowed, verified={u.is_verified}")

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

    if u.role == 'lecturer':
        next_url = url_for('lecturer_initial_home') if not u.is_verified else url_for('lecturer_dashboard')
    else:
        next_url = url_for('student_initial_home') if not u.is_verified else url_for('student_dashboard')
    logging.info(f"[LOGIN] Computed next_url: {next_url} for role {u.role}, verified={u.is_verified}")

    if not u.is_verified:
        flash('Please verify your email before accessing the dashboard', 'warning')
    if request.is_json:
        response_data = {'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id, 'is_verified': u.is_verified}, 'redirect_url': next_url, 'success': True, 'message': 'Logged in successfully' + (' Please verify your email to access full features.' if not u.is_verified else '')}
        logging.info(f"[LOGIN] Returning JSON response: { {k: v if k != 'token' else f'token_len:{len(v)}' for k,v in response_data.items()} }, session after: {dict(session)}")
        return jsonify(response_data)
    else:
        flash('Logged in successfully' + ('. Please verify your email to access the dashboard.' if not u.is_verified else ''), 'success')
        logging.info(f"[LOGIN] Redirecting to {next_url} for form submission")
        return redirect(next_url)
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
    

@auth_bp.post('/forgot_password')
def forgot_password():
    logging.info("[FORGOT_PASSWORD] Request received")
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = (data.get('email') or '').strip().lower()

    if not email:
        logging.warning("[FORGOT_PASSWORD] No email provided")
        if request.is_json:
            return jsonify({'error': 'Email is required'}), 400
        else:
            flash('Email is required', 'error')
            return redirect(url_for('account'))

    # Email validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        logging.warning(f"[FORGOT_PASSWORD] Invalid email format: {email}")
        if request.is_json:
            return jsonify({'error': 'Invalid email format'}), 400
        else:
            flash('Invalid email format', 'error')
            return redirect(url_for('account'))

    user = User.query.filter_by(email=email).first()
    if not user:
        logging.warning(f"[FORGOT_PASSWORD] User not found for email: {email}")
        if request.is_json:
            return jsonify({'error': 'User not found'}), 404
        else:
            flash('User not found', 'error')
            return redirect(url_for('account'))

    try:
        reset_token = create_reset_token(user.email, user.role)
        logging.info(f"[FORGOT_PASSWORD] Reset token created for {user.email}")
    except Exception as e:
        logging.error(f"[FORGOT_PASSWORD] Failed to create reset token for {user.email}: {str(e)}", exc_info=True)
        if request.is_json:
            return jsonify({'error': 'Failed to generate reset token'}), 500
        else:
            flash('Failed to send reset email', 'error')
            return redirect(url_for('account'))

    if send_password_reset_email(user.email, user.role, reset_token):
        logging.info(f"[FORGOT_PASSWORD] Password reset email sent successfully to {user.email}")
        if request.is_json:
            return jsonify({'message': 'Password reset email sent. Check your email.'}), 200
        else:
            flash('Password reset email sent. Check your email.', 'success')
            return redirect(url_for('account'))
    else:
        logging.error(f"[FORGOT_PASSWORD] Failed to send password reset email to {user.email}")
        if request.is_json:
            return jsonify({'error': 'Failed to send reset email'}), 500
        else:
            flash('Failed to send reset email. Please try again.', 'error')
            return redirect(url_for('account'))


@auth_bp.get('/validate_reset_token')
def validate_reset_token():
    token = request.args.get('token')
    if not token:
        return jsonify({'valid': False, 'message': 'Missing token'}), 400
    valid, payload = verify_reset_token(token)
    if valid:
        return jsonify({'valid': True, 'role': payload.get('role')})
    else:
        return jsonify({'valid': False, 'message': 'Invalid or expired token'}), 400


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

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('account'))
