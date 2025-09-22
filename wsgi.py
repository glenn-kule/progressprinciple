from app import app, db, seed_exercises

# Ensure DB tables exist when the service boots on Render
with app.app_context():
    db.create_all()
    seed_exercises()

# Expose 'app' for Gunicorn (Render runs: gunicorn wsgi:app)
