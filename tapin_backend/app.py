import sys
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from datetime import datetime, timedelta
import os
import logging
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, flash, send_from_directory
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
from tapin_backend.utils import hash_password, verify_password, create_token, broadcast_check_in

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
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail = Mail(app)
with app.app_context():
    migrate_db(app)

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
    print(f"About to register blueprint {bp.name} with prefix {prefix}")
    try:
        app.register_blueprint(bp, url_prefix=prefix)
        print(f"Successfully registered blueprint {bp.name}")
    except Exception as e:
        print(f"Failed to register blueprint {bp.name}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

# Log all registered routes for debugging
print("=== REGISTERED ROUTES ===")
for rule in app.url_map.iter_rules():
    methods = ','.join(rule.methods)
    print(f"Endpoint: {rule.endpoint}, Path: {rule}, Methods: {methods}")
print("=== END ROUTES ===")
# -------------------------------
# AUTH DECORATORS
# -------------------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
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
        logging.info(f"[LECTURER_REQUIRED] Session check for {request.path}: user_id={session.get('user_id')}, role={session.get('role')}, all_session={dict(session)}, cookies={dict(request.cookies)}")
        if 'user_id' not in session:
            logging.warning(f"[LECTURER_REQUIRED] No user_id in session for {request.path}, redirecting to account")
            flash('Please login', 'error')
            return redirect(url_for('account'))
        if session.get('role') != 'lecturer':
            logging.warning(f"[LECTURER_REQUIRED] Role {session.get('role')} != lecturer for {request.path}, redirecting to account")
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        if not session.get('is_verified', True):
            logging.warning(f"[LECTURER_REQUIRED] User {session.get('user_id')} not verified for {request.path}, redirecting to account")
            flash('Please verify your email before accessing the dashboard.', 'error')
            return redirect(url_for('account'))
        logging.info(f"[LECTURER_REQUIRED] Access granted for {request.path}")
        return f(*args, **kwargs)
    return wrapper

def student_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        logging.info(f"[STUDENT_REQUIRED] Checking session for {request.path}: full session {dict(session)}")
        if 'user_id' not in session:
            logging.warning(f"[STUDENT_REQUIRED] No user_id in session for {request.path}, redirecting to account")
            flash('Please login', 'error')
            return redirect(url_for('account'))
        if session.get('role') != 'student':
            logging.warning(f"[STUDENT_REQUIRED] Role {session.get('role')} != student for {request.path}, redirecting to account")
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        if not session.get('is_verified', True):
            logging.warning(f"[STUDENT_REQUIRED] User {session.get('user_id')} not verified for {request.path}, redirecting to account")
            flash('Please verify your email before accessing the dashboard.', 'error')
            return redirect(url_for('account'))
        logging.info(f"[STUDENT_REQUIRED] Access granted for {request.path}, user_id={session['user_id']}")
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
    logging.info(f"[SEND_RESET_LINK] Request received: email={request.get_json().get('email') if request.is_json else request.form.get('email')}, role={request.get_json().get('role') if request.is_json else request.form.get('role')}")
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = (data.get('email') or '').strip().lower()
    role = data.get('role')

    if not email or not role:
        logging.warning(f"[SEND_RESET_LINK] Missing email or role")
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
        token = make_reset_token(email, role)
        if send_reset_email(email, role, token):
            logging.info(f"[SEND_RESET_LINK] Reset email sent successfully to {email}")
            return jsonify({'message': 'Password reset link sent to your email.'}), 200
        else:
            logging.error(f"[SEND_RESET_LINK] Failed to send reset email to {email}")
            return jsonify({'error': 'Failed to send reset email. Please try again.'}), 500
    except Exception as e:
        logging.error(f"[SEND_RESET_LINK] Unexpected error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

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

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    token = data.get('token')
    role = data.get('role')
    password = data.get('password')
    confirm_password = data.get('confirm_password', data.get('confirmPassword', ''))

    if not all([token, role, password]):
        return jsonify({'success': False, 'error': 'Token, role, and password are required'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    # Password strength validation (same as registration)
    errors = []
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
        return jsonify({'success': False, 'error': ', '.join(errors)}), 400

    valid, payload = verify_reset_token(token, max_age=3600)
    if not valid:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 400

    email = payload.get('email')
    if payload.get('role') != role:
        return jsonify({'success': False, 'message': 'Token does not match role'}), 400

    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    user.password_hash = hash_password(password)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Password reset successful. You can now log in.'}), 200

# -------------------------------
# DASHBOARD ROUTES
# -------------------------------
@app.route('/lecturer/dashboard')
@lecturer_required
def lecturer_dashboard():
    return render_template('lecturer_page/lecturer_home.html')

@app.route('/lecturer/initial-home')
@lecturer_required
def lecturer_initial_home():
    return render_template('lecturer_page/lecturer_initial_home.html')

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
def get_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='tapin-reset')

def make_reset_token(email, role):
    s = get_serializer()
    return s.dumps({'email': email, 'role': role})

def verify_reset_token(token, max_age=3600):
    s = get_serializer()
    try:
        return True, s.loads(token, max_age=max_age)
    except Exception as e:  # Catch both SignatureExpired and BadSignature
        import logging
        logging.error(f"[RESET/VERIFY] Token error: {str(e)}")
        return False, {'error': 'invalid'}

def send_reset_email(email, role, token):
    import logging
    logging.basicConfig(level=logging.DEBUG)
    try:
        reset_url = url_for('reset_password_page', token=token, role=role, _external=True)
        # Check if mail is configured for development bypass
        if not current_app.config.get('MAIL_SERVER'):
            print(f"[EMAIL DEV BYPASS] Reset URL for {email} ({role}): {reset_url}")
            logging.info(f"[EMAIL DEV BYPASS] Logged reset URL to console for {email} -> {reset_url}")
            return True  # Treat as success for testing

        msg = Message(
            subject="TapIn password reset",
            recipients=[email],
            body=f"Click the link to reset your password:\n{reset_url}\nValid for 1 hour."
        )
        mail.send(msg)
        logging.info(f"[EMAIL] Sent reset link to {email} -> {reset_url}")
        return True
    except Exception as e:
        logging.error(f"[EMAIL] Failed to send reset email to {email}: {str(e)}")
        print(f"[EMAIL ERROR] Failed to send to {email}: {str(e)}. Manual reset URL: {reset_url}")
        return False


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
    is_verified = session.get('is_verified', False)
    if not is_verified:
        return jsonify({'error': 'Account not verified. Please verify your email.'}), 401
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
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = True
    reloader = not debug_mode  # Disable reloader in dev mode to prevent duplicate route additions
    app.run(host='127.0.0.1', port=port, debug=debug_mode, use_reloader=reloader)
