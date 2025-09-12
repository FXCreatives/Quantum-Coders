from tapin_backend.app import app
from tapin_backend.models import db

with app.app_context():
    from sqlalchemy import text
    db.engine.execute(text('ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE'))
    print("Added is_verified column.")