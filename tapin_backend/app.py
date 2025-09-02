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

# Local imports
from .models import db, migrate_db
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
app = Flask(__name__,
             static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static'),
             template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates'))

# Static files configuration for production
app.config['STATIC_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')
app.config['TEMPLATE_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates')

# Use instance directory for database consistency
instance_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance')
os.makedirs(instance_dir, exist_ok=True)
default_db_path = f"sqlite:///{os.path.join(instance_dir, 'tapin.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey-change-me')

# Production settings
app.config['DEBUG'] = os.getenv('DEBUG', 'False').lower() == 'true'
app.config['TESTING'] = False

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'TapIn <no-reply@example.com>')

# Initialize extensions
mail = Mail(app)

# Enable CORS
origins = os.getenv('CORS_ORIGINS', '*').split(',') if os.getenv('CORS_ORIGINS') else ['*']
CORS(app, supports_credentials=True, origins=origins)

# Initialize DB
db.init_app(app)
with app.app_context():
    migrate_db()

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# -------------------------------
# SOCKET.IO EVENT HANDLERS
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

# -------------------------------
# HELPER FUNCTION
# -------------------------------
def broadcast_check_in(class_id, student):
    socketio.emit('student_checked_in', {
        'name': student['name'],
        'student_id': student['student_id'],
        'check_in_time': student['check_in_time']
    }, to=str(class_id))

# -------------------------------
# BLUEPRINTS
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
# HEALTH CHECK ROUTE
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

@app.get('/api')
def root():
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
        return jsonify({
            'error': 'Frontend not available',
            'message': 'Please access the frontend through the correct URL',
            'details': str(e)
        }), 404

# -------------------------------
# AUTHENTICATION MIDDLEWARE
# -------------------------------
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def lecturer_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'lecturer':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def student_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('account'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

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
    return render_template('welcome_page/reset_password.html')

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
# AUTHENTICATION ROUTES
# -------------------------------
@app.post('/register')
def register():
    # Detect JSON or form data
    if request.is_json:
        data = request.get_json()
        fullname = data.get('fullname', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm = data.get('confirm-password', '')
        student_id = data.get('student_id', '').strip()
    else:
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm-password', '')
        student_id = request.form.get('student_id', '').strip()

    # Determine role
         # Determine role
     role = request.form.get('role') or ('student' if student_id else 'lecturer')
     # Determine role (prefer explicit, fallback to student_id)
     role = (request.form.get('role') or request.get_json(silent=True) or {}).get('role') if request.is_json else request.form.get('role')
     if not role:
         role = 'student' if student_id else 'lecturer'


    # Validate inputs
    if not fullname or not email or not password:
        message = 'Missing required fields'
        if request.is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'error')
        return redirect(request.referrer or url_for('account'))

    if password != confirm:
        message = 'Passwords do not match'
        if request.is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'error')
        return redirect(request.referrer or url_for('account'))

    # Check if user exists
    from .models import User
    existing = User.query.filter_by(email=email).first()
    if existing:
        message = 'Email already registered'
        if request.is_json:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'error')
        return redirect(request.referrer or url_for('account'))

    # Create new user
    user = User(role=role, fullname=fullname, email=email, student_id=student_id or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    # Set session
    session['user_id'] = user.id
    session['role'] = user.role
    session['user_email'] = user.email
    session['user_name'] = user.fullname
    if role == 'student':
        session['student_id'] = user.student_id

    message = 'Registration successful'
    if request.is_json:
        # Return next URL for JS redirect
        next_url = url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_home')
        return jsonify({'success': True, 'message': message, 'redirect': next_url})

    flash(message, 'success')
    return redirect(url_for('lecturer_initial_home') if role == 'lecturer' else url_for('student_home'))

# -------------------------------
# LOGIN AND LOGOUT ROUTES
# -------------------------------
@app.post('/login')
def login_lecturer():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    from .models import User
    user = User.query.filter_by(email=email, role='lecturer').first()
    if not user or not user.check_password(password):
        flash('Invalid credentials', 'error')
        return redirect(url_for('lecturer_login_page'))

    session['user_id'] = user.id
    session['role'] = user.role
    session['user_email'] = user.email
    session['user_name'] = user.fullname
    flash('Logged in successfully', 'success')
    return redirect(url_for('lecturer_dashboard'))

@app.post('/login_student')
def login_student():
    email = request.form.get('email', '').strip().lower()
    student_id = request.form.get('student_id', '').strip()
    password = request.form.get('password', '')

    from .models import User
    user = None
    if email:
        user = User.query.filter_by(email=email, role='student').first()
    elif student_id:
        user = User.query.filter_by(student_id=student_id, role='student').first()

    if not user or not user.check_password(password):
        flash('Invalid credentials', 'error')
        return redirect(url_for('student_login_page'))

    session['user_id'] = user.id
    session['role'] = user.role
    session['user_email'] = user.email
    session['user_name'] = user.fullname
    session['student_id'] = user.student_id
    flash('Logged in successfully', 'success')
    return redirect(url_for('student_dashboard'))

@app.get('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('home'))

# -------------------------------
# EMAIL HELPERS
# -------------------------------
def get_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='tapin-reset')

def make_reset_token(email: str, role: str) -> str:
    s = get_serializer()
    return s.dumps({'email': email, 'role': role})

def verify_reset_token(token: str, max_age=3600):
    s = get_serializer()
    try:
        data = s.loads(token, max_age=max_age)
        return True, data
    except SignatureExpired:
        return False, {'error': 'expired'}
    except BadSignature:
        return False, {'error': 'invalid'}

def send_reset_email(email: str, role: str, token: str):
    reset_url = url_for('reset_password_page', token=token, role=role, _external=True)
    msg = Message(
        subject="TapIn password reset",
        recipients=[email],
        body=f"Click the link below to reset your password:\n{reset_url}\n\nThis link expires in 1 hour."
    )
    mail.send(msg)
    app.logger.info(f"[EMAIL] Sent reset link to {email} -> {reset_url}")

# -------------------------------
# PASSWORD RESET API ROUTES
# -------------------------------
@app.post('/api/send-reset-link')
def api_send_reset_link():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    role = data.get('role', '').strip().lower()

    if role not in ('lecturer', 'student'):
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    from .models import User
    user = User.query.filter_by(email=email, role=role).first()
    if not user:
        return jsonify({'success': True, 'message': 'If the account exists, a reset link has been sent.'})

    token = make_reset_token(email, role)
    try:
        send_reset_email(email, role, token)
    except Exception:
        app.logger.exception("Failed to send email")
        return jsonify({'success': True, 'message': 'Reset link generated but email failed (check logs).',
                        'debug_link': url_for('reset_password_page', token=token, role=role, _external=True)})

    return jsonify({'success': True, 'message': 'Password reset link sent to your email.'})

@app.get('/api/validate-token')
def api_validate_token():
    token = request.args.get('token', '')
    role = request.args.get('role', '').strip().lower()
    valid, data = verify_reset_token(token)
    if not valid or (role and data.get('role') != role):
        return jsonify({'valid': False})
    return jsonify({'valid': True})

@app.post('/api/reset-password')
def api_reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '')
    role = data.get('role', '').strip().lower()
    password = data.get('password', '')

    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password too short.'}), 400

    valid, payload = verify_reset_token(token)
    if not valid:
        return jsonify({'success': False, 'message': 'Invalid or expired token.'}), 400

    if role and payload.get('role') != role:
        return jsonify({'success': False, 'message': 'Role mismatch.'}), 400

    from .models import User
    user = User.query.filter_by(email=payload.get('email'), role=payload.get('role')).first()
    if not user:
        return jsonify({'success': False, 'message': 'User not found.'}), 404

    user.set_password(password)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password updated successfully.'})

# -------------------------------
# SERVER ENTRY
# -------------------------------
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    port = int(os.getenv('PORT', 8000))
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)
