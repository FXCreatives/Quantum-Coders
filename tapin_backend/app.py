from datetime import datetime
import os
import logging
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, flash, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from flask_socketio import SocketIO, join_room, emit
import jwt
import re

# Local imports
from .models import db, User, Course, Enrollment, migrate_db
from .auth import auth_bp
from .routes_classes import classes_bp
from .routes_attendance import attendance_bp
from .routes_announcements import announcements_bp
from .routes_student_profile import student_profile_bp
from .routes_profile import profile_bp
from .routes_analytics import analytics_bp
from .routes_reports import reports_bp
from .routes_notifications import notifications_bp
from .routes_qr_attendance import qr_attendance_bp
from .routes_student_analytics import student_analytics_bp
from .routes_bulk_enrollment import bulk_enrollment_bp
from .routes_schedule import schedule_bp
from .routes_reminders import reminders_bp
from .routes_backup import backup_bp
from .routes_visualization import visualization_bp
from .utils import hash_password, verify_password, create_token

logging.basicConfig(level=logging.DEBUG)
load_dotenv()

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static'),
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')
)

# Config
instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
os.makedirs(instance_dir, exist_ok=True)
default_db_path = f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey-change-me')
app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
app.config['TESTING'] = False

# Enable CORS
origins = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else ['*', 'https://tapin-attendance-app.onrender.com', 'http://localhost:3000', 'http://localhost:5000', 'http://127.0.0.1:5000']
CORS(app, supports_credentials=True, origins=origins)

# Initialize extensions
db.init_app(app)
with app.app_context():
    migrate_db(app)

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

def broadcast_check_in(class_id, student):
    socketio.emit('student_checked_in', {
        'name': student['name'],
        'student_id': student['student_id'],
        'check_in_time': student['check_in_time']
    }, to=str(class_id))

# -------------------------------
# BLUEPRINTS
# -------------------------------
blueprints = [
    (auth_bp, '/api/auth'), (profile_bp, '/api/profile'), (classes_bp, '/api/classes'), (attendance_bp, '/api'),
    (announcements_bp, '/api/announcements'), (student_profile_bp, '/api/student'),
    (profile_bp, '/api/profile'), (analytics_bp, '/api/analytics'), (reports_bp, '/api/reports'),
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
            flash('Please login', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    return wrapper

def lecturer_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'lecturer':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    return wrapper

def student_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
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
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='tapin-reset')

def make_reset_token(email, role):
    s = get_serializer()
    return s.dumps({'email': email, 'role': role})

def verify_reset_token(token, max_age=3600):
    s = get_serializer()
    try:
        return True, s.loads(token, max_age=max_age)
    except SignatureExpired:
        return False, {'error': 'expired'}
    except BadSignature:
        return False, {'error': 'invalid'}

def send_reset_email(email, role, token):
    reset_url = url_for('reset_password_page', token=token, role=role, _external=True)
    msg = Message(
        subject="TapIn password reset",
        recipients=[email],
        body=f"Click the link to reset your password:\n{reset_url}\nValid for 1 hour."
    )
    mail.send(msg)
    logging.info(f"[EMAIL] Sent reset link to {email} -> {reset_url}")

# Registration route
@app.route('/register', methods=['POST'])
def register():
    # Detect JSON or form
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    fullname = (data.get('fullname') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    confirm = data.get('confirm-password', '')
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
    db.session.commit()

    token = create_token(u.id, u.role)

    # Set session for fallback
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    if role == 'student':
        session['student_id'] = u.student_id

    next_url = url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_dashboard')
    return jsonify({'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'message': 'Registration successful'})

# Login route
@app.route('/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    student_id = data.get('student_id', '')

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
    
    if not u or not verify_password(password, u.password_hash):
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    token = create_token(u.id, u.role)

    # Set session for fallback
    session['user_id'] = u.id
    session['role'] = u.role
    session['user_email'] = u.email
    session['user_name'] = u.fullname
    if u.role == 'student':
        session['student_id'] = u.student_id

    next_url = url_for('lecturer_dashboard') if u.role == 'lecturer' else url_for('student_dashboard')
    return jsonify({'token': token, 'user': {'id': u.id, 'fullname': u.fullname, 'email': u.email, 'role': u.role, 'student_id': u.student_id}, 'redirect_url': next_url, 'success': True, 'message': 'Logged in successfully'})

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'success')
    return redirect(url_for('account'))

# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.route('/api/health')
def health_check():
    print(f"[APP] Health check hit - session: {'user_id' in session}")
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat()})

# -------------------------------
# SERVE FRONTEND
# -------------------------------
@app.route('/app/<path:path>')
def serve_app(path):
    return send_from_directory(os.path.join(app.root_path, '../static'), path)

# -------------------------------
# SERVER ENTRY
# -------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
