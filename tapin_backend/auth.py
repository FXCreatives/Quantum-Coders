import logging
import re
from flask import Blueprint, request, jsonify, session, url_for, flash, redirect, render_template
from .models import db, User
from .utils import (
    hash_password, verify_password, send_verification_email,
    create_verification_token, send_password_reset_email,
    create_reset_token, verify_reset_token, auth_required,
    set_user_session, verify_verification_token, create_token
)

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/register')
def register():
    logging.info("[REGISTER] Request received")
    data = request.get_json() if request.is_json else request.form

    fullname = (data.get('fullname') or data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    confirm = data.get('confirm-password', '') or data.get('confirm_password', '')
    student_id = (data.get('student_id') or '').strip()
    role = (data.get('role') or '').strip().lower()   # ✅ FIXED
    if role not in ('student', 'lecturer'):
        return jsonify({'error': 'Invalid role'}), 400

    errors = []
    if not fullname or not email or not password:
        errors.append('Missing required fields')
    if password != confirm:
        errors.append('Passwords do not match')
    if len(password) < 8:
        errors.append('Password must be at least 8 characters long')
    if errors:
        return jsonify({'error': ', '.join(errors)}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 400
    if role == 'student' and not student_id:
        return jsonify({'error': 'Student ID is required for student accounts'}), 400

    u = User(
        fullname=fullname, email=email, phone=None,
        student_id=student_id or None, role=role,
        is_verified=False, password_hash=hash_password(password)
    )
    db.session.add(u)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Registration failed'}), 500

    session.clear()
    set_user_session(u)

    token = create_verification_token(u.email, u.role)
    send_verification_email(u.email, u.role, token)

    next_url = url_for('lecturer_initial_home') if u.role == 'lecturer' else url_for('student_dashboard')
    if request.is_json:
        return jsonify({
            'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role},
            'redirect_url': next_url,
            'message': 'Registration successful. Please verify your email.'
        })
    else:
        flash('Registration successful. Please verify your email.', 'success')
        return redirect(next_url)

@auth_bp.post('/login')
def login():
    logging.info("[LOGIN] Request received")
    data = request.get_json() if request.is_json else request.form
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    student_id = (data.get('student_id') or '').strip()

    # Lookup
    u = None
    if email:
        u = User.query.filter_by(email=email).first()
    if not u and student_id:
        u = User.query.filter_by(student_id=student_id, role='student').first()
    if not u or not verify_password(password, u.password_hash):
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    session.clear()
    set_user_session(u)

    if u.is_verified:
        next_url = url_for('lecturer_dashboard') if u.role == 'lecturer' else url_for('student_classes')
        flash_msg = 'Logged in successfully'
    else:
        next_url = url_for('lecturer_verify_notice') if u.role == 'lecturer' else url_for('student_initial_home')
        flash_msg = 'Logged in. Please verify your email.'

    if request.is_json:
        return jsonify({
            'token': create_token(u.id, u.role),
            'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'is_verified': u.is_verified},
            'redirect_url': next_url,
            'success': True,
            'message': flash_msg
        })
    else:
        flash(flash_msg, 'success')
        return redirect(next_url)
@auth_bp.post('/resend')
def resend_verification():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = (data.get('email') or '').strip().lower()
    role = (data.get('role', 'lecturer') or '').strip().lower()

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


@auth_bp.route('/me', methods=['GET', 'PUT'])
@auth_required()
def me():
    logging.debug(f"Me request method: {request.method}")
    logging.debug(f"Me request headers: {dict(request.headers)}")
    if request.method == 'GET':
        u = User.query.get(request.user_id)
        return jsonify({'id': u.id, 'fullname': u.fullname, 'email': u.email, 'phone': u.phone, 'role': u.role, 'student_id': u.student_id, 'is_verified': u.is_verified})
    else:
        data = request.get_json(force=True)
        u = User.query.get(request.user_id)
        u.fullname = data.get('fullname') or data.get('name', u.fullname)  # Support both field names
        u.phone = data.get('phone', u.phone)
        u.student_id = data.get('student_id', u.student_id)
        db.session.commit()
        return jsonify({'message': 'Profile updated'})

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('account'))

@auth_bp.route('/verify-email/<token>')
def verify_email_route(token):
    valid, payload = verify_verification_token(token, max_age=3600)
    if not valid:
        flash('Verification link invalid or expired.', 'error')
        return redirect(url_for('account'))

    email = payload.get('email')
    role = (payload.get('role') or '').lower()
    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        flash('Account not found.', 'error')
        return redirect(url_for('account'))
    if user.is_verified:
        flash('Account already verified. Please login.', 'info')
        return redirect(url_for('account'))

    user.is_verified = True
    db.session.commit()
    session.clear()
    set_user_session(user)

    flash('Your email has been verified. Welcome!', 'success')
    if user.role == 'lecturer':
        return redirect(url_for('lecturer_dashboard'))
    return redirect(url_for('student_classes'))
