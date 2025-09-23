# scripts/backfill_user_ids.py
import os
from app import app, db, User, Program, Workout, SetLog, Exercise

EMAIL = os.getenv("BACKFILL_EMAIL")  # set this in the shell
assert EMAIL, "Set BACKFILL_EMAIL to your user email"

with app.app_context():
    u = User.query.filter_by(email=EMAIL.lower()).first()
    if not u:
        raise SystemExit(f"User {EMAIL} not found. Create it via /signup first.")

    # Programs
    prog_updated = Program.query.filter_by(user_id=None).update({"user_id": u.id})
    # Workouts
    wo_updated = Workout.query.filter_by(user_id=None).update({"user_id": u.id})
    # Set logs
    sl_updated = SetLog.query.filter_by(user_id=None).update({"user_id": u.id})

    # Optional: make every custom (non-global) exercise yours
    # (global ones should stay owner_id NULL)
    # If you want to claim ALL exercises (not recommended), uncomment below:
    # ex_updated = Exercise.query.filter_by(owner_id=None).update({"owner_id": u.id})
    ex_updated = 0

    db.session.commit()
    print(f"Programs: {prog_updated}, Workouts: {wo_updated}, SetLogs: {sl_updated}, Exercises claimed: {ex_updated}")
