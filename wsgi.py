# wsgi.py
from tapin_backend.app import app  # Import from tapin_backend package

if __name__ == "__main__":
    app.run()