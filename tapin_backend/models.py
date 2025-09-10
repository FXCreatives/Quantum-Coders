from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize SQLAlchemy (no Flask app here)
db = SQLAlchemy()

# -------------------------
# Models
# -------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    student_id = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    role = db.Column(db.String(20), nullable=False)  # 'lecturer' or 'student'
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Course(db.Model):
    __tablename__ = 'classes'  # table name can remain 'classes'
    id = db.Column(db.Integer, primary_key=True)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    programme = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    course_code = db.Column(db.String(50), nullable=False)
    level = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(20), nullable=False)
    join_pin = db.Column(db.String(6), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lecturer = db.relationship('User', backref='courses')


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', backref='enrollments')
    course = db.relationship('Course', backref='enrollments')


class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    method = db.Column(db.String(10), nullable=False)  # 'geo' or 'pin'
    pin_code = db.Column(db.String(10), nullable=True)
    lecturer_lat = db.Column(db.Float, nullable=True)
    lecturer_lng = db.Column(db.Float, nullable=True)
    radius_m = db.Column(db.Integer, default=120)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_open = db.Column(db.Boolean, default=True)

    course = db.relationship('Course', backref='sessions')


class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='Present')  # Present, Absent, etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship('AttendanceSession', backref='records')
    student = db.relationship('User', backref='attendance_records')


# -------------------------
# DB helper
# -------------------------
def migrate_db(app):
    """Create all tables for the database."""
    with app.app_context():
        db.create_all()
