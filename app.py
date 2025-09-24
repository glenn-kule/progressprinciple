# ---------- imports (top of file) ----------
import os
from datetime import datetime, date
from math import ceil

from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- app & db init ----------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or "sqlite:///hypertrophy_v2.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# =========================
# AUTH: Flask-Login wiring
# =========================
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

login_manager = LoginManager(app)
login_manager.login_view = "login"   # where to send unauth'd users

# --- If your User model isn't defined yet, leave user_loader and routes here;
#     your actual User class must include: id, email, password_hash and inherit UserMixin.

@login_manager.user_loader
def load_user(user_id: str):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

# ---------- Auth routes ----------
@app.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("current_program"))
    return render_template("login.html")

@app.post("/login")
def login_post():
    if current_user.is_authenticated:
        return redirect(url_for("current_program"))
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    if not email or not password:
        flash("Please enter email and password.")
        return redirect(url_for("login"))
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        flash("Invalid email or password.")
        return redirect(url_for("login"))
    login_user(user)  # log them in
    flash("Welcome back!")
    next_url = request.args.get("next")
    return redirect(next_url or url_for("current_program"))

@app.get("/signup")
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("current_program"))
    return render_template("signup.html")

@app.post("/signup")
def signup_post():
    if current_user.is_authenticated:
        return redirect(url_for("current_program"))
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    if not email or not password:
        flash("Please enter email and password.")
        return redirect(url_for("signup"))

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash("That email is already in use.")
        return redirect(url_for("signup"))

    user = User(email=email)
    user.set_password(password)  # hashes
    db.session.add(user)
    db.session.commit()
    login_user(user)
    flash("Account created — let’s build your program.")
    return redirect(url_for("current_program"))

@app.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.")
    return redirect(url_for("login"))


# ---------- MODELS ----------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, raw): self.password_hash = generate_password_hash(raw)
    def check_password(self, raw): return check_password_hash(self.password_hash, raw)

class MuscleGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)

class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    muscle_group = db.Column(db.String(32), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # NULL = global

# ... your other models: Program, ProgramDay, ProgramExercise, Workout, SetLog ...
# make sure Program has fields: duration_weeks, deload_week (nullable), user_id, locked, etc.

# ---------- ROUTES ----------
# (login/signup/logout, index/current_program/etc...)

from flask import abort  # keep this import at the top of app.py with your other imports

@app.route("/program/<int:program_id>/deload", methods=["POST"], endpoint="set_deload")
@login_required
def set_deload(program_id):
    # Program must exist and belong to the current user
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id:
        abort(403)

    action = request.form.get("action", "set")
    if action == "clear":
        prog.deload_week = None
        db.session.commit()
        flash("Deload cleared for this program.")
        return redirect(url_for("current_program"))

    # set a deload week
    week_raw = request.form.get("deload_week")
    try:
        w = int(week_raw) if week_raw is not None else None
        if not w or w < 1 or w > (prog.duration_weeks or 1):
            raise ValueError
    except Exception:
        flash("Invalid deload week.", "error")
        return redirect(url_for("current_program"))

    prog.deload_week = w
    db.session.commit()
    flash(f"Deload scheduled for week {w}.")
    return redirect(url_for("current_program"))


# ... rest of your routes ...

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

# --- DB CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or "sqlite:///hypertrophy_v2.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)           # <-- create db AFTER app
migrate = Migrate(app, db)     # <-- then register Migrate(app, db)

# ... then your models, routes, etc. ...


login_manager = LoginManager(app)
login_manager.login_view = "login"  # redirect here if not authed

# -------------------- MODELS --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

class MuscleGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)

class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    muscle_group = db.Column(db.String(32), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # NULL = global

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    days_per_week = db.Column(db.Integer, nullable=False)
    target_rir = db.Column(db.Integer, nullable=False)
    duration_weeks = db.Column(db.Integer, nullable=False)
    deload = db.Column(db.Boolean, default=False)
    deload_week = db.Column(db.Integer, nullable=True)
    start_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(16), default="active")  # active | archived
    locked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProgramDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("program.id"), nullable=False)
    day_index = db.Column(db.Integer, nullable=False)
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
    position = db.Column(db.Integer, default=0)
    exercise = db.relationship("Exercise")

class Workout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, default=date.today)
    session_name = db.Column(db.String(64))
    program_day_id = db.Column(db.Integer, db.ForeignKey("program_day.id"), nullable=True)
    week_number = db.Column(db.Integer, nullable=True)

class SetLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey("workout.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Float, nullable=False)
    target_reps = db.Column(db.Integer, nullable=True)
    progressed = db.Column(db.Boolean, default=None)
    exercise = db.relationship("Exercise")

# -------------------- HELPERS --------------------
SPLITS = {
    "PPL": ["Push A", "Pull A", "Legs A", "Push B", "Pull B", "Legs B"],
    "UL":  ["Upper A", "Lower A", "Upper B", "Lower B"],
    "FB":  ["Full 1", "Full 2", "Full 3", "Full 4", "Full 5", "Full 6"],
}
INCREMENT_LBS = {
    "legs": 5.0, "chest": 2.5, "back": 2.5, "shoulders": 2.5,
    "biceps": 2.5, "triceps": 2.5, "calves": 5.0, "forearms": 2.5
}

def get_muscle_names():
    names = [m.name for m in MuscleGroup.query.order_by(MuscleGroup.name).all()]
    return names or ["chest","back","legs","shoulders","biceps","triceps","calves","forearms"]

def days_for_split(split: str, days_per_week: int):
    return SPLITS.get(split, SPLITS["FB"])[:days_per_week]

def seed_muscles():
    defaults = ["chest","back","legs","shoulders","biceps","triceps","calves","forearms"]
    existing = {m.name for m in MuscleGroup.query.all()}
    for n in defaults:
        if n not in existing:
            db.session.add(MuscleGroup(name=n))
    db.session.commit()

def seed_exercises():
    if Exercise.query.count() > 0:
        return
    catalog = [
        ("Bench Press","chest"), ("Incline DB Press","chest"),
        ("Overhead Press","shoulders"), ("Lateral Raise","shoulders"),
        ("Pulldown","back"), ("Chest-Supported Row","back"),
        ("Back Squat","legs"), ("Romanian Deadlift","legs"),
        ("Leg Press","legs"), ("Bicep Curl","biceps"),
        ("Triceps Pushdown","triceps"), ("Standing Calf Raise","calves")
    ]
    for n,g in catalog: db.session.add(Exercise(name=n, muscle_group=g, owner_id=None))
    db.session.commit()

def archive_any_active_before_creating(uid: int):
    for p in Program.query.filter_by(user_id=uid, status="active").all():
        p.status = "archived"
    db.session.commit()

def get_current_week(program: Program) -> int:
    if not program.start_date: return 1
    days = (date.today() - program.start_date).days
    return max(1, min((days // 7) + 1, program.duration_weeks))

def get_last_session_sets(uid: int, exercise_id: int):
    from sqlalchemy import desc
    last = (
        db.session.query(SetLog.workout_id, Workout.date)
        .join(Workout, Workout.id == SetLog.workout_id)
        .filter(SetLog.user_id == uid, SetLog.exercise_id == exercise_id)
        .order_by(desc(Workout.date), desc(SetLog.id))
        .first()
    )
    if not last: return []
    last_wid = last.workout_id
    return (
        SetLog.query.filter_by(user_id=uid, exercise_id=exercise_id, workout_id=last_wid)
        .order_by(SetLog.set_number.asc())
        .all()
    )

def is_deload_week(program: Program, week_num: int) -> bool:
    return program.deload_week is not None and week_num == program.deload_week

def compute_session_targets(uid: int, rep_min: int, rep_max: int, exercise: Exercise, deload: bool):
    last_sets = get_last_session_sets(uid, exercise.id)
    if not last_sets:
        return rep_min, None, None
    best_reps = max(s.reps for s in last_sets)
    last_top_weight = max(s.weight for s in last_sets)
    if best_reps >= rep_max:
        inc = INCREMENT_LBS.get(exercise.muscle_group, 2.5)
        return rep_min, round(last_top_weight + inc, 1), last_top_weight
    return min(best_reps + 1, rep_max), None, last_top_weight

def mark_progress(rep_target: int, reps: int, weight: float, last_top_weight: float | None):
    if last_top_weight is not None and weight > last_top_weight:
        return True
    return reps >= rep_target

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- AUTH --------------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = (request.form.get("email") or "").lower().strip()
        pw = request.form.get("password") or ""
        if not email or not pw:
            flash("Email and password required.")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("Account already exists. Log in.")
            return redirect(url_for("login"))
        u = User(email=email)
        u.set_password(pw)
        db.session.add(u); db.session.commit()
        login_user(u)
        flash("Welcome! Account created.")
        return redirect(url_for("current_program"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").lower().strip()
        pw = request.form.get("password") or ""
        u = User.query.filter_by(email=email).first()
        if not u or not u.check_password(pw):
            flash("Invalid email or password.")
            return redirect(url_for("login"))
        login_user(u, remember=True)
        flash("Logged in.")
        return redirect(url_for("current_program"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.")
    return redirect(url_for("login"))

# -------------------- ROUTES (protected) --------------------
@app.route("/")
def index():
    if not current_user.is_authenticated:
        return render_template("landing.html")
    active = Program.query.filter_by(user_id=current_user.id, status="active").first()
    return render_template("index.html", active=active)

@app.route("/current")
@login_required
def current_program():
    prog = Program.query.filter_by(user_id=current_user.id, status="active").first()
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
    return render_template("current_program.html", program=prog, day_blocks=day_blocks, current_week=current_wk, weeks=weeks)

@app.route("/programs")
@login_required
def programs_history():
    past = Program.query.filter_by(user_id=current_user.id, status="archived").order_by(Program.created_at.desc()).all()
    return render_template("programs.html", past=past)

@app.route("/program/<int:program_id>/archive", methods=["POST"])
@login_required
def archive_program(program_id):
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id:
        flash("Not your program.")
        return redirect(url_for("current_program"))
    prog.status = "archived"
    db.session.commit()
    flash("Program archived.")
    return redirect(url_for("programs_history"))

# ---------- MUSCLE BANK ----------
@app.route("/muscles", methods=["GET", "POST"])
@login_required
def muscles():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip().lower()
        if not name:
            flash("Enter a name.")
        elif MuscleGroup.query.filter_by(name=name).first():
            flash("Muscle already exists.")
        else:
            db.session.add(MuscleGroup(name=name)); db.session.commit(); flash("Muscle added.")
        return redirect(url_for("muscles"))
    items = MuscleGroup.query.order_by(MuscleGroup.name).all()
    return render_template("muscles.html", muscles=items)

@app.route("/muscles/<int:mid>/update", methods=["POST"])
@login_required
def update_muscle(mid):
    m = MuscleGroup.query.get_or_404(mid)
    new = (request.form.get("name") or "").strip().lower()
    if not new:
        flash("Enter a name.")
    elif MuscleGroup.query.filter(MuscleGroup.id != mid, MuscleGroup.name == new).first():
        flash("Another muscle with that name exists.")
    else:
        Exercise.query.filter_by(muscle_group=m.name).update({"muscle_group": new})
        m.name = new; db.session.commit(); flash("Muscle updated (and exercises retagged).")
    return redirect(url_for("muscles"))

@app.route("/muscles/<int:mid>/delete", methods=["POST"])
@login_required
def delete_muscle(mid):
    m = MuscleGroup.query.get_or_404(mid)
    if Exercise.query.filter_by(muscle_group=m.name).count() > 0:
        flash(f"Cannot delete '{m.name}' — exercises use it.")
    else:
        db.session.delete(m); db.session.commit(); flash("Muscle deleted.")
    return redirect(url_for("muscles"))

# ---------- EXERCISE BANK ----------
@app.route("/exercises", methods=["GET","POST"])
@login_required
def exercises_bank():
    muscles = get_muscle_names()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        group = (request.form.get("muscle_group") or "").strip().lower()
        if not name or group not in muscles:
            flash("Provide a name and valid muscle.")
        elif Exercise.query.filter_by(name=name).first():
            flash("Exercise already exists.")
        else:
            db.session.add(Exercise(name=name, muscle_group=group, owner_id=current_user.id))
            db.session.commit()
            flash("Exercise added.")
        return redirect(url_for("exercises_bank"))
    # Show global (owner_id is NULL) + your own
    exercises = Exercise.query.filter((Exercise.owner_id == None) | (Exercise.owner_id == current_user.id)).order_by(Exercise.muscle_group, Exercise.name).all()  # noqa: E711
    return render_template("exercises.html", exercises=exercises, muscles=muscles)

@app.route("/exercises/<int:ex_id>/update", methods=["POST"])
@login_required
def update_exercise(ex_id):
    ex = Exercise.query.get_or_404(ex_id)
    if ex.owner_id not in (None, current_user.id):
        flash("Not allowed.")
        return redirect(url_for("exercises_bank"))
    new_name = (request.form.get("name") or "").strip()
    new_group = (request.form.get("muscle_group") or "").strip().lower()
    if not new_name or new_group not in get_muscle_names():
        flash("Invalid input.")
        return redirect(url_for("exercises_bank"))
    exists = Exercise.query.filter(Exercise.id != ex_id, Exercise.name == new_name).first()
    if exists:
        flash("Another exercise has that name.")
        return redirect(url_for("exercises_bank"))
    ex.name = new_name
    ex.muscle_group = new_group
    db.session.commit()
    flash("Exercise updated.")
    return redirect(url_for("exercises_bank"))

@app.route("/exercises/<int:ex_id>/delete", methods=["POST"])
@login_required
def delete_exercise(ex_id):
    ex = Exercise.query.get_or_404(ex_id)
    if ex.owner_id != current_user.id:
        flash("You can only delete your own exercises.")
        return redirect(url_for("exercises_bank"))
    in_use = ProgramExercise.query.filter_by(exercise_id=ex.id).count()
    if in_use > 0:
        flash(f"Cannot delete '{ex.name}' — used in {in_use} program day(s).")
        return redirect(url_for("exercises_bank"))
    db.session.delete(ex); db.session.commit(); flash("Exercise deleted.")
    return redirect(url_for("exercises_bank"))

# ---------- PROGRAM CREATE / EDIT / LOCK ----------
@app.route("/create-program", methods=["GET","POST"])
@login_required
def create_program():
    if request.method == "POST":
        name = (request.form.get("name") or "My Program").strip() or "My Program"
        split = request.form.get("split","PPL")
        days_per_week = int(request.form.get("days_per_week","4"))
        target_rir = int(request.form.get("target_rir","2"))
        duration_weeks = int(request.form.get("duration_weeks","8"))
        deload = request.form.get("deload") == "on"

        archive_any_active_before_creating(current_user.id)

        prog = Program(
            user_id=current_user.id,
            name=name, days_per_week=days_per_week, target_rir=target_rir,
            duration_weeks=duration_weeks, deload=deload, status="active", locked=False
        )
        db.session.add(prog); db.session.flush()

        for idx, nm in enumerate(days_for_split(split, days_per_week)):
            db.session.add(ProgramDay(program_id=prog.id, day_index=idx, day_name=nm))
        db.session.commit()

        flash(f"Program '{prog.name}' created.")
        return redirect(url_for("current_program"))
    return render_template("create_program.html")

@app.route("/program/<int:program_id>/edit-day/<int:day_id>", methods=["GET","POST"])
@login_required
def edit_program_day(program_id, day_id):
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id:
        flash("Not your program."); return redirect(url_for("current_program"))
    day = ProgramDay.query.get_or_404(day_id)
    allow_edit_exercises = not prog.locked

    if request.method == "POST":
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
                db.session.commit(); flash("Exercise added.")
            else:
                flash("Provide valid sets/rep range.")
        elif action == "update_sets":
            pe_id = int(request.form.get("pe_id"))
            new_sets = int(request.form.get("new_sets", "0"))
            pe = ProgramExercise.query.get_or_404(pe_id)
            if new_sets < 1: flash("Sets must be >=1.")
            else: pe.target_sets = new_sets; db.session.commit(); flash("Sets updated.")
        return redirect(url_for("edit_program_day", program_id=program_id, day_id=day_id))

    pes = ProgramExercise.query.filter_by(day_id=day.id).order_by(ProgramExercise.position.asc(), ProgramExercise.id.asc()).all()
    # bank = global + yours
    bank = Exercise.query.filter((Exercise.owner_id == None) | (Exercise.owner_id == current_user.id)).order_by(Exercise.muscle_group, Exercise.name).all()  # noqa: E711
    return render_template("edit_day.html", program=prog, day=day, pes=pes, bank=bank, allow_edit_exercises=allow_edit_exercises)

@app.route("/program/exercise/<int:pe_id>/delete", methods=["POST"])
@login_required
def delete_program_exercise(pe_id):
    pe = ProgramExercise.query.get_or_404(pe_id)
    day = ProgramDay.query.get_or_404(pe.day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.user_id != current_user.id: flash("Not your program."); return redirect(url_for("current_program"))
    if prog.locked: flash("Program is locked."); return redirect(url_for("current_program"))
    db.session.delete(pe); db.session.commit(); flash("Exercise removed.")
    return redirect(url_for("edit_program_day", program_id=prog.id, day_id=day.id))

@app.route("/program/<int:program_id>/start", methods=["POST"])
@login_required
def start_program(program_id):
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id: flash("Not your program."); return redirect(url_for("current_program"))
    if prog.locked: flash("Program already started."); return redirect(url_for("current_program"))
    for d in ProgramDay.query.filter_by(program_id=prog.id).all():
        if ProgramExercise.query.filter_by(day_id=d.id).count() == 0:
            flash(f"Add exercises to {d.day_name} before starting."); return redirect(url_for("current_program"))
    prog.locked = True; prog.start_date = date.today(); db.session.commit()
    flash("Program started. (You can still change sets.)")
    return redirect(url_for("current_program"))

@app.route("/program/day/<int:day_id>/sort", methods=["POST"])
@login_required
def sort_program_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.user_id != current_user.id or prog.locked:
        return jsonify({"ok": False}), 400
    order = request.json.get("order", [])
    for idx, pe_id in enumerate(order):
        pe = ProgramExercise.query.get(int(pe_id))
        if pe and pe.day_id == day.id:
            pe.position = idx
    db.session.commit()
    return jsonify({"ok": True})

# ----- Remove a program day (and its exercises) -----
from flask import abort, flash, redirect, url_for  # make sure these are imported at top
from flask_login import login_required, current_user

@app.post("/program/<int:program_id>/day/<int:day_id>/remove", endpoint="remove_program_day")
@login_required
def remove_program_day(program_id, day_id):
    # Load and ownership-check program
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id:
        abort(403)

    # Load day and verify it belongs to the program
    day = ProgramDay.query.get_or_404(day_id)
    if day.program_id != prog.id:
        abort(404)

    # Remove all exercises under this day, then the day
    ProgramExercise.query.filter_by(program_day_id=day.id).delete()
    db.session.delete(day)
    db.session.commit()

    flash("Day removed.")
    return redirect(url_for("current_program"))


@app.route("/program/<int:program_id>/add-day", methods=["POST"])
@login_required
def add_day(program_id):
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id or prog.locked:
        flash("Cannot add day."); return redirect(url_for("current_program"))
    next_idx = (db.session.query(db.func.coalesce(db.func.max(ProgramDay.day_index), -1))
                .filter_by(program_id=prog.id).scalar() or -1) + 1
    name = request.form.get("day_name", f"Day {next_idx+1}")
    db.session.add(ProgramDay(program_id=prog.id, day_index=next_idx, day_name=name))
    prog.days_per_week = next_idx + 1; db.session.commit(); flash("Day added.")
    return redirect(url_for("current_program"))

@app.route("/program/day/<int:day_id>/remove", methods=["POST"])
@login_required
def remove_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.user_id != current_user.id or prog.locked:
        flash("Cannot remove day."); return redirect(url_for("current_program"))
    ProgramExercise.query.filter_by(day_id=day.id).delete()
    db.session.delete(day)
    days = ProgramDay.query.filter_by(program_id=prog.id).order_by(ProgramDay.day_index).all()
    for i, d in enumerate(days): d.day_index = i
    prog.days_per_week = len(days); db.session.commit(); flash("Day removed.")
    return redirect(url_for("current_program"))

# ------------- Logging -------------
@app.route("/log/day/<int:day_id>", methods=["GET","POST"])
@login_required
def log_program_day(day_id):
    day = ProgramDay.query.get_or_404(day_id)
    prog = Program.query.get_or_404(day.program_id)
    if prog.user_id != current_user.id:
        flash("Not your program."); return redirect(url_for("current_program"))
    pes = ProgramExercise.query.filter_by(day_id=day.id).order_by(ProgramExercise.position.asc(), ProgramExercise.id.asc()).all()

    weeks = list(range(1, prog.duration_weeks + 1))
    default_wk = get_current_week(prog)
    selected_week = int(request.form.get("week_number", request.args.get("week_number", str(default_wk))))
    deload_now = is_deload_week(prog, selected_week)

    if request.method == "POST":
        w = Workout(user_id=current_user.id, session_name=day.day_name, program_day_id=day.id, week_number=selected_week)
        db.session.add(w); db.session.flush()
        for pe in pes:
            rep_target, next_weight_suggestion, last_top_weight = compute_session_targets(current_user.id, pe.rep_min, pe.rep_max, pe.exercise, deload_now)
            sets_this_session = max(1, ceil(pe.target_sets * 0.6)) if deload_now else pe.target_sets
            for set_no in range(1, sets_this_session+1):
                reps_val = int(request.form.get(f"reps-{pe.id}-{set_no}", "0") or "0")
                weight_val = float(request.form.get(f"weight-{pe.id}-{set_no}", "0") or "0")
                if reps_val > 0 and weight_val > 0:
                    progressed = mark_progress(rep_target, reps_val, weight_val, last_top_weight)
                    db.session.add(SetLog(
                        user_id=current_user.id, workout_id=w.id, exercise_id=pe.exercise_id,
                        set_number=set_no, reps=reps_val, weight=weight_val,
                        target_reps=rep_target, progressed=progressed
                    ))
        db.session.commit(); flash("Workout saved.")
        return redirect(url_for("current_program"))

    per_ex = []
    for pe in pes:
        rep_target, next_weight, last_top_weight = compute_session_targets(current_user.id, pe.rep_min, pe.rep_max, pe.exercise, deload_now)
        last_session_sets = get_last_session_sets(current_user.id, pe.exercise_id)
        default_weight = next_weight if next_weight is not None else (last_top_weight if last_top_weight is not None else 0)
        sets_this_session = max(1, ceil(pe.target_sets * 0.6)) if deload_now else pe.target_sets
        per_ex.append((pe, rep_target, next_weight, default_weight, last_session_sets, sets_this_session))

    return render_template("log_program_day.html",
        program=prog, day=day, weeks=weeks, selected_week=selected_week,
        per_ex=per_ex, deload_now=deload_now
    )

@app.route("/program/<int:program_id>/week/<int:week>")
@login_required
def view_program_week(program_id, week):
    prog = Program.query.get_or_404(program_id)
    if prog.user_id != current_user.id or week < 1 or week > prog.duration_weeks:
        flash("Invalid."); return redirect(url_for("current_program"))
    days = ProgramDay.query.filter_by(program_id=prog.id).order_by(ProgramDay.day_index).all()
    summary = []
    for d in days:
        wkts = Workout.query.filter_by(user_id=current_user.id, program_day_id=d.id, week_number=week).order_by(Workout.date.asc()).all()
        exercise_map = {}
        for w in wkts:
            sets = SetLog.query.filter_by(user_id=current_user.id, workout_id=w.id).order_by(SetLog.exercise_id, SetLog.set_number).all()
            for s in sets:
                exercise_map.setdefault(s.exercise, []).append(s)
        summary.append((d, sorted(exercise_map.items(), key=lambda kv: kv[0].name.lower())))
    weeks = list(range(1, prog.duration_weeks + 1))
    current_wk = get_current_week(prog)
    return render_template("week_summary.html", program=prog, week=week, days_summary=summary, weeks=weeks, current_week=current_wk)

# ------------- Quick freeform logger -------------
@app.route("/log", methods=["GET","POST"])
@login_required
def log_workout_quick():
    if request.method == "POST":
        session_name = request.form.get("session_name", "Session")
        w = Workout(user_id=current_user.id, session_name=session_name)
        db.session.add(w); db.session.flush()
        ex_id = int(request.form["exercise_id"]); reps = int(request.form["reps"]); weight = float(request.form["weight"])
        db.session.add(SetLog(user_id=current_user.id, workout_id=w.id, exercise_id=ex_id, set_number=1, reps=reps, weight=weight))
        db.session.commit(); flash("Quick workout saved.")
        return redirect(url_for("current_program"))
    exercises = Exercise.query.filter((Exercise.owner_id == None) | (Exercise.owner_id == current_user.id)).order_by(Exercise.muscle_group, Exercise.name).all()  # noqa: E711
    return render_template("log_workout.html", exercises=exercises)

# ------------- STARTUP PATCH (adds columns safely) -------------
def _ensure_columns():
    from sqlalchemy import inspect, text
    insp = inspect(db.engine)

    def has_col(table, col):
        return col in [c["name"] for c in insp.get_columns(table)]

    # Add missing columns for auth/ownership
    if not has_col("exercise","owner_id"):
        db.session.execute(text("ALTER TABLE exercise ADD COLUMN owner_id INTEGER"))
        db.session.commit()
    for table, col in [("program","user_id"), ("workout","user_id"), ("set_log","user_id")]:
        if has_col(table, col): continue
        try:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER"))
            db.session.commit()
        except Exception:
            pass
    # position & deload_week
    if not has_col("program_exercise","position"):
        db.session.execute(text("ALTER TABLE program_exercise ADD COLUMN position INTEGER DEFAULT 0"))
        db.session.commit()
    if not has_col("program","deload_week"):
        try:
            db.session.execute(text("ALTER TABLE program ADD COLUMN deload_week INTEGER"))
            db.session.commit()
        except Exception:
            pass

# -------------------- BOOT --------------------
@app.before_request
def _bootstrap_seed():
    # Seed only when DB is empty of muscles/exercises
    if request.endpoint in ("static",):  # skip static
        return
    try:
        if MuscleGroup.query.count() == 0:
            seed_muscles()
        if Exercise.query.count() == 0:
            seed_exercises()
    except Exception:
        # First run on a fresh DB: ensure schema
        with app.app_context():
            db.create_all()
            _ensure_columns()
            seed_muscles()
            seed_exercises()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        _ensure_columns()
        seed_muscles()
        seed_exercises()
    app.run(host="0.0.0.0", port=5000, debug=True)
