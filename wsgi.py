from app import app, db, seed_exercises, _ensure_columns

# Ensure tables exist and columns are up-to-date when the service boots on Render
with app.app_context():
    db.create_all()
    _ensure_columns()   # <- this adds missing columns like program.deload_week and program_exercise.position
    seed_exercises()

# Expose 'app' for Gunicorn (Render runs: gunicorn wsgi:app)
