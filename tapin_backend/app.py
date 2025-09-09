from datetime import datetime
import os
from flask import Flask, jsonify, request, send_from_directory, render_template, redirect, url_for, session, flash
from flask_cors import CORS
from dotenv import load_dotenv
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Mail, Message
import jwt
import logging

logging.basicConfig(level=logging.DEBUG)

# -------------------------------
# Local imports
# -------------------------------
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

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

# -------------------------------
# App initialization
# -------------------------------
app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static'),
    template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')
)

# Static & template folders
app.config['STATIC_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')
app.config['TEMPLATE_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')

# Database setup
instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
os.makedirs(instance_dir, exist_ok=True)
default_db_path = f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey-change-me')

# Debug & testing
app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
app.config['TESTING'] = False

# Email
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'TapIn <no-reply@example.com>')

# Extensions
mail = Mail(app)
origins = os.getenv('CORS_ORIGINS', '*').split(',') if os.getenv('CORS_ORIGINS') else ['*']
CORS(app, supports_credentials=True, origins=origins)

# DB init
db.init_app(app)
with app.app_context():
    migrate_db()

# SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# -------------------------------
# Socket.IO events
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
# Blueprints
# -------------------------------
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(classes_bp, url_prefix='/api/classes')
app.register_blueprint(attendance_bp, url_prefix='/api')
app.register_blueprint(announcements_bp, url_prefix='/api/announcements')
app.register_blueprint(student_profile_bp, url_prefix='/api/student')
app.register_blueprint(profile_bp, url_prefix='/api/profile')
app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
app.register_blueprint(reports_bp, url_prefix='/api/reports')
app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
app.register_blueprint(qr_attendance_bp, url_prefix='/api/qr')
app.register_blueprint(student_analytics_bp, url_prefix='/api/student-analytics')
app.register_blueprint(bulk_enrollment_bp, url_prefix='/api/bulk')
app.register_blueprint(schedule_bp, url_prefix='/api/schedule')
app.register_blueprint(reminders_bp, url_prefix='/api/reminders')
app.register_blueprint(backup_bp, url_prefix='/api/backup')
app.register_blueprint(visualization_bp, url_prefix='/api/visualization')

# -------------------------------
# Middleware
# -------------------------------
def login_required(f):
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def lecturer_required(f):
    def decorated(*args, **kwargs):
        if session.get('role') != 'lecturer':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def student_required(f):
    def decorated(*args, **kwargs):
        if session.get('role') != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

# -------------------------------
# Frontend routes
# -------------------------------
frontend_pages = {
    'home': 'welcome_page/index.html',
    'account': 'welcome_page/account.html',
    'lecturer_login_page': 'welcome_page/lecturer_login.html',
    'student_login_page': 'welcome_page/student_login.html',
    'lecturer_create_account_page': 'welcome_page/lecturer_create_account.html',
    'student_create_account_page': 'welcome_page/student_create_account.html',
    'lecturer_forgot_password_page': 'welcome_page/lecturer_forgot_password.html',
    'student_forgot_password_page': 'welcome_page/student_forgot_password.html',
    'reset_password_page': 'welcome_page/reset_password.html'
}
for route, template in frontend_pages.items():
    app.add_url_rule(f'/{route.replace("_page","") if "_page" in route else route}', route, lambda template=template: render_template(template))

# -------------------------------
# Dashboard routes
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
    return render_template('lecturer_page/class_page.html')

@app.route('/lecturer/take-attendance/<int:class_id>')
@lecturer_required
def lecturer_take_attendance(class_id):
    return render_template('lecturer_page/take_attendance.html')

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

# -------------------------------
# Registration/Login/Logout
# -------------------------------
@app.post('/register')
def register():
    data = request.get_json() if request.is_json else request.form
    fullname = data.get('fullname', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm = data.get('confirm_password') or data.get('confirm-password', '')
    student_id = data.get('student_id', '').strip()

    role = 'student' if student_id else 'lecturer'

    if not fullname or not email or not password:
        msg = 'Missing required fields'
        if request.is_json: return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'error'); return redirect(request.referrer or url_for('account'))
    if password != confirm:
        msg = 'Passwords do not match'
        if request.is_json: return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'error'); return redirect(request.referrer or url_for('account'))

    existing = User.query.filter_by(email=email).first()
    if existing:
        msg = 'Email already registered'
        if request.is_json: return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'error'); return redirect(request.referrer or url_for('account'))

    user = User(fullname=fullname, email=email, role=role, student_id=student_id or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['role'] = user.role
    session['user_email'] = user.email
    session['user_name'] = user.fullname
    if role == 'student': session['student_id'] = user.student_id

    msg = 'Registration successful'
    if request.is_json:
        next_url = url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_dashboard')
        return jsonify({'success': True, 'message': msg, 'redirect': next_url})
    flash(msg, 'success')
    return redirect(url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_dashboard'))

@app.post('/login')
def login_lecturer():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = User.query.filter_by(email=email, role='lecturer').first()
    if not user or not user.check_password(password):
        flash('Invalid credentials', 'error')
        return redirect(url_for('lecturer_login_page'))
    session.update({
        'user_id': user.id,
        'role': user.role,
        'user_email': user.email,
        'user_name': user.fullname
    })
    flash('Logged in successfully', 'success')
    return redirect(url_for('lecturer_dashboard'))

@app.post('/login_student')
def login_student():
    email = request.form.get('email', '').strip().lower()
    student_id = request.form.get('fullname', '').strip()
    password = request.form.get('password', '')

    user = None
    if email: user = User.query.filter_by(email=email, role='student').first()
    elif student_id: user = User.query.filter_by(student_id=student_id, role='student').first()

    if not user or not user.check_password(password):
        flash('Invalid credentials', 'error')
        return redirect(url_for('student_login_page'))

    session.update({
        'user_id': user.id,
        'role': user.role,
        'user_email': user.email,
        'user_name': user.fullname,
        'student_id': user.student_id
