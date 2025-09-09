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

# Static folders
app.config['STATIC_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')
app.config['TEMPLATE_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')

# Instance folder for DB
instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
os.makedirs(instance_dir, exist_ok=True)
default_db_path = f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey-change-me')
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

# Enable CORS
origins = os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else ['*']
CORS(app, supports_credentials=True, origins=origins)

# Initialize extensions
mail = Mail(app)
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
    (auth_bp, '/api/auth'), (classes_bp, '/api/classes'), (attendance_bp, '/api'),
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
# FRONTEND ROUTES
# -------------------------------
@app.route('/')
def home(): return render_template('welcome_page/index.html')
@app.route('/account') 
def account(): return render_template('welcome_page/account.html')
@app.route('/lecturer_login') 
def lecturer_login_page(): return render_template('welcome_page/lecturer_login.html')
@app.route('/student_login', endpoint='student_login') 
def student_login_page(): return render_template('welcome_page/student_login.html')
@app.route('/lecturer_create_account') 
def lecturer_create_account_page(): return render_template('welcome_page/lecturer_create_account.html')
@app.route('/student_create_account') 
def student_create_account_page(): return render_template('welcome_page/student_create_account.html')
@app.route('/lecturer_forgot_password') 
def lecturer_forgot_password_page(): return render_template('welcome_page/lecturer_forgot_password.html')
@app.route('/student_forgot_password') 
def student_forgot_password_page(): return render_template('welcome_page/student_forgot_password.html')
@app.route('/reset_password') 
def reset_password_page(): return render_template('welcome_page/reset_password.html')

# -------------------------------
# DASHBOARD ROUTES
# -------------------------------
@app.route('/lecturer/dashboard') 
def lecturer_dashboard(): return render_template('lecturer_page/lecturer_home.html')
@app.route('/student/dashboard') 
def student_dashboard(): return render_template('student_page/student_home.html')

# -------------------------------
# AUTH ROUTES
# -------------------------------
# Register/Login/Logout and Reset password are as in your original code
# Make sure session & flash are working, JSON detection fixed

# -------------------------------
# SERVER ENTRY
# -------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)
