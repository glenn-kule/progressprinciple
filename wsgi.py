# wsgi.py — minimal WSGI entrypoint for Gunicorn
from app import app  # do NOT import or call seeders or create_all here

# Optional local run:
if __name__ == "__main__":
    app.run()
