# models.py
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


# -------------------------
# DB helper
# -------------------------
def migrate_db(app):
    """Create all tables for the database."""
    with app.app_context():
        db.create_all()
