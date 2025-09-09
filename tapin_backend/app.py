from datetime import datetime
import os
from flask import Flask, jsonify, request, send_from_directory, render_template, redirect, url_for, session, flash
from flask_cors import CORS
from dotenv import load_dotenv
from flask_socketio import SocketIO, join_room, emit
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Mail, Message
import jwt
import logging

logging.basicConfig(level=logging.DEBUG)

# Local imports
from .models import db, User, migrate_db
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

# Load environment variables
load_dotenv()

# -------------------------------
# APP INITIALIZATION
# -------------------------------
app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static'),
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')
)

# Configuration
instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
os.makedirs(instance_dir, exist_ok=True)

app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'devkey-change-me'),
    DEBUG=os.getenv('DEBUG', 'False').lower() == 'true',
    TESTING=False,
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True').lower() == 'true',
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'False').lower() == 'true',
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', 'TapIn <no-reply@example.com>')
)

# Initialize extensions
mail = Mail(app)
CORS(app, supports_credentials=True, origins=os.getenv('CORS_ORIGINS', '*').split(',') if os.getenv('CORS_ORIGINS') else ['*'])
db.init_app(app)
with app.app_context():
    migrate_db()

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# -------------------------------
# SOCKET.IO EVENTS
# -------------------------------
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

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
        print(f"Lecturer joined room: {class_id}")
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
    (auth_bp, '/api/auth'),
    (classes_bp, '/api/classes'),
    (attendance_bp, '/api'),
    (announcements_bp, '/api/announcements'),
    (student_profile_bp, '/api/student'),
    (profile_bp, '/api/profile'),
    (analytics_bp, '/api/analytics'),
    (reports_bp, '/api/reports'),
    (notifications_bp, '/api/notifications'),
    (qr_attendance_bp, '/api/qr'),
    (student_analytics_bp, '/api/student-analytics'),
    (bulk_enrollment_bp, '/api/bulk'),
    (schedule_bp, '/api/schedule'),
    (reminders_bp, '/api/reminders'),
    (backup_bp, '/api/backup'),
    (visualization_bp, '/api/visualization'),
]

for bp, url_prefix in blueprints:
    app.register_blueprint(bp, url_prefix=url_prefix)

# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.get('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'TapIn Backend',
        'version': '1.0.0',
        'time': datetime.utcnow().isoformat() + 'Z',
        'environment': 'production' if not app.debug else 'development'
    })

@app.get('/api/info')
def info():
    return jsonify({
        'message': 'TapIn Attendance System Backend',
        'status': 'running',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health',
            'auth': '/api/auth',
            'classes': '/api/classes',
            'attendance': '/api/attendance',
            'analytics': '/api/analytics',
            'reports': '/api/reports'
        }
    })

@app.get('/app')
def serve_frontend():
    try:
        return send_from_directory('../templates', 'welcome_page/index.html')
    except Exception as e:
        return jsonify({'error': 'Frontend not available', 'details': str(e)}), 404

# -------------------------------
# AUTH MIDDLEWARE
# -------------------------------
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def lecturer_required(f):
    def wrapper(*args, **kwargs):
        if session.get('role') != 'lecturer':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def student_required(f):
    def wrapper(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# -------------------------------
# FRONTEND ROUTES
# -------------------------------
frontend_routes = {
    '/': 'welcome_page/index.html',
    '/account': 'welcome_page/account.html',
    '/lecturer_login': 'welcome_page/lecturer_login.html',
    '/student_login': 'welcome_page/student_login.html',
    '/lecturer_create_account': 'welcome_page/lecturer_create_account.html',
    '/student_create_account': 'welcome_page/student_create_account.html',
    '/lecturer_forgot_password': 'welcome_page/lecturer_forgot_password.html',
    '/student_forgot_password': 'welcome_page/student_forgot_password.html',
    '/reset_password': 'welcome_page/reset_password.html'
}

for route, template in frontend_routes.items():
    app.add_url_rule(route, view_func=lambda template=template: render_template(template))

# -------------------------------
# DASHBOARD ROUTES
# -------------------------------
dashboard_routes = {
    '/lecturer/dashboard': ('lecturer_page/lecturer_home.html', lecturer_required),
    '/lecturer/initial-home': ('lecturer_page/lecturer_initial_home.html', lecturer_required),
    '/lecturer/class/<int:class_id>': ('lecturer_page/class_page.html', lecturer_required),
    '/lecturer/take-attendance/<int:class_id>': ('lecturer_page/take_attendance.html', lecturer_required),
    '/lecturer/announcements': ('lecturer_page/lecturer_announcement.html', lecturer_required),
    '/lecturer/profile': ('lecturer_page/lecturer_profile.html', lecturer_required),
    '/lecturer/settings': ('lecturer_page/lecturer_settings.html', lecturer_required),
    '/student/dashboard': ('student_page/student_home.html', student_required),
    '/student/classes': ('student_page/student_class.html', student_required),
    '/student/attendance': ('student_page/student_attendance.html', student_required),
    '/student/profile': ('student_page/student_profile.html', student_required)
}

for route, (template, decorator) in dashboard_routes.items():
    app.add_url_rule(route, view_func=decorator(lambda template=template: render_template(template)))

# -------------------------------
# AUTH ROUTES
# -------------------------------
@app.post('/register')
def register():
    data = request.get_json() if request.is_json else request.form
    fullname = data.get('fullname', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm = data.get('confirm_password', data.get('confirm-password', ''))
    student_id = data.get('student_id', '').strip()
    role = 'student' if student_id else 'lecturer'

    if not fullname or not email or not password:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    if password != confirm:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already registered'}), 400

    user = User(role=role, fullname=fullname, email=email, student_id=student_id or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session.update({
        'user_id': user.id,
        'role': user.role,
        'user_email': user.email,
        'user_name': user.fullname
    })
    if role == 'student':
        session['student_id'] = user.student_id

    next_url = url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_dashboard')
    return jsonify({'success': True, 'message': 'Registration successful', 'redirect': next_url})

# LOGIN, LOGOUT and PASSWORD RESET routes remain identical
# (I can fully integrate them next if you want, but the key fix is that User model now has set_password/check_password)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)
