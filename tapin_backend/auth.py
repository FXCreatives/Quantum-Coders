import logging
import re
from flask import Blueprint, request, jsonify, session, url_for, flash, redirect, render_template
from .models import db, User
from .utils import hash_password, verify_password, create_token, send_verification_email, create_verification_token, send_password_reset_email, create_reset_token, verify_reset_token, auth_required

auth_bp = Blueprint('auth', __name__)

@auth_bp.post('/register')
def register():
    logging.info("[REGISTER] Request received")
    try:
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
            return jsonify({'error': error_msg, 'details': 'Validation failed - check input fields'}), 400

        existing = User.query.filter_by(email=email).first()
        if existing:
            logging.warning(f"[REGISTER] Email already registered: {email}")
            return jsonify({'error': 'Email already registered', 'details': 'Account with this email exists. Try logging in or use forgot password.'}), 400

        # For students, validate student_id if role is student
        if role == 'student' and not student_id:
            logging.warning(f"[REGISTER] Missing student_id for student role: email={email}")
            return jsonify({'error': 'Student ID is required for student accounts', 'details': 'Provide your student ID during registration.'}), 400

        u = User(fullname=fullname, email=email, phone=None, student_id=student_id or None, role=role, is_verified=False, password_hash=hash_password(password))
        db.session.add(u)
        try:
            db.session.commit()
            logging.info(f"[REGISTER] User committed: id={u.id}, email={u.email}, role={role}, verified=False")
        except Exception as e:
            db.session.rollback()
            logging.error(f"[REGISTER] Commit failed: {str(e)}", exc_info=True)
            return jsonify({'error': 'Registration failed due to database error', 'details': 'Database issue - try again or contact support.'}), 500
        
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
            message = 'Registration successful. Please check your email to verify your account.'
        else:
            logging.warning(f"[REGISTER] Failed to send verification email to {u.email}")
            message = 'Registration successful but verification email failed to send. Please contact support to verify your account.'

        next_url = url_for('lecturer_initial_home') if u.role == 'lecturer' else url_for('student_initial_home')
        if request.is_json:
            response_data = {'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'message': message}
            logging.info(f"[REGISTER] Returning JSON response: {response_data}")
            return jsonify(response_data)
        else:
            flash(message, 'success')
            logging.info(f"[REGISTER] Redirecting to {next_url} for form submission")
            return redirect(next_url)
    except Exception as e:
        logging.error(f"[REGISTER] Unexpected error: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error during registration', 'details': 'Please try again or contact support.'}), 500

@auth_bp.post('/login')
def login():
    logging.info("[LOGIN] Request received")
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        email = (data.get('email') or '').strip().lower()
        password = data.get('password', '')
        student_id = (data.get('student_id') or '').strip()

        logging.info(f"[LOGIN] Attempting login with email='{email}', student_id='{student_id}'")

        if not email and not student_id:
            logging.warning("[LOGIN] No email or student_id provided")
            if request.is_json:
                return jsonify({'success': False, 'message': 'Email or Student ID required', 'details': 'Provide either email or student ID.'}), 400
            else:
                flash('Email or Student ID required', 'error')
                return redirect(url_for('account'))

        # Query user: prioritize email, fallback to student_id for students
        u = None
        role = None
        if email:
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_regex, email):
                logging.warning(f"[LOGIN] Invalid email format: {email}")
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Invalid email format', 'details': 'Email must be a valid format.'}), 400
                else:
                    flash('Invalid email format', 'error')
                    return redirect(url_for('account'))
            u = User.query.filter_by(email=email).first()
            if u:
                role = u.role
                logging.info(f"[LOGIN] Found user by email: id={u.id}, role={role}, verified={u.is_verified}")
        if not u and student_id:
            u = User.query.filter_by(student_id=student_id, role='student').first()
            if u:
                role = 'student'
                logging.info(f"[LOGIN] Found user by student_id: id={u.id}, email={u.email}, verified={u.is_verified}")

        if not u:
            logging.warning(f"[LOGIN] No user found for email='{email}' or student_id='{student_id}'")
            if request.is_json:
                return jsonify({'success': False, 'message': 'Invalid credentials', 'details': 'No account found with provided details.'}), 401  # Generic for security
            else:
                flash('Invalid credentials', 'error')
                return redirect(url_for('account'))

        if not verify_password(password, u.password_hash):
            logging.warning(f"[LOGIN] Password mismatch for user {u.id} (email={u.email})")
            if request.is_json:
                return jsonify({'success': False, 'message': 'Invalid credentials', 'details': 'Incorrect password.'}), 401  # Generic
            else:
                flash('Invalid credentials', 'error')
                return redirect(url_for('account'))

        logging.info(f"[LOGIN] Successful authentication for user {u.id} ({u.email}), role={role}, verified={u.is_verified}")

        try:
            client_token = create_token(u.id, u.role)
            logging.info(f"[LOGIN] Token created for user {u.id}")
        except Exception as e:
            logging.error(f"[LOGIN] Failed to create token for user {u.id}: {str(e)}", exc_info=True)
            if request.is_json:
                return jsonify({'success': False, 'message': 'Failed to generate session token', 'details': 'Token generation error - try again.'}), 500
            else:
                flash('Login failed due to internal error', 'error')
                return redirect(url_for('account'))

        # Set session
        session.clear()  # Clear any old session
        session['user_id'] = u.id
        session['role'] = u.role
        session['user_email'] = u.email
        session['user_name'] = u.fullname
        session['is_verified'] = u.is_verified
        if u.role == 'student':
            session['student_id'] = u.student_id
        session.permanent = True
        logging.info(f"[LOGIN] Session set for user {u.id}, role {u.role}, verified={u.is_verified}")

        # Determine redirect based on verification status
        if u.is_verified:
            if u.role == 'lecturer':
                next_url = url_for('lecturer_dashboard')
                flash_msg = 'Logged in successfully'
            else:
                next_url = url_for('student_dashboard')
                flash_msg = 'Logged in successfully'
        else:
            if u.role == 'lecturer':
                next_url = url_for('lecturer_initial_home')
                flash_msg = 'Logged in successfully. Please verify your email to access full features.'
            else:
                next_url = url_for('student_initial_home')
                flash_msg = 'Logged in successfully. Please verify your email to access full features.'

        logging.info(f"[LOGIN] Redirecting to {next_url} for role {u.role}, verified={u.is_verified}")

        if request.is_json:
            response_data = {
                'token': client_token,
                'user': {
                    'id': u.id,
                    'fullname': u.fullname,
                    'email': u.email,
                    'role': u.role,
                    'student_id': u.student_id if u.role == 'student' else None,
                    'is_verified': u.is_verified
                },
                'redirect_url': next_url,
                'success': True,
                'message': flash_msg
            }
            logging.info(f"[LOGIN] JSON response prepared")
            return jsonify(response_data)
        else:
            flash(flash_msg, 'success')
            return redirect(next_url)
    except Exception as e:
        logging.error(f"[LOGIN] Unexpected error: {str(e)}", exc_info=True)
        if request.is_json:
            return jsonify({'success': False, 'message': 'Internal server error during login', 'details': 'Please try again or contact support.'}), 500
        else:
            flash('Login failed due to server error. Please try again.', 'error')
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
    

@auth_bp.post('/forgot_password')
def forgot_password():
    logging.info("[FORGOT_PASSWORD] Request received")
    try:
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        email = (data.get('email') or '').strip().lower()

        if not email:
            logging.warning("[FORGOT_PASSWORD] No email provided")
            if request.is_json:
                return jsonify({'error': 'Email is required', 'details': 'Enter your registered email address.'}), 400
            else:
                flash('Email is required to reset password.', 'error')
                return redirect(url_for('account'))

        # Email validation
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            logging.warning(f"[FORGOT_PASSWORD] Invalid email format: {email}")
            if request.is_json:
                return jsonify({'error': 'Invalid email format', 'details': 'Please provide a valid email address.'}), 400
            else:
                flash('Invalid email format. Please check and try again.', 'error')
                return redirect(url_for('account'))

        user = User.query.filter_by(email=email).first()
        if not user:
            logging.info(f"[FORGOT_PASSWORD] User not found for email: {email} - sending generic response for security")
            # Generic response for security - don't reveal if user exists
            if request.is_json:
                return jsonify({'message': 'If an account with this email exists, a reset link has been sent. Check your inbox.'}), 200
            else:
                flash('If an account with this email exists, a reset link has been sent. Check your inbox.', 'success')
                return redirect(url_for('account'))

        try:
            reset_token = create_reset_token(user.email, user.role)
            logging.info(f"[FORGOT_PASSWORD] Reset token created for {user.email}")
        except Exception as e:
            logging.error(f"[FORGOT_PASSWORD] Failed to create reset token for {user.email}: {str(e)}", exc_info=True)
            if request.is_json:
                return jsonify({'error': 'Failed to generate reset token', 'details': 'Server error - try again or contact support.'}), 500
            else:
                flash('Failed to generate reset link. Please try again or contact support.', 'error')
                return redirect(url_for('account'))

        if send_password_reset_email(user.email, user.role, reset_token):
            logging.info(f"[FORGOT_PASSWORD] Password reset email sent successfully to {user.email}")
            if request.is_json:
                return jsonify({'message': 'Password reset email sent. Check your email for the link (valid for 1 hour).', 'details': 'Look in spam folder if not received.'}), 200
            else:
                flash('Password reset email sent. Check your email for the link (valid for 1 hour).', 'success')
                return redirect(url_for('account'))
        else:
            logging.error(f"[FORGOT_PASSWORD] Failed to send password reset email to {user.email}")
            if request.is_json:
                return jsonify({'error': 'Failed to send reset email', 'details': 'Email service issue - try again later or contact support.'}), 500
            else:
                flash('Failed to send reset email. Please try again later or contact support.', 'error')
                return redirect(url_for('account'))
    except Exception as e:
        logging.error(f"[FORGOT_PASSWORD] Unexpected error: {str(e)}", exc_info=True)
        if request.is_json:
            return jsonify({'error': 'Internal server error', 'details': 'Please try again or contact support.'}), 500
        else:
            flash('An error occurred. Please try again or contact support.', 'error')
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
    try:
        logging.debug(f"Me request method: {request.method}")
        logging.debug(f"Me request headers: {dict(request.headers)}")
        if request.method == 'GET':
            u = User.query.get(request.user_id)
            if not u:
                logging.error(f"[ME/GET] User not found: {request.user_id}")
                return jsonify({'error': 'User not found', 'details': 'Session invalid - please log in again.'}), 404
            logging.info(f"[ME/GET] Returning profile for user {request.user_id}")
            return jsonify({'id': u.id, 'fullname': u.fullname, 'email': u.email, 'phone': u.phone, 'role': u.role, 'student_id': u.student_id, 'is_verified': u.is_verified})
        else:
            data = request.get_json(force=True)
            if not data:
                logging.warning(f"[ME/PUT] No JSON data provided for user {request.user_id}")
                return jsonify({'error': 'No data provided', 'details': 'Include profile updates in request body.'}), 400
            u = User.query.get(request.user_id)
            if not u:
                logging.error(f"[ME/PUT] User not found: {request.user_id}")
                return jsonify({'error': 'User not found', 'details': 'Session invalid - please log in again.'}), 404
            updated = False
            if 'fullname' in data or 'name' in data:
                new_name = data.get('fullname') or data.get('name')
                if new_name and new_name.strip() != u.fullname:
                    u.fullname = new_name.strip()
                    updated = True
                    logging.info(f"[ME/PUT] Updated fullname to '{u.fullname}' for user {request.user_id}")
            if 'phone' in data:
                new_phone = data.strip() if data['phone'] else None
                if new_phone != u.phone:
                    u.phone = new_phone
                    updated = True
                    logging.info(f"[ME/PUT] Updated phone to '{u.phone}' for user {request.user_id}")
            if 'student_id' in data and u.role == 'student':
                new_student_id = data['student_id'].strip() if data['student_id'] else None
                if new_student_id != u.student_id:
                    u.student_id = new_student_id
                    updated = True
                    logging.info(f"[ME/PUT] Updated student_id to '{u.student_id}' for user {request.user_id}")
            if not updated:
                logging.info(f"[ME/PUT] No changes detected for user {request.user_id}")
                return jsonify({'message': 'No updates applied', 'details': 'Provided data matches current profile.'})
            db.session.commit()
            logging.info(f"[ME/PUT] Profile updated for user {request.user_id}")
            return jsonify({'message': 'Profile updated successfully', 'details': 'Changes saved.'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"[ME] Unexpected error for user {request.user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to update profile', 'details': 'Server error - please try again or contact support.'}), 500

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('account'))
