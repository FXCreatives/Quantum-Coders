from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint

# -------------------------
# App & DB setup
# -------------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tapin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

# ... [other models remain unchanged] ...

# -------------------------
# Routes
# -------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        fullname = data.get('fullname')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role')
        student_id = data.get('student_id', None)
        phone = data.get('phone', None)

        # Check if email already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400

        # Create new user
        user = User(
            fullname=fullname,
            email=email,
            role=role,
            student_id=student_id,
            phone=phone
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        email = data.get('email')
        password = data.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            return jsonify({'success': f'Logged in as {user.role}'}), 200
        else:
            return jsonify({'error': 'Invalid email or password'}), 401

    return render_template('login.html')

# -------------------------
# DB create helper
# -------------------------
@app.before_first_request
def create_tables():
    db.create_all()

# -------------------------
# Run App
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)
