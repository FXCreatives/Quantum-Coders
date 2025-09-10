from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(120), nullable=False)  # Changed from 'name' to match frontend
    email = db.Column(db.String(120), unique=True, nullable=False)
    student_id = db.Column(db.String(50), nullable=True)  # Added to match frontend
    phone = db.Column(db.String(30), nullable=True)  # Keep for additional info
    role = db.Column(db.String(20), nullable=False)  # 'lecturer' or 'student'
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Course(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    programme = db.Column(db.String(120), nullable=False)
    faculty = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    course_name = db.Column(db.String(160), nullable=False)
    course_code = db.Column(db.String(60), nullable=False)
    level = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(40), nullable=False)
    join_pin = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lecturer = db.relationship('User', backref='classes', lazy=True)

class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('class_id', 'student_id', name='uq_enrollment'),
    )

class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    method = db.Column(db.String(10), nullable=False)  # 'geo' | 'pin'
    pin_code = db.Column(db.String(10))
    lecturer_lat = db.Column(db.Float)
    lecturer_lng = db.Column(db.Float)
    radius_m = db.Column(db.Integer, default=120)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_open = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'Present' | 'Absent'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('session_id', 'student_id', name='uq_attendance_once'),
    )

class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)  # null = global
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications', lazy=True)

class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # fixed: Course not "Class"
    class_ref = db.relationship('Course', backref='schedules', lazy=True)

# ----------------------
# FIXED migrate_db
# ----------------------
def migrate_db(app):
    """Initialize database tables if they don't exist."""
    with app.app_context():
        db.create_all()
