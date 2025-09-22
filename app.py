import os
from math import ceil
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret"

# --- DATABASE CONFIG (Postgres in prod, SQLite local) ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    DB_PATH = os.path.join(BASEDIR, "hypertrophy_v2.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -------------------- MODELS --------------------
class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    muscle_group = db.Column(db.String(32), nullable=False)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    days_per_week = db.Column(db.Integer, nullable=False)
    target_rir = db.Column(db.Integer, nullable=False)
    duration_weeks = db.Column(db.Integer, nullable=False)
    deload = db.Column(db.Boolean, default=False)
    deload_week = db.Column(db.Integer, nullable=True)   # NEW: optional scheduled deload week
    start_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(16), default="active")  # active | archived
    locked = db.Column(db.Boolean, default=False)        # lock exercise selection when started
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProgramDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=False)
    day_index = db.Column(db.Integer, nullable=False)  # 0..N-1
    day_name = db.Column(db.String(32), nullable=False)

class ProgramExercise(db.Model):
    __tablename__ = "program_exercise"
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("program_day.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    target_sets = db.Column(db.Integer, nullable=False)
    rep_min = db.Column(db.Integer, nullable=False)
    rep_max = db.Column(db.Integer, nullable=False)
    rir = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, default=0)   # NEW: ordering within the day
    exercise = db.relationship("Exercise")

class Workout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today)
    session_name = db.Column(db.String(64))
    program_day_id = db.Column(db.Integer, db.ForeignKey("program_day.id"), nullable=True)
    week_number = db.Column(db.Integer, nullable=True)

class SetLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey("workout.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    target_reps = db.Column(db.Integer, nullable=True)
    progressed = db.Column(db.Boolean, default=None)
    exercise = db.relationship("Exercise")

# -------------------- CONSTANTS & HELPERS --------------------
SPLITS = {
    "PPL": ["Push A", "Pull A", "Legs A", "Push B", "Pull B", "Legs B"],
    "UL":  ["Upper A", "Lower A", "Upper B", "Lower B"],
    "FB":  ["Full 1", "Full 2", "Full 3", "Full 4", "Full 5", "Full 6"],
}
MUSCLE_GROUPS = ["chest", "back", "legs", "shoulders", "biceps", "triceps"]

INCREMENT_LBS = {
    "legs": 5.0, "chest": 2.5, "back": 2.5, "shoulders": 2.5, "biceps": 2.5, "triceps": 2.5,
}

def days_for_split(split: str, days_per_week: int):
    base = SPLITS.get(split, SPLITS["FB"])
    return base[:days_per_week]

def seed_exercises():
    if Exercise.query.count() > 0:
        return
    catalog = [
        ("Bench Press","chest"), ("Incline DB Press","chest"),
        ("Overhead Press","shoulders"), ("Lateral Raise","shoulders"),
        ("Pulldown","back"), ("Chest-Supported Row","back"),
        ("Back Squat","legs"), ("Romanian Deadlift","legs"),
        ("Leg Press","legs"), ("Bicep Curl","biceps"), ("Triceps Pushdown","triceps")
    ]
    for n,g in catalog: db.session.add(Exercise(name=n, muscle_group=g))
    db.session.commit()

def archive_any_active_before_creating():
    active = Program.query.filter_by(status="active").all()
    for p in active: p.status = "archived"
    if active: db.session.commit()

def get_current_week(program: Program) -> int:
    if not program.start_date: return 1
    days = (date.today() - program.start_date).days
    return max(1, min((days // 7) + 1, program.duration_weeks))

# ---------- last-session utilities & progression ----------
def get_last_session_sets(exercise_id: int):
    from sqlalchemy import desc
    last = (
        db.session.query(SetLog.workout_id, Workout.date)
        .join(Workout, Workout.id == SetLog.workout_id)
        .filter(SetLog.exercise_id == exercise_id)
        .order_by(desc(Workout.date), desc(SetLog.id))
        .first()
    )
    if not last: return []
    last_wid = last.workout_id
    return (
        SetLog.query.filter_by(exercise_id=exercise_id, workout_id=last_wid)
        .order_by(SetLog.set_number.asc())
        .all()
    )

def is_deload_week(program: Program, week_num: int) -> bool:
    return program.deload_week is not None and week_num == program.deload_week

def compute_session_targets(rep_min: int, rep_max: int, exercise: Exercise, deload: bool):
    """
    Progressive overload:
      - If last best reps >= rep_max OR last best reps > rep_max (overshoot), suggest weight increase next time and reset target to rep_min.
      - Else, target = min(best + 1, rep_max).
      - If no history: target = rep_min.
      - Deload week: we still compute target reps, but we'll reduce sets elsewhere.
    Returns (target_reps_this_session, suggested_next_weight_or_None, last_top_weight_or_None)
    """
    last_sets = get_last_session_sets(exercise.id)
    if not last_sets:
        return rep_min, None, None

    best_reps = max(s.reps for s in last_sets)
    last_top_weight = max(s.weight for s in last_sets)

    if best_reps >= rep_max:
        inc = INCREMENT_LBS.get(exercise.muscle_group, 2.5)
        return rep_min, round(last_top_weight + inc, 1), last_top_weight
    else:
        return min(best_reps + 1, rep_max), None, last_top_weight

def mark_progress(rep_target: int, reps: int, weight: float, last_top_weight: float | None):
    # count as progress if hitting/above target OR any weight increase vs last top
    if last_top_weight is not None and weight > last_top_weight:
        return True
    return reps >= rep_target

# -------------------- ROUTES --------------------
@app.route("/")
def index():
    active = Program.query.filter_by(status="active").first()
    return render_template("index.html", active=active)

@app.route("/current")
def current_program():
    prog = Program.query.filter_by(status="active").first()
    if not prog:
        flash("No active program. Create one.")
        return redirect(url_for("create_program"))
    days = ProgramDay.query.filter_by(program_id=prog.id).order_by(ProgramDay.day_index).all()
    day_blocks = []
    for d in days:
        pes = ProgramExercise.query.filter_by(day_id=d.id).order_by(ProgramExercise.position.asc(), ProgramExercise.id.asc()).all()
        day_blocks.append((d, pes))
    current_wk = get_current_week(prog)
    weeks = list(range(1, prog.duration_weeks + 1))
    return render_template("current_program.html",
                           program=prog, day_blocks=day_blocks,
                           current_week=current_wk, weeks=weeks)

@app.route("/programs")
def programs_history():
    past = Program.query.filter_by(status="archived").order_by(Program.created_at.desc()).all()
    return render_template("programs.html", past=past)

@app.route("/program/<int:program_id>/archive", methods=["POST"])
def archive_program(program_id):
    prog = Program.query.get_or_404(program_id)
    prog.status = "archived"
    db.session.commit()
    flash("Program archived.")
    return redirect(url_for("programs_history"))

# ------------- Exercise bank -------------
@app.route("/exercises", methods=["GET","POST"])
def exercises_bank():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        muscle_group = request.form.get("muscle_group","").strip().lower()
        if not name or muscle_group not in MUSCLE_GROUPS:
            flash("Provide a name and a valid muscle group.")
        else:
            if not Exercise.query.filter_by(name=name).first():
                db.session.add(Exercise(name=name, muscle_group=muscle_group))
                db.session.commit()
                flash("Exercise added to bank.")
            else:
                flash("Exercise already exists.")
        return redirect(url_for("exercises_bank"))
    exercises = Exercise.query.order_by(Exercise.muscle_group, Exercise.name).all()
    return render_template("exercises.html", exercises=exercises, groups=MUSCLE_GROUPS)

# ------------- Program create / edit / lock -------------
@app.route("/create-program", methods=["GET","POST"])
def create_program():
    if request.method == "POST":
        name = request.form.get("name","My Program").strip() or "My Program"
        split = request.form.get("split","PPL")
        days_per_week = int(request.form.get("days_per_week","4"))
        target_rir = int(request.form.get("target_rir","2"))
        duration_weeks = int(request.form.get("duration_weeks","8"))
        deload = request.form.get("deload") == "on"

        archive_any_active_before_creating()

        prog = Program(
            name=name, days_per_week=days_per_week, target_rir=target_rir,
            duration_weeks=duration_weeks, deload=deload, status="active", locked=False
        )
        db.session.add(prog); db.session.flush()

        names = days_for_split(split, days_per_week)
        for idx, nm in enumerate(names):
            db.session.add(ProgramDay(program_id=prog.id, day_index=idx, day_name=nm))
        db.session.commit()

        flash(f"Program '{prog.name}' created. Add exercises to each day, reorder, then Start to lock.")
        return redirect(url_for("current_program"))
    return render_template("create_program.html")

@app.route("/program/<int:program_id>/edit-day/<int:day_id>", methods=["GET","POST"])
def edit_program_day(program_id, day_id):
    prog = Program.query.get_or_404(program_id)
    day = ProgramDay.query.get_or_404(day_id)
    if day.program_id != prog.id:
        flash("Day does not belong to this program.")
        return redirect(url_for("current_program"))

    # You can always adjust sets; adding/removing exercises allowed only before lock.
    allow_edit_exercises = not prog.locked

    if request.method == "POST":
        # Two forms share this endpoint:
        action = request.form.get("action", "add")
        if action == "add" and allow_edit_exercises:
            ex_id = int(request.form.get("exercise_id","0"))
            target_sets = int(request.form.get("target_sets","3"))
            rep_min = int(request.form.get("rep_min","8"))
            rep_max = int(request.form.get("rep_max","10"))
            rir = int(request.form.get("rir", str(prog.target_rir)))
            if ex_id and rep_min > 0 and rep_max >= rep_min and target_sets > 0:
                max_pos = db.session.query(db.func.coalesce(db.func.max(ProgramExercise.position), -1)).filter_by(day_id=day.id).scalar() or -1
                db.session.add(ProgramExercise(
                    day_id=day.id, exercise_id=ex_id, target_sets=target_sets,
                    rep_min=rep_min, rep_max=rep_max, rir=rir, position=max_pos+1
                ))
                db.session.commit()
                flash("Exercise added.")
            else:
                flash("Provide valid sets/rep range.")
        elif action == "update_sets":
            # Update target_sets even when locked
            pe_id = int(request.form.get("pe_id"))
            new_sets = int(request.form.get("new_sets", "0"))
            pe = ProgramExercise.query.get_or_404(pe_id)
            if pe.day_id != day.id:
                flash("Exercise mismatch.")
            elif new_sets < 1:
                flash("Sets must be >= 1.")
            else:
                pe.target_sets = new_sets
                db.session.commit()
                flash("Sets updated.")
        return redirect(url_for("edit_program_day", program_id=program_id, day_id=day_id))

    pes = ProgramExercise.query.filter_by(day_id=day.id).order_by(ProgramExercise.position.asc(), ProgramExercise.id.asc()).all()
    bank = Exercise.query.order_by(Exercise.muscle_group, Exercise.name).all()
    return render_template("edit_day.html", program=prog, day=day, pes=pes, bank=bank, allow_edit_exercises=allow_edit_exercises)

@app.route("/program/exercise/<int:pe_id>/delete", methods=["POST"])
def delete_program_exercise(pe_id):
    pe = ProgramExercise.query.get_or_404(pe_id)
    prg_day = ProgramDay.query.get(pe.day_id)
    prog = Program.query.get(prg_day.program_id) if prg_day else None
    if prog and prog.locked:
        flash("Program is locked. Cannot remove exercises.")
        return redirect(url_for("current_program"))
    db.session.delete(pe)
    db.session.commit()
    flash("Exercise removed.")
    if prg_day:
        return redirect(url_for("edit_program_day", program_id=prg_day.program_id, day_id=prg_day.id))
    return redirect(url_for("current_program"))

@app.route("/program/<int:program_id>/start", methods=["POST"])
def start_program(program_id):
    prog = Program.query.get_or_404(program_id)
    if prog.locked:
        flash("Program already started.")
        return redirect(url_for("current_program"))
    days = ProgramDay.query.filter_by(program_id=prog.id).all()
    for d in days:
        if ProgramExercise.query.filter_by(day_id=d.id).count() == 0:
            flash(f"Add exercises to {d.day_name} before starting.")
            return redirect(url_for("current_program"))
    prog.locked = True
    prog.start_date = date.today()
    db.session.commit()
    flash("Program started. Exercises locked. (You can still change sets.)")
    return redirect(url_for("current_program"))

# ---- NEW: drag-sort endpoint (AJAX) ----
@app.route("/program/day/<int:day_id>/sort", methods=["POST"])
def sort_program_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.locked:
        return jsonify({"ok": False, "msg": "Program locked"}), 400
    order = request.json.get("order", [])  # list of pe_id in new order
    for idx, pe_id in enumerate(order):
        pe = ProgramExercise.query.get(int(pe_id))
        if pe and pe.day_id == day.id:
            pe.position = idx
    db.session.commit()
    return jsonify({"ok": True})

# ---- NEW: add/remove day (pre-lock) ----
@app.route("/program/<int:program_id>/add-day", methods=["POST"])
def add_day(program_id):
    prog = Program.query.get_or_404(program_id)
    if prog.locked:
        flash("Program is locked. Cannot add days.")
        return redirect(url_for("current_program"))
    next_idx = (db.session.query(db.func.coalesce(db.func.max(ProgramDay.day_index), -1))
                .filter_by(program_id=prog.id).scalar() or -1) + 1
    name = request.form.get("day_name", f"Day {next_idx+1}")
    db.session.add(ProgramDay(program_id=prog.id, day_index=next_idx, day_name=name))
    prog.days_per_week = next_idx + 1
    db.session.commit()
    flash("Day added.")
    return redirect(url_for("current_program"))

@app.route("/program/day/<int:day_id>/remove", methods=["POST"])
def remove_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.locked:
        flash("Program is locked. Cannot remove days.")
        return redirect(url_for("current_program"))
    # delete its exercises, then the day
    ProgramExercise.query.filter_by(day_id=day.id).delete()
    db.session.delete(day)
    # reindex remaining days
    days = ProgramDay.query.filter_by(program_id=prog.id).order_by(ProgramDay.day_index).all()
    for i, d in enumerate(days): d.day_index = i
    prog.days_per_week = len(days)
    db.session.commit()
    flash("Day removed.")
    return redirect(url_for("current_program"))

# ---- NEW: schedule/cancel deload ----
@app.route("/program/<int:program_id>/set-deload", methods=["POST"])
def set_deload(program_id):
    prog = Program.query.get_or_404(program_id)
    wk = request.form.get("deload_week")
    if wk == "none" or wk is None or wk == "":
        prog.deload_week = None
        db.session.commit()
        flash("Deload cleared.")
    else:
        w = int(wk)
        if w < 1 or w > prog.duration_weeks:
            flash("Invalid deload week.")
        else:
            prog.deload_week = w
            db.session.commit()
            flash(f"Deload scheduled for week {w}.")
    return redirect(url_for("current_program"))

# ------------- Logging -------------
@app.route("/log/day/<int:day_id>", methods=["GET","POST"])
def log_program_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    pes = ProgramExercise.query.filter_by(day_id=day.id).order_by(ProgramExercise.position.asc(), ProgramExercise.id.asc()).all()

    weeks = list(range(1, prog.duration_weeks + 1))
    default_wk = get_current_week(prog)
    selected_week = int(request.form.get("week_number", request.args.get("week_number", str(default_wk))))

    deload_now = is_deload_week(prog, selected_week)

    if request.method == "POST":
        w = Workout(session_name=day.day_name, program_day_id=day.id, week_number=selected_week)
        db.session.add(w); db.session.flush()

        non_progress_count = 0

        for pe in pes:
            rep_target, next_weight_suggestion, last_top_weight = compute_session_targets(
                pe.rep_min, pe.rep_max, pe.exercise, deload_now
            )

            # sets allowed to change dynamically; apply deload cut to sets
            sets_this_session = pe.target_sets
            if deload_now:
                sets_this_session = max(1, ceil(pe.target_sets * 0.6))

            for set_no in range(1, sets_this_session+1):
                reps_field = f"reps-{pe.id}-{set_no}"
                weight_field = f"weight-{pe.id}-{set_no}"
                reps_val = int(request.form.get(reps_field, "0") or "0")
                weight_val = float(request.form.get(weight_field, "0") or "0")

                if reps_val > 0 and weight_val > 0:
                    # Accept outside-range reps; progression adapts:
                    # - If reps >= rep_max: treat as cap hit -> weight increase next time
                    # - Else target increments by +1 up to rep_max
                    progressed = mark_progress(rep_target, reps_val, weight_val, last_top_weight)
                    if not progressed:
                        non_progress_count += 1
                    db.session.add(SetLog(
                        workout_id=w.id, exercise_id=pe.exercise_id, set_number=set_no,
                        reps=reps_val, weight=weight_val, target_reps=rep_target, progressed=progressed
                    ))

        db.session.commit()
        if non_progress_count > 0:
            flash(f"Logged. {non_progress_count} set(s) didn’t meet target/add weight — focus next time.")
        else:
            flash("Logged. Targets met or baseline established.")
        return redirect(url_for("current_program"))

    # GET view data
    per_ex = []
    for pe in pes:
        rep_target, next_weight, last_top_weight = compute_session_targets(pe.rep_min, pe.rep_max, pe.exercise, deload_now)
        last_session_sets = get_last_session_sets(pe.exercise_id)
        default_weight = next_weight if next_weight is not None else (last_top_weight if last_top_weight is not None else 0)
        sets_this_session = pe.target_sets if not deload_now else max(1, ceil(pe.target_sets * 0.6))
        per_ex.append((pe, rep_target, next_weight, default_weight, last_session_sets, sets_this_session))

    return render_template("log_program_day.html",
        program=prog, day=day, weeks=weeks, selected_week=selected_week,
        per_ex=per_ex, deload_now=deload_now
    )

# ------------- Week review -------------
@app.route("/program/<int:program_id>/week/<int:week>")
def view_program_week(program_id, week):
    prog = Program.query.get_or_404(program_id)
    if week < 1 or week > prog.duration_weeks:
        flash("Invalid week."); return redirect(url_for("current_program"))

    days = ProgramDay.query.filter_by(program_id=prog.id).order_by(ProgramDay.day_index).all()
    summary = []
    for d in days:
        wkts = Workout.query.filter_by(program_day_id=d.id, week_number=week).order_by(Workout.date.asc()).all()
        exercise_map = {}
        for w in wkts:
            sets = SetLog.query.filter_by(workout_id=w.id).order_by(SetLog.exercise_id, SetLog.set_number).all()
            for s in sets:
                exercise_map.setdefault(s.exercise, []).append(s)
        exercise_items = sorted(exercise_map.items(), key=lambda kv: kv[0].name.lower())
        summary.append((d, exercise_items))
    weeks = list(range(1, prog.duration_weeks + 1))
    current_wk = get_current_week(prog)
    return render_template("week_summary.html",
        program=prog, week=week, days_summary=summary,
        weeks=weeks, current_week=current_wk
    )

# ------------- Quick freeform logger -------------
@app.route("/log", methods=["GET","POST"])
def log_workout_quick():
    if request.method == "POST":
        session_name = request.form.get("session_name", "Session")
        w = Workout(session_name=session_name)
        db.session.add(w); db.session.flush()
        ex_id = int(request.form["exercise_id"]); reps = int(request.form["reps"]); weight = float(request.form["weight"])
        db.session.add(SetLog(workout_id=w.id, exercise_id=ex_id, set_number=1, reps=reps, weight=weight))
        db.session.commit()
        flash("Quick workout saved.")
        return redirect(url_for("current_program"))
    exercises = Exercise.query.order_by(Exercise.muscle_group, Exercise.name).all()
    return render_template("log_workout.html", exercises=exercises)

# ------------- STARTUP / MIGRATIONS (lightweight) -------------
def _ensure_columns():
    """One-time, safe 'ALTER TABLE' additions for Postgres/SQLite."""
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)
    # program_exercise.position
    cols = [c["name"] for c in insp.get_columns("program_exercise")]
    if "position" not in cols:
        db.session.execute(text("ALTER TABLE program_exercise ADD COLUMN position INTEGER DEFAULT 0"))
        db.session.commit()
    # program.deload_week
    cols_p = [c["name"] for c in insp.get_columns("program")]
    if "deload_week" not in cols_p:
        # Postgres
        try:
            db.session.execute(text("ALTER TABLE program ADD COLUMN deload_week INTEGER"))
        except Exception:
            pass
        db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _ensure_columns()
        seed_exercises()
    app.run(host="0.0.0.0", port=5000, debug=True)
