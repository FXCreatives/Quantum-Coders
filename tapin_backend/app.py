import sys
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from datetime import datetime, timedelta
import os
import logging
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, flash, send_from_directory, current_app
from flask_mail import Mail, Message
from flask_cors import CORS
from dotenv import load_dotenv
from flask_socketio import SocketIO, join_room, emit
import jwt
import re

# Local imports
from tapin_backend.models import db, User, Course, Enrollment, migrate_db
from tapin_backend.auth import auth_bp
from tapin_backend.routes_classes import classes_bp
from tapin_backend.routes_attendance import attendance_bp
from tapin_backend.routes_announcements import announcements_bp
from tapin_backend.routes_student_profile import student_profile_bp
from tapin_backend.routes_profile import profile_bp
from tapin_backend.routes_analytics import analytics_bp
from tapin_backend.routes_reports import reports_bp
from tapin_backend.routes_notifications import notifications_bp
from tapin_backend.routes_qr_attendance import qr_attendance_bp
from tapin_backend.routes_student_analytics import student_analytics_bp
from tapin_backend.routes_bulk_enrollment import bulk_enrollment_bp
from tapin_backend.routes_schedule import schedule_bp
from tapin_backend.routes_reminders import reminders_bp
from tapin_backend.routes_backup import backup_bp
from tapin_backend.routes_visualization import visualization_bp
from tapin_backend.utils import hash_password, verify_password, create_token, broadcast_check_in, verify_verification_token, set_user_session, create_reset_token, send_password_reset_email, verify_reset_token

logging.basicConfig(level=logging.DEBUG)
load_dotenv()


app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, 'static'),
    template_folder=os.path.join(BASE_DIR, 'templates')
)

# Config
instance_dir = os.path.join(BASE_DIR, 'instance')
os.makedirs(instance_dir, exist_ok=True)
default_db_path = f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey-change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['JWT_TOKEN_LOCATION'] = ["cookies", "headers"]
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
app.config['TESTING'] = False

# Enable CORS
origins = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else ['*', 'https://tapin-attendance-app.onrender.com', 'http://localhost:3000', 'http://localhost:5000', 'http://127.0.0.1:5000']
CORS(app, supports_credentials=True, origins=origins)

# Initialize extensions
db.init_app(app)
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'myapp@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'myapp@gmail.com')
mail = Mail(app)
if not app.config['MAIL_PASSWORD']:
    logging.warning("[APP START] MAIL_PASSWORD not set in .env. Verification and reset emails will fail unless using dev bypass. Please set MAIL_PASSWORD=your_gmail_app_password in .env")

# TODO: Create .env file in root with: MAIL_PASSWORD=your_gmail_app_password
# Generate app password: Google Account > Security > 2-Step Verification > App passwords > Select 'Mail' and 'Other' (name: TapIn)
# Do NOT use your regular Gmail password; app passwords are required for SMTP with 2FA.
with app.app_context():
    migrate_db(app)
    # Seed test users if no users exist
    if User.query.count() == 0:
        from .utils import hash_password
        # Test Lecturer
        lecturer = User(
            fullname='Test Lecturer',
            email='lecturer@test.com',
            role='lecturer',
            password_hash=hash_password('TestPass123!'),
            is_verified=True  # Set verified to skip verification step
        )
        db.session.add(lecturer)
        
        # Test Student
        student = User(
            fullname='Test Student',
            email='student@test.com',
            student_id='STU001',
            role='student',
            password_hash=hash_password('TestPass123!'),
            is_verified=True  # Set verified to skip verification step
        )
        db.session.add(student)
        
        db.session.commit()
        logging.info("Test users seeded: lecturer@test.com and student@test.com (password: TestPass123!)")

from flask_jwt_extended import JWTManager
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# -------------------------------
# SOCKET.IO EVENTS
# -------------------------------
@socketio.on('connect')
def handle_connect():
    logging.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logging.info('Client disconnected')

@socketio.on('join_class')
def handle_join_class(data):
    token = data.get('token')
    class_id = data.get('classId')
    if not token or not class_id:
        emit('error', {'message': 'Missing token or class ID'})
        return
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        join_room(class_id)
        logging.info(f"Joined room: {class_id}")
        emit('joined', {'classId': class_id})
    except jwt.ExpiredSignatureError:
        emit('error', {'message': 'Token expired'})
    except jwt.InvalidTokenError:
        emit('error', {'message': 'Invalid token'})


# -------------------------------
# BLUEPRINTS
# -------------------------------
blueprints = [
    (auth_bp, '/api/auth'), (profile_bp, '/api/profile'), (classes_bp, '/api/classes'), (attendance_bp, '/api'),
    (announcements_bp, '/api/announcements'), (student_profile_bp, '/api/student'),
    (analytics_bp, '/api/analytics'), (reports_bp, '/api/reports'),
    (notifications_bp, '/api/notifications'), (qr_attendance_bp, '/api/qr'),
    (student_analytics_bp, '/api/student-analytics'), (bulk_enrollment_bp, '/api/bulk'),
    (schedule_bp, '/api/schedule'), (reminders_bp, '/api/reminders'), (backup_bp, '/api/backup'),
    (visualization_bp, '/api/visualization')
]
for bp, prefix in blueprints:
    app.register_blueprint(bp, url_prefix=prefix)

# -------------------------------
# AUTH DECORATORS
# -------------------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Please login to access this resource'}), 401
            flash('Please login', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    return wrapper

def lecturer_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        import logging
        logging.basicConfig(level=logging.DEBUG)
        ip = request.remote_addr
        ua = request.user_agent.string if request.user_agent else 'unknown'
        full_session = dict(session)
        logging.info(f"[LECTURER_REQUIRED] Entry for {request.path}: user_id={session.get('user_id')}, role={session.get('role')}, is_verified={session.get('is_verified')}, ip={ip}, ua={ua}, full_session={full_session}")
        if 'user_id' not in session:
            logging.warning(f"[LECTURER_REQUIRED] No user_id in session for {request.path}, returning 401")
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Please login as lecturer'}), 401
            flash('Please login', 'error')
            return redirect(url_for('account'))
        if session.get('role') != 'lecturer':
            logging.warning(f"[LECTURER_REQUIRED] Role {session.get('role')} != lecturer for {request.path}, returning 403")
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Access denied: lecturer required'}), 403
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        current_path = request.path
        is_verified = session.get('is_verified', False)
        logging.info(f"[LECTURER_REQUIRED] Verification check: current_path={current_path}, is_verified={is_verified}, full_session={dict(session)}")
        if not is_verified:
            if current_path not in ['/lecturer/initial-home', '/lecturer/dashboard']:
                logging.info(f"[LECTURER_REQUIRED] Unverified lecturer on {current_path}, redirecting to initial_home")
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Please verify your email'}), 403
                flash('Please verify your email before accessing the dashboard', 'warning')
                return redirect(url_for('lecturer_initial_home'))
            else:
                logging.info(f"[LECTURER_REQUIRED] Unverified lecturer on {current_path}, allowing access")
        else:
            logging.info(f"[LECTURER_REQUIRED] Verified lecturer on {current_path}, allowing access")
        logging.info(f"[LECTURER_REQUIRED] Access granted for {request.path}")
        return f(*args, **kwargs)
    return wrapper

def student_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        import logging
        ip = request.remote_addr
        ua = request.user_agent.string if request.user_agent else 'unknown'
        full_session = dict(session)
        logging.info(f"[STUDENT_REQUIRED] Entry for {request.path}: user_id={session.get('user_id')}, role={session.get('role')}, is_verified={session.get('is_verified')}, ip={ip}, ua={ua}, full_session={full_session}")
        if 'user_id' not in session:
            logging.warning(f"[STUDENT_REQUIRED] No user_id in session for {request.path}, returning 401")
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Please login as student'}), 401
            flash('Please login', 'error')
            return redirect(url_for('account'))
        if session.get('role') != 'student':
            logging.warning(f"[STUDENT_REQUIRED] Role {session.get('role')} != student for {request.path}, returning 403")
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Access denied: student required'}), 403
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        current_path = request.path
        is_verified = session.get('is_verified', False)
        if not is_verified:
            if current_path != '/student/initial-home':
                logging.info(f"[STUDENT_REQUIRED] Unverified student on {current_path}, redirecting to initial_home")
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Please verify your email'}), 403
                flash('Please verify your email to access full features', 'warning')
                return redirect(url_for('student_initial_home'))
            else:
                logging.info(f"[STUDENT_REQUIRED] Unverified student on initial_home, allowing limited access with prompt")
        else:
            logging.info(f"[STUDENT_REQUIRED] Verified student on {current_path}, allowing full access")
        logging.info(f"[STUDENT_REQUIRED] Access granted for {request.path}")
        return f(*args, **kwargs)
    return wrapper

# -------------------------------
# FRONTEND ROUTES
# -------------------------------
@app.route('/')
def home():
    return render_template('welcome_page/index.html')

@app.route('/account')
def account():
    return render_template('welcome_page/account.html')

@app.route('/lecturer_login')
def lecturer_login_page():
    return render_template('welcome_page/lecturer_login.html')

@app.route('/student_login')
def student_login_page():
    return render_template('welcome_page/student_login.html')

@app.route('/lecturer_create_account')
def lecturer_create_account_page():
    return render_template('welcome_page/lecturer_create_account.html')

@app.route('/student_create_account')
def student_create_account_page():
    return render_template('welcome_page/student_create_account.html')

@app.route('/lecturer_forgot_password')
def lecturer_forgot_password_page():
    return render_template('welcome_page/lecturer_forgot_password.html')

@app.route('/student_forgot_password')
def student_forgot_password_page():
    return render_template('welcome_page/student_forgot_password.html')

@app.route('/reset_password')
def reset_password_page():
    token = request.args.get('token')
    role = request.args.get('role')
    if not token or not role:
        flash('Invalid reset link', 'error')
        return redirect(url_for('account'))
    return render_template('welcome_page/reset_password.html', token=token, role=role)

@app.route('/api/send-reset-link', methods=['POST'])
def send_reset_link():
    logging.info("[SEND_RESET_LINK] Request received")
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = (data.get('email') or '').strip().lower()
    role = data.get('role')

    logging.info(f"[SEND_RESET_LINK] Parsed data: email={email}, role={role}")

    if not email or not role:
        logging.warning(f"[SEND_RESET_LINK] Missing email or role: email={bool(email)}, role={role}")
        return jsonify({'error': 'Email and role are required'}), 400

    # Email validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, email):
        logging.warning(f"[SEND_RESET_LINK] Invalid email format: {email}")
        return jsonify({'error': 'Invalid email format'}), 400

    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        logging.info(f"[SEND_RESET_LINK] No user found for {email}, {role} - security response")
        # Don't reveal if user exists for security
        return jsonify({'message': 'If an account with this email exists, a reset link has been sent.'}), 200

    try:
        token = create_reset_token(email, role)
        logging.info(f"[SEND_RESET_LINK] Reset token created for {email}")
    except Exception as e:
        logging.error(f"[SEND_RESET_LINK] Failed to create reset token for {email}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to generate reset link'}), 500

    if send_password_reset_email(email, role, token):
        logging.info(f"[SEND_RESET_LINK] Reset email sent successfully to {email}")
        return jsonify({'message': 'Password reset link sent to your email.'}), 200
    else:
        logging.error(f"[SEND_RESET_LINK] Failed to send reset email to {email}")
        return jsonify({'error': 'Failed to send reset email. Please try again.'}), 500

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    logging.info("[RESET_PASSWORD] Request received")
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    token = data.get('token')
    role = data.get('role')
    password = data.get('password')
    confirm_password = data.get('confirm_password', data.get('confirmPassword', ''))

    logging.info(f"[RESET_PASSWORD] Parsed data: token_len={len(token) if token else 0}, role={role}, password_len={len(password) if password else 0}, confirm_len={len(confirm_password) if confirm_password else 0}")

    if not all([token, role, password]):
        logging.warning(f"[RESET_PASSWORD] Missing required fields: token={bool(token)}, role={bool(role)}, password={bool(password)}")
        return jsonify({'success': False, 'error': 'Token, role, and password are required'}), 400

    if password != confirm_password:
        logging.warning(f"[RESET_PASSWORD] Passwords do not match for role={role}")
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    # Password strength validation (same as registration)
    errors = []
    if len(password) < 8:
        errors.append('Password must be at least 8 characters long')
        logging.warning(f"[RESET_PASSWORD] Password too short: length={len(password)}")
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter')
        logging.warning("[RESET_PASSWORD] No uppercase in password")
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter')
        logging.warning("[RESET_PASSWORD] No lowercase in password")
    if not re.search(r'\d', password):
        errors.append('Password must contain at least one digit')
        logging.warning("[RESET_PASSWORD] No digit in password")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Password must contain at least one special character')
        logging.warning("[RESET_PASSWORD] No special char in password")

    if errors:
        error_msg = ', '.join(errors)
        logging.warning(f"[RESET_PASSWORD] Password validation errors: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 400

    try:
        valid, payload = verify_reset_token(token, max_age=3600)
        logging.info(f"[RESET_PASSWORD] Token verification: valid={valid}, payload_role={payload.get('role') if valid else 'N/A'}")
    except Exception as e:
        logging.error(f"[RESET_PASSWORD] Token verification failed: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Invalid token'}), 400

    if not valid:
        logging.warning("[RESET_PASSWORD] Invalid or expired token")
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 400

    email = payload.get('email')
    if payload.get('role') != role:
        logging.warning(f"[RESET_PASSWORD] Token role mismatch: expected={role}, got={payload.get('role')}")
        return jsonify({'success': False, 'message': 'Token does not match role'}), 400

    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        logging.warning(f"[RESET_PASSWORD] User not found: email={email}, role={role}")
        return jsonify({'success': False, 'message': 'User not found'}), 404

    try:
        user.password_hash = hash_password(password)
        db.session.commit()
        logging.info(f"[RESET_PASSWORD] Password updated and committed for user {user.id} (email={email})")

        # Auto-login after successful password reset
        session.clear()
        set_user_session(user)
        logging.info(f"[RESET_PASSWORD] Auto-login session set for user {user.id} (email={email}, role={role})")

        # Generate token and response like login
        token = create_token(user.id, user.role)
        if role == 'lecturer':
            next_url = url_for('lecturer_initial_home') if not user.is_verified else url_for('lecturer_dashboard')
        else:
            next_url = url_for('student_initial_home') if not user.is_verified else url_for('student_dashboard')
        response_data = {
            'token': token,
            'user': {
                'id': user.id,
                'fullname': user.fullname,
                'email': user.email,
                'role': user.role,
                'student_id': user.student_id,
                'is_verified': user.is_verified
            },
            'redirect_url': next_url,
            'success': True,
            'message': 'Password reset successful. You are now logged in.'
        }
        logging.info(f"[RESET_PASSWORD] Auto-login response prepared for {email}")
        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        logging.error(f"[RESET_PASSWORD] Failed to update password for {email}: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'Failed to update password'}), 500

@app.route('/api/validate-token')
def validate_token():
    token = request.args.get('token')
    role = request.args.get('role')
    if not token or not role:
        return jsonify({'valid': False, 'message': 'Missing token or role'}), 400

    valid, payload = verify_reset_token(token, max_age=3600)
    if valid and payload.get('email') and payload.get('role') == role:
        return jsonify({'valid': True})
    else:
        return jsonify({'valid': False, 'message': 'Invalid or expired token'})


# -------------------------------
# DASHBOARD ROUTES
# -------------------------------
@app.route('/lecturer/dashboard')
@lecturer_required
def lecturer_dashboard():
    logging.info(f"[LECTURER_DASHBOARD] Rendering lecturer_home.html for user_id={session.get('user_id')}, is_verified={session.get('is_verified')}, full_session={dict(session)}")
    return render_template('lecturer_page/lecturer_home.html')

@app.route('/lecturer/initial-home')
@lecturer_required
def lecturer_initial_home():
    return render_template('lecturer_page/lecturer_verify_notice.html')

@app.route('/lecturer/class/<int:class_id>')
@lecturer_required
def lecturer_class_page(class_id):
    return render_template('lecturer_page/class_page.html', class_id=class_id)

@app.route('/lecturer/take-attendance/<int:class_id>')
@lecturer_required
def lecturer_take_attendance(class_id):
    return render_template('lecturer_page/take_attendance.html', class_id=class_id)

@app.route('/lecturer/announcements')
@lecturer_required
def lecturer_announcements():
    return render_template('lecturer_page/lecturer_announcement.html')

@app.route('/lecturer/profile')
@lecturer_required
def lecturer_profile():
    return render_template('lecturer_page/lecturer_profile.html')

@app.route('/lecturer/settings')
@lecturer_required
def lecturer_settings():
    return render_template('lecturer_page/lecturer_settings.html')

@app.route('/lecturer/about')
@lecturer_required
def lecturer_about():
    return render_template('lecturer_page/lecturer_about.html')

@app.route('/lecturer/notification')
@lecturer_required
def lecturer_notification():
    return render_template('lecturer_page/lecturer_notification.html')

@app.route('/lecturer/attendance-history')
@lecturer_required
def lecturer_attendance_history():
    return render_template('lecturer_page/attendance_history.html')

@app.route('/student/initial-home')
@student_required
def student_initial_home():
    logging.info(f"[STUDENT_INITIAL_HOME] Rendering initial home for unverified student user_id={session.get('user_id')}, session={dict(session)}")
    return render_template('student_page/student_initial_home.html')

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    logging.info(f"[STUDENT_DASHBOARD] Rendering dashboard for user_id={session.get('user_id')}, session={dict(session)}")
    return render_template('student_page/student_home.html')

@app.route('/student/classes')
@student_required
def student_classes():
    return render_template('student_page/student_class.html')

@app.route('/student/attendance')
@student_required
def student_attendance():
    return render_template('student_page/student_attendance.html')

@app.route('/student/profile')
@student_required
def student_profile():
    return render_template('student_page/student_profile.html')

@app.route('/student/about')
@student_required
def student_about():
    return render_template('student_page/student_about.html')

@app.route('/student/settings')
@student_required
def student_settings():
    return render_template('student_page/student_settings.html')

@app.route('/student/notification')
@student_required
def student_notification():
    return render_template('student_page/student_notification.html')

@app.route('/student/attendance-history')
@student_required
def student_attendance_history():
    return render_template('student_page/student_attendance_history.html')

@app.route('/student/class-detail/<int:class_id>')
@student_required
def student_class_detail(class_id):
    return render_template('student_page/student_class_detail.html', class_id=class_id)

# -------------------------------
# AUTHENTICATION
# -------------------------------


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('account'))


# Get fresh token from session for client-side use
@app.route('/api/get_token', methods=['GET'])
@login_required
def get_token():
    user_id = session['user_id']
    role = session['role']
    token = create_token(user_id, role)
    return jsonify({'token': token})

# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.route('/api/health')
def health_check():
    session_info = {'has_user_id': 'user_id' in session, 'role': session.get('role'), 'user_id': session.get('user_id')}
    logging.info(f"[HEALTH] Check hit - session info: {session_info}, full session: {dict(session)}")
    return jsonify({'status': 'ok', 'authenticated': 'user_id' in session, 'session': session_info, 'time': datetime.utcnow().isoformat()})


# -------------------------------
# GLOBAL ERROR HANDLER
# -------------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    logging.error(f"[GLOBAL ERROR] Unhandled exception: {str(e)}", exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500
    else:
        flash('An unexpected error occurred', 'error')
        return render_template('welcome_page/error.html'), 500  # Assume a generic error template exists or redirect

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    else:
        flash('Page not found', 'error')
        return redirect(url_for('home')), 404

@app.errorhandler(403)
def forbidden(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Forbidden'}), 403
    else:
        flash('Access denied', 'error')
        return redirect(url_for('account')), 403

@app.errorhandler(401)
def unauthorized(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Unauthorized'}), 401
    else:
        flash('Please log in', 'error')
        return redirect(url_for('account')), 401

# -------------------------------
# SERVE FRONTEND
# -------------------------------
@app.route('/app/<path:path>')
def serve_app(path):
    return send_from_directory(os.path.join(BASE_DIR, 'static'), path)

# -------------------------------
# SERVER ENTRY
# -------------------------------
@app.route('/join_class/<token>')
def join_via_link(token):
    from tapin_backend.models import db, Course, Enrollment, User
    cls = Course.query.filter_by(join_code=token).first()
    if not cls:
        flash('Invalid join link.', 'error')
        return redirect(url_for('account'))
    
    if 'user_id' not in session or session.get('role') != 'student':
        # Redirect to login with return_url
        return_url = f"{request.url}"
        return redirect(url_for('student_login_page', return_url=return_url))
    
    # Check if already enrolled
    existing = Enrollment.query.filter_by(class_id=cls.id, student_id=session['user_id']).first()
    if existing:
        flash('You are already enrolled in this class.', 'success')
        return redirect(url_for('student_classes'))
    
    # Enroll
    enr = Enrollment(class_id=cls.id, student_id=session['user_id'])
    db.session.add(enr)
    db.session.commit()
    flash('Successfully joined the class!', 'success')
    return redirect(url_for('student_classes'))



@app.route('/verify-email/<token>')
def verify_email_route(token):
    logging.info(f"[VERIFY_EMAIL] Route hit with token (len={len(token) if token else 0})")
    valid, payload = verify_verification_token(token, max_age=3600)
    logging.info(f"[VERIFY_EMAIL] Token valid={valid}, payload={payload}")
    if not valid:
        logging.warning(f"[VERIFY_EMAIL] Invalid token, payload error={payload.get('error') if isinstance(payload, dict) else 'N/A'}")
        flash('Verification link is invalid or expired. Please request a new one.', 'error')
        return redirect(url_for('account'))

    email = payload.get('email')
    role = (payload.get('role') or '').lower()
    logging.info(f"[VERIFY_EMAIL] Extracted email={email}, role={role}")
    if role not in ('lecturer', 'student') or not email:
        flash('Verification link is invalid. Please request a new one.', 'error')
        return redirect(url_for('account'))

    user = User.query.filter_by(email=email.lower(), role=role).first()
    logging.info(f"[VERIFY_EMAIL] User query result: found={user is not None}, user_role={getattr(user, 'role', 'N/A') if user else 'N/A'}, is_verified={getattr(user, 'is_verified', 'N/A') if user else 'N/A'}")
    if not user:
        flash('Verification link is invalid or the account does not exist.', 'error')
        return redirect(url_for('account'))

    if user.is_verified:
        logging.warning(f"[VERIFY_EMAIL] User condition failed: user={user is not None}, already_verified={True}")
        flash('Account already verified. Please login.', 'info')
        return redirect(url_for('account'))

    user.is_verified = True
    db.session.commit()
    logging.info(f"[VERIFY_EMAIL] DB commit successful, new is_verified=True for user_id={user.id}")

    session.clear()
    set_user_session(user)
    logging.info(f"[VERIFY_EMAIL] Session set for verified user {user.id}, role {user.role}")

    # Generate JWT token for frontend bootstrap
    try:
        auth_token = create_token(user.id, user.role)
        logging.info(f"[VERIFY_EMAIL] Generated auth token for user {user.id}, length={len(auth_token)}")
    except Exception as e:
        logging.error(f"[VERIFY_EMAIL] Failed to generate token for user {user.id}: {str(e)}", exc_info=True)
        auth_token = None

    flash('Your email has been verified. Welcome to your dashboard!', 'success')

    # Redirect to dashboard with token
    if user.role == 'lecturer':
        redirect_url = url_for('lecturer_dashboard', auth_token=auth_token) if auth_token else url_for('lecturer_dashboard')
        logging.info(f"[VERIFY_EMAIL] Redirecting to lecturer_dashboard with token for verified user {user.id}")
        return redirect(redirect_url)
    else:
        redirect_url = url_for('student_dashboard', auth_token=auth_token) if auth_token else url_for('student_dashboard')
        logging.info(f"[VERIFY_EMAIL] Redirecting to student_dashboard with token for verified user {user.id}")
        return redirect(redirect_url)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = True
    reloader = not debug_mode  # Disable reloader in dev mode to prevent duplicate route additions
    app.run(host='127.0.0.1', port=port, debug=debug_mode, use_reloader=reloader)
