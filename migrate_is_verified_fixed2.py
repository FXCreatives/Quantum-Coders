from tapin_backend.app import app
from tapin_backend.models import db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as connection:
        connection.execute(text('ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE'))
        connection.commit()
    print("Added is_verified column.")