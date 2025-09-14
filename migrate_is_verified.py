from flask import Flask
from sqlalchemy import text
from tapin_backend.models import db
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///e:/attendance_app/instance/tapin.db'
db.init_app(app)

with app.app_context():
    # Check if column exists
    inspector = db.inspect(db.engine)
    if 'is_verified' not in [col['name'] for col in inspector.get_columns('users')]:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE'))
            conn.commit()
        print('Added is_verified column successfully')
    else:
        print('is_verified column already exists')