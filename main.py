from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload, deferred
import mimetypes
import tempfile
import uuid
from sqlalchemy import func, insert, update
import os
import json
import io
from datetime import datetime, timezone

def utc_now():
    """Timezone-aware UTC now, stored as naive to match existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
from functools import wraps
from werkzeug.utils import secure_filename
import re
import traceback

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-fast490')

db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 10,
    "connect_args": {"connect_timeout": 30},
    "pool_timeout": 30,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Lesson attachments: stored in Replit Object Storage when a bucket is configured
# (large files, does not grow the database). Without a bucket they fall back to
# PostgreSQL with a smaller limit. The deployment disk itself is never used because
# it is not persistent.
MB = 1024 * 1024
OBJECT_STORAGE_MAX_MB = max(1, int(os.getenv('ATTACHMENT_MAX_MB', '50')))
DB_STORAGE_MAX_MB = 10
ALLOWED_ATTACHMENT_EXT = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'pps', 'ppsx', 'xls', 'xlsx', 'csv',
                          'png', 'jpg', 'jpeg', 'webp', 'gif', 'txt', 'zip', 'rar',
                          'mp3', 'm4a', 'wav', 'mp4', 'mov', 'webm'}
app.config['MAX_CONTENT_LENGTH'] = (max(OBJECT_STORAGE_MAX_MB, DB_STORAGE_MAX_MB) + 5) * MB

# Static files (CSS) are cached by the browser; the ?v= version changes whenever the file changes.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 30
try:
    ASSET_VERSION = str(int(os.path.getmtime(os.path.join(app.root_path, 'static', 'css', 'plan.css'))))
except OSError:
    ASSET_VERSION = '1'

@app.context_processor
def inject_asset_version():
    return {'asset_version': ASSET_VERSION}

def natural_key(text):
    """Sort 'Grade 4' before 'Grade 10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(text or ''))]

@app.template_filter('natsort')
def natsort_filter(items, attribute='name'):
    return sorted(items, key=lambda x: natural_key(getattr(x, attribute, x)))

DAYS_AR = {'Sunday': 'الأحد', 'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس'}
DAYS_ORDER = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday']

class School(db.Model):
    __tablename__ = 'school'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=True)
    admin_username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(200), nullable=True)

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    classes = db.relationship('Class', backref='grade', cascade="all, delete-orphan", lazy=True)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey('grade.id'), nullable=False)
    subjects = db.relationship('Subject', backref='class_obj', cascade="all, delete-orphan", lazy=True)
    weekly_data = db.relationship('WeeklyData', backref='class_obj', cascade="all, delete-orphan", lazy=True)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=True)
    school_id = db.Column(db.Integer, nullable=True)

class WeeklyData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.Text, default='')
    homework = db.Column(db.Text, default='')
    subject_name = db.Column(db.String(200), default='')
    school_id = db.Column(db.Integer, nullable=True, server_default='1')
    teacher_id = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)

class Setting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    school_id = db.Column(db.Integer, nullable=True)

class LockedDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_number = db.Column(db.Integer, nullable=False)
    day_name = db.Column(db.String(20), nullable=False)
    school_id = db.Column(db.Integer, nullable=True)
    __table_args__ = (db.UniqueConstraint('week_number', 'day_name', name='_week_day_uc'),)

class WeekPublication(db.Model):
    """Tracks which class/week combinations the admin has approved for parents to view."""
    __tablename__ = 'week_publication'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    school_id = db.Column(db.Integer, nullable=True, server_default='1')
    published_at = db.Column(db.DateTime, default=utc_now)
    __table_args__ = (db.UniqueConstraint('class_id', 'week_number', name='_class_week_pub_uc'),)

class TeacherAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    school_id = db.Column(db.Integer, nullable=True, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)

class SupervisorAccount(db.Model):
    """Limited-access account: can only review and approve/publish weekly schedules."""
    __tablename__ = 'supervisor_account'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    school_id = db.Column(db.Integer, nullable=True, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)

class TeacherAssignment(db.Model):
    __tablename__ = 'teacher_assignment'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher_account.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id', ondelete='CASCADE'), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    school_id = db.Column(db.Integer, default=1)
    __table_args__ = (db.UniqueConstraint('teacher_id', 'class_id', 'day', 'period', name='_ta_unique'),)

class PeriodAttachment(db.Model):
    """One downloadable file per class/week/day/period cell, uploaded by the teacher."""
    __tablename__ = 'period_attachment'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id', ondelete='CASCADE'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mimetype = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    data = deferred(db.Column(db.LargeBinary, nullable=True))      # used when Object Storage is not configured
    storage_key = db.Column(db.String(400), nullable=True)          # object name in Replit Object Storage
    teacher_id = db.Column(db.Integer, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=utc_now)
    school_id = db.Column(db.Integer, nullable=True, server_default='1')
    __table_args__ = (db.UniqueConstraint('class_id', 'week_number', 'day', 'period', name='_attachment_cell_uc'),)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(50))
    action = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=utc_now)
    school_id = db.Column(db.Integer, nullable=True, default=1)
    teacher_name = db.Column(db.String(200), nullable=True)
    action_type = db.Column(db.String(50), nullable=True)
    target_subject = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)

def safe_week(val, default=1):
    """Convert week value to int safely; returns default if invalid."""
    try:
        v = int(str(val).strip())
        return v if 1 <= v <= 99 else default
    except (ValueError, TypeError):
        return default

def get_periods_per_day(settings=None):
    """Return the configured daily period count, clamped to a safe UI range."""
    raw_value = settings.get('periods_per_day', '8') if settings is not None else None
    if raw_value is None:
        stored = db.session.get(Setting, 'periods_per_day')
        raw_value = stored.value if stored else '8'
    try:
        return max(1, min(12, int(str(raw_value).strip())))
    except (ValueError, TypeError):
        return 8

def log_activity(role, action, teacher_name=None, action_type=None, target_subject=None, description=None):
    try:
        log = ActivityLog(
            user_role=role,
            action=action,
            timestamp=utc_now(),
            school_id=1,
            teacher_name=teacher_name or (role if role != 'admin' else 'المدير'),
            action_type=action_type or 'عام',
            target_subject=target_subject or '',
            description=description or action
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

_tables_ensured = False

@app.before_request
def ensure_tables():
    """Fallback only: migrations normally run once at startup (see bottom of file)."""
    if not _tables_ensured:
        run_startup_migrations()

def run_startup_migrations():
    global _tables_ensured
    if _tables_ensured:
        return
    _tables_ensured = True
    try:
        db.create_all()
    except Exception:
        db.session.rollback()
    try:
        seed_db()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text('''
            CREATE TABLE IF NOT EXISTS teacher_account (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(200) NOT NULL,
                school_id INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text(
            "ALTER TABLE weekly_data ADD COLUMN IF NOT EXISTS teacher_id INTEGER"
        ))
        db.session.execute(db.text(
            "ALTER TABLE weekly_data ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"
        ))
        db.session.execute(db.text(
            "ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS teacher_name VARCHAR(200)"
        ))
        db.session.execute(db.text(
            "ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS action_type VARCHAR(50)"
        ))
        db.session.execute(db.text(
            "ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS target_subject VARCHAR(200)"
        ))
        db.session.execute(db.text(
            "ALTER TABLE activity_log ADD COLUMN IF NOT EXISTS description TEXT"
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(db.text('''
            CREATE TABLE IF NOT EXISTS teacher_assignment (
                id SERIAL PRIMARY KEY,
                teacher_id INTEGER REFERENCES teacher_account(id) ON DELETE CASCADE,
                class_id INTEGER REFERENCES class(id) ON DELETE CASCADE,
                day VARCHAR(20) NOT NULL,
                period INTEGER NOT NULL,
                school_id INTEGER DEFAULT 1,
                CONSTRAINT _ta_unique UNIQUE (teacher_id, class_id, day, period)
            )
        '''))
        db.session.commit()
    except Exception:
        db.session.rollback()
    # Data integrity fix: heal any Subject/WeeklyData records missing school_id
    try:
        db.session.execute(db.text("UPDATE subject SET school_id = 1 WHERE school_id IS NULL"))
        db.session.execute(db.text("UPDATE weekly_data SET school_id = 1 WHERE school_id IS NULL"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    # Attachments: allow Object Storage rows (no bytes in the database)
    try:
        db.session.execute(db.text("ALTER TABLE period_attachment ADD COLUMN IF NOT EXISTS storage_key VARCHAR(400)"))
        db.session.execute(db.text("ALTER TABLE period_attachment ALTER COLUMN data DROP NOT NULL"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    # Indexes for the pages that load on every login / save
    for stmt in (
        "CREATE INDEX IF NOT EXISTS ix_weekly_data_class_week ON weekly_data (class_id, week_number)",
        "CREATE INDEX IF NOT EXISTS ix_weekly_data_week ON weekly_data (week_number)",
        "CREATE INDEX IF NOT EXISTS ix_subject_class ON subject (class_id)",
        "CREATE INDEX IF NOT EXISTS ix_teacher_assignment_teacher ON teacher_assignment (teacher_id)",
        "CREATE INDEX IF NOT EXISTS ix_teacher_assignment_class ON teacher_assignment (class_id)",
        "CREATE INDEX IF NOT EXISTS ix_week_publication_class ON week_publication (class_id)",
        "CREATE INDEX IF NOT EXISTS ix_activity_log_timestamp ON activity_log (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS ix_period_attachment_class_week ON period_attachment (class_id, week_number)",
        "CREATE INDEX IF NOT EXISTS ix_locked_day_week ON locked_day (week_number)",
    ):
        try:
            db.session.execute(db.text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def review_access_required(f):
    """Allows the admin AND limited-access supervisor accounts (review + approve only)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') not in ('admin', 'supervisor'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') not in ('admin', 'teacher'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_or_create_class(grade_name, class_name):
    grade = Grade.query.filter_by(name=grade_name).first()
    if not grade:
        grade = Grade(name=grade_name)
        db.session.add(grade)
        db.session.flush()
    cls = Class.query.filter_by(name=class_name, grade_id=grade.id).first()
    if not cls:
        cls = Class(name=class_name, grade_id=grade.id)
        db.session.add(cls)
        db.session.flush()
    return cls

def clean_display_filename(name):
    """Keep the teacher's original (often Arabic) file name, minus paths and control characters."""
    name = (name or '').replace('\\', '/').split('/')[-1]
    name = re.sub(r'[\x00-\x1f\x7f"<>|:*?]', '', name).strip().strip('.')
    return name[-180:] if name else 'ملف'

def teacher_can_edit_cell(class_id, day, period):
    """Same rule as the lesson save: admin always; a teacher with assignments only on assigned cells."""
    role = session.get('user_role')
    if role == 'admin':
        return True
    if role != 'teacher':
        return False
    t_id = session.get('teacher_id')
    if not t_id:
        return False
    if not TeacherAssignment.query.filter_by(teacher_id=t_id, school_id=1).first():
        return True
    return TeacherAssignment.query.filter_by(teacher_id=t_id, class_id=class_id, day=day,
                                             period=period, school_id=1).first() is not None

def attachment_payload(att):
    return {'id': att.id, 'name': att.original_name, 'size': att.size_bytes,
            'url': url_for('download_attachment', att_id=att.id)}

_object_client = None
_object_checked = False

def object_storage():
    """Returns a Replit Object Storage client when a bucket is configured, else None (cached)."""
    global _object_client, _object_checked
    if _object_checked:
        return _object_client
    _object_checked = True
    if os.getenv('ATTACHMENT_STORAGE', 'auto').lower() == 'db':
        return None
    try:
        import requests
        r = requests.get('http://127.0.0.1:1106/object-storage/default-bucket', timeout=2)
        if r.status_code != 200 or not (r.json() or {}).get('bucketId'):
            return None
        from replit.object_storage import Client
        _object_client = Client()
    except Exception:
        _object_client = None
    return _object_client

def attachment_limit_mb():
    return OBJECT_STORAGE_MAX_MB if object_storage() else DB_STORAGE_MAX_MB

def delete_stored_objects(keys):
    """Best-effort removal of files from Object Storage (never blocks the request)."""
    client = object_storage()
    if not client:
        return
    for key in keys:
        if not key:
            continue
        try:
            client.delete(key, ignore_not_found=True)
        except Exception:
            traceback.print_exc()

def purge_class_attachments(class_ids):
    """Deletes attachment rows (and their stored files) for classes that are being removed."""
    if not class_ids:
        return
    keys = [k for (k,) in db.session.query(PeriodAttachment.storage_key)
            .filter(PeriodAttachment.class_id.in_(class_ids), PeriodAttachment.storage_key.isnot(None)).all()]
    PeriodAttachment.query.filter(PeriodAttachment.class_id.in_(class_ids)).delete(synchronize_session=False)
    delete_stored_objects(keys)

def add_attachments_to_schedule(schedule, class_id, week_int):
    """Adds an 'attachment' dict to each schedule cell that has a file (file bytes are not loaded)."""
    rows = PeriodAttachment.query.filter_by(class_id=class_id, week_number=week_int).all()
    for att in rows:
        if att.day in schedule and att.period in schedule[att.day]:
            schedule[att.day][att.period]['attachment'] = attachment_payload(att)

def swap_attachments(class_id, from_day, from_period, to_day, to_period, week_number=None):
    """Moves files together with their lessons when the admin swaps two cells."""
    q = PeriodAttachment.query.filter_by(class_id=class_id)
    if week_number is not None:
        q = q.filter_by(week_number=week_number)
    src = q.filter_by(day=from_day, period=from_period).all()
    dst = PeriodAttachment.query.filter_by(class_id=class_id)
    if week_number is not None:
        dst = dst.filter_by(week_number=week_number)
    dst = dst.filter_by(day=to_day, period=to_period).all()
    # Park the source files on a temporary period so the unique constraint never collides
    for a in src:
        a.period = -a.period - 1000
    db.session.flush()
    for a in dst:
        a.day, a.period = from_day, from_period
    db.session.flush()
    for a in src:
        a.day, a.period = to_day, to_period
    db.session.flush()

@app.route('/')
def index():
    settings = {s.key: s.value for s in Setting.query.all()}
    return render_template('index.html', current_week=settings.get('current_week', '1'), settings=settings)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        stored = db.session.get(Setting, 'admin_password')
        admin_pass = stored.value if stored else 'fast490'
        if password == admin_pass and (not username or username == 'admin'):
            session.clear()
            session['user_role'] = 'admin'
            log_activity('admin', 'تم تسجيل الدخول للوحة التحكم', teacher_name='المدير', action_type='تسجيل دخول')
            return redirect(url_for('admin'))
        if username:
            supervisor = SupervisorAccount.query.filter_by(username=username, is_active=True).first()
            if supervisor and supervisor.password == password:
                session.clear()
                session['user_role'] = 'supervisor'
                session['supervisor_id'] = supervisor.id
                session['supervisor_name'] = supervisor.name
                log_activity('supervisor', f'تسجيل دخول المشرف: {supervisor.name}', teacher_name=supervisor.name, action_type='تسجيل دخول')
                return redirect(url_for('audit_report'))
            teacher = TeacherAccount.query.filter_by(username=username, is_active=True).first()
            if teacher and teacher.password == password:
                session.clear()
                session['user_role'] = 'teacher'
                session['teacher_id'] = teacher.id
                session['teacher_name'] = teacher.name
                log_activity('teacher', f'تسجيل دخول المعلم: {teacher.name}', teacher_name=teacher.name, action_type='تسجيل دخول')
                return redirect(url_for('teacher'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    display_name = session.get('teacher_name') or session.get('supervisor_name') or 'المدير'
    log_activity(session.get('user_role', 'guest'), 'تم تسجيل الخروج', teacher_name=display_name, action_type='تسجيل خروج')
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            if action == 'add_grade':
                name = request.form.get('name')
                if name:
                    try:
                        db.session.add(Grade(name=name))
                        db.session.commit()
                        log_activity('admin', f'إضافة صف جديد: {name}', teacher_name='المدير', action_type='إضافة', description=f'إضافة صف جديد: {name}')
                        flash('تم إضافة الصف بنجاح')
                    except Exception as e:
                        db.session.rollback()
                        flash(f"خطأ: {e}")
            elif action == 'edit_grade':
                gid = request.form.get('grade_id')
                new_name = request.form.get('name')
                if gid and gid.isdigit() and new_name:
                    grade = db.session.get(Grade, int(gid))
                    if grade:
                        old_name = grade.name
                        grade.name = new_name
                        db.session.commit()
                        log_activity('admin', f'تعديل اسم الصف من {old_name} إلى {new_name}', teacher_name='المدير', action_type='تعديل', description=f'تعديل اسم الصف من {old_name} إلى {new_name}')
                        flash('تم تعديل اسم الصف بنجاح')
            elif action == 'delete_grade':
                gid = request.form.get('grade_id')
                if gid and gid.isdigit():
                    grade = db.session.get(Grade, int(gid))
                    if grade:
                        name = grade.name
                        class_ids = [cls_obj.id for cls_obj in grade.classes]
                        if class_ids:
                            TeacherAssignment.query.filter(TeacherAssignment.class_id.in_(class_ids)).delete(synchronize_session=False)
                            WeekPublication.query.filter(WeekPublication.class_id.in_(class_ids)).delete(synchronize_session=False)
                            purge_class_attachments(class_ids)
                        for cls_obj in grade.classes:
                            db.session.execute(db.delete(Subject).where(Subject.class_id == cls_obj.id))
                            db.session.execute(db.delete(WeeklyData).where(WeeklyData.class_id == cls_obj.id))
                            db.session.delete(cls_obj)
                        db.session.delete(grade)
                        db.session.commit()
                        log_activity('admin', f'حذف صف: {name}', teacher_name='المدير', action_type='حذف', description=f'حذف صف: {name} وجميع فصوله وبياناته')
                        flash('تم حذف الصف بنجاح')
            elif action == 'delete_all_grades':
                if request.form.get('confirmation') != 'DELETE_ALL_GRADES':
                    flash('تم إلغاء العملية: تأكيد حذف جميع الصفوف غير صحيح')
                else:
                    grade_count = Grade.query.count()
                    class_ids = [class_id for (class_id,) in db.session.query(Class.id).all()]
                    if class_ids:
                        TeacherAssignment.query.filter(TeacherAssignment.class_id.in_(class_ids)).delete(synchronize_session=False)
                        WeekPublication.query.filter(WeekPublication.class_id.in_(class_ids)).delete(synchronize_session=False)
                        purge_class_attachments(class_ids)
                        Subject.query.filter(Subject.class_id.in_(class_ids)).delete(synchronize_session=False)
                        WeeklyData.query.filter(WeeklyData.class_id.in_(class_ids)).delete(synchronize_session=False)
                        Class.query.filter(Class.id.in_(class_ids)).delete(synchronize_session=False)
                    Grade.query.delete(synchronize_session=False)
                    db.session.commit()
                    log_activity(
                        'admin',
                        f'حذف جميع الصفوف ({grade_count})',
                        teacher_name='المدير',
                        action_type='حذف',
                        description=f'تم حذف جميع الصفوف وعددها {grade_count} مع الفصول والجداول والخطط والتوزيعات المرتبطة'
                    )
                    flash(f'تم حذف جميع الصفوف بنجاح ({grade_count} صف)')
            elif action == 'edit_class':
                cid = request.form.get('class_id')
                new_name = request.form.get('name')
                if cid and cid.isdigit() and new_name:
                    cls = db.session.get(Class, int(cid))
                    if cls:
                        old_name = cls.name
                        cls.name = new_name
                        db.session.commit()
                        log_activity('admin', f'تعديل اسم الفصل من {old_name} إلى {new_name}')
                        flash('تم تعديل اسم الفصل بنجاح')
            elif action == 'add_class':
                name = request.form.get('name')
                gid = request.form.get('grade_id')
                if name and gid and gid.isdigit():
                    try:
                        db.session.add(Class(name=name, grade_id=int(gid)))
                        db.session.commit()
                        log_activity('admin', f'إضافة فصل جديد: {name}')
                        flash('تم إضافة الفصل بنجاح')
                    except Exception as e:
                        db.session.rollback()
                        flash(f"خطأ: {e}")
            elif action == 'delete_class':
                cid = request.form.get('class_id')
                if cid and cid.isdigit():
                    class_id = int(cid)
                    TeacherAssignment.query.filter_by(class_id=class_id).delete(synchronize_session=False)
                    WeekPublication.query.filter_by(class_id=class_id).delete(synchronize_session=False)
                    purge_class_attachments([class_id])
                    db.session.execute(db.delete(Subject).where(Subject.class_id == class_id))
                    db.session.execute(db.delete(WeeklyData).where(WeeklyData.class_id == class_id))
                    cls = db.session.get(Class, class_id)
                    if cls:
                        name = cls.name
                        db.session.delete(cls)
                        db.session.commit()
                        log_activity('admin', f'حذف فصل: {name}', teacher_name='المدير', action_type='حذف', description=f'حذف فصل: {name} وجميع بياناته الأسبوعية')
                        flash('تم حذف الفصل بنجاح')
            elif action == 'save_fixed_schedule':
                cid = request.form.get('class_id')
                if cid and cid != 'None':
                    class_id = int(cid)
                    periods_per_day = get_periods_per_day()
                    cls = db.session.get(Class, class_id)
                    if cls:
                        db.session.query(Subject).filter(
                            Subject.class_id==class_id,
                            Subject.period <= periods_per_day
                        ).delete(synchronize_session=False)
                        for day in DAYS_ORDER:
                            for period in range(1, periods_per_day + 1):
                                name = request.form.get(f'fixed_{day}_{period}')
                                if name:
                                    db.session.add(Subject(class_id=class_id, day=day, period=period, name=name, school_id=1))
                                    # FIX: Update existing WeeklyData (all weeks) where topic+homework empty
                                    db.session.query(WeeklyData).filter_by(
                                        class_id=class_id, day=day, period=period, school_id=1
                                    ).filter(
                                        db.or_(WeeklyData.topic == None, WeeklyData.topic == ''),
                                        db.or_(WeeklyData.homework == None, WeeklyData.homework == '')
                                    ).update({"subject_name": name}, synchronize_session=False)
                                    # FIX: Create WeeklyData for weeks 1-19 that don't exist yet
                                    existing_weeks = {w.week_number for w in WeeklyData.query.filter_by(
                                        class_id=class_id, day=day, period=period, school_id=1).all()}
                                    for wk in range(1, 20):
                                        if wk not in existing_weeks:
                                            db.session.add(WeeklyData(class_id=class_id, week_number=wk,
                                                day=day, period=period, subject_name=name, school_id=1))
                        db.session.commit()
                        log_activity('admin', f'حفظ الجدول الأساسي للفصل: {cls.grade.name} - {cls.name}', teacher_name='المدير', action_type='تعديل', description=f'حفظ الجدول الأساسي للفصل {cls.grade.name} - {cls.name} — تم نشر المادة للأسابيع 1-19')
                        flash('تم الحفظ بنجاح — تم نشر المواد للأسابيع 1-19')
            elif action == 'update_settings':
                for key in ['period1_date', 'period2_date', 'final_date', 'current_week', 'school_name', 'periods_per_day']:
                    val = request.form.get(key)
                    if key == 'periods_per_day':
                        try:
                            val = str(max(1, min(12, int(val))))
                        except (ValueError, TypeError):
                            val = '8'
                    s = db.session.get(Setting, key)
                    if s: s.value = val
                    else: db.session.add(Setting(key=key, value=val))
                db.session.commit()
                flash('تم الحفظ')
            elif action == 'update_locked_days':
                week = request.form.get('week_number')
                if week:
                    w_int = safe_week(week)
                    db.session.execute(db.delete(LockedDay).where(LockedDay.week_number == w_int))
                    for d in request.form.getlist('locked_days'):
                        db.session.add(LockedDay(week_number=w_int, day_name=d, school_id=1))
                    db.session.commit()
                    flash('تم تحديث القفل')
            elif action == 'save_override_batch':
                cid = request.form.get('class_id')
                week = request.form.get('week')
                if cid and cid != 'None' and week:
                    class_id = int(cid)
                    week_num = safe_week(week)
                    periods_per_day = get_periods_per_day()
                    for day in DAYS_ORDER:
                        for period in range(1, periods_per_day + 1):
                            subject_name = request.form.get(f'override_{day}_{period}', '').strip()
                            # FIX: include school_id=1 in lookup to avoid touching orphaned records
                            wd = WeeklyData.query.filter_by(class_id=class_id, week_number=week_num,
                                                             day=day, period=period, school_id=1).first()
                            if wd:
                                wd.subject_name = subject_name
                            elif subject_name:
                                db.session.add(WeeklyData(class_id=class_id, week_number=week_num,
                                    day=day, period=period, subject_name=subject_name, topic='', homework='', school_id=1))
                    db.session.commit()
                    flash('تم حفظ التعديلات الأسبوعية بنجاح')
            elif action == 'add_teacher':
                t_name = request.form.get('teacher_name', '').strip()
                t_username = request.form.get('teacher_username', '').strip().lower()
                t_password = request.form.get('teacher_password', '').strip()
                if t_name and t_username and t_password:
                    if t_username == 'admin':
                        flash('لا يمكن استخدام "admin" كاسم مستخدم للمعلم')
                    elif TeacherAccount.query.filter_by(username=t_username).first():
                        flash(f'اسم المستخدم "{t_username}" موجود بالفعل')
                    else:
                        db.session.add(TeacherAccount(name=t_name, username=t_username, password=t_password, school_id=1))
                        db.session.commit()
                        log_activity('admin', f'إضافة حساب معلم: {t_name}')
                        flash(f'تم إضافة المعلم: {t_name}')
            elif action == 'reset_teacher_password':
                t_id = request.form.get('teacher_id')
                new_pass = request.form.get('new_password', '').strip()
                if t_id and new_pass:
                    teacher = db.session.get(TeacherAccount, int(t_id))
                    if teacher:
                        teacher.password = new_pass
                        db.session.commit()
                        log_activity('admin', f'إعادة تعيين كلمة مرور المعلم: {teacher.name}')
                        flash(f'تم تغيير كلمة مرور: {teacher.name}')
            elif action == 'delete_teacher':
                t_id = request.form.get('teacher_id')
                if t_id and t_id.isdigit():
                    teacher_id = int(t_id)
                    teacher = db.session.get(TeacherAccount, teacher_id)
                    if teacher:
                        name = teacher.name
                        TeacherAssignment.query.filter_by(teacher_id=teacher_id).delete(synchronize_session=False)
                        WeeklyData.query.filter_by(teacher_id=teacher_id).update(
                            {'teacher_id': None}, synchronize_session=False
                        )
                        db.session.delete(teacher)
                        db.session.commit()
                        log_activity('admin', f'حذف حساب معلم: {name}')
                        flash(f'تم حذف المعلم: {name}')
            elif action == 'delete_all_teachers':
                if request.form.get('confirmation') != 'DELETE_ALL_TEACHERS':
                    flash('تم إلغاء العملية: تأكيد حذف جميع حسابات المعلمين غير صحيح')
                else:
                    teacher_ids = [
                        teacher_id for (teacher_id,) in
                        db.session.query(TeacherAccount.id).filter_by(school_id=1).all()
                    ]
                    teacher_count = len(teacher_ids)
                    if teacher_ids:
                        TeacherAssignment.query.filter(
                            TeacherAssignment.teacher_id.in_(teacher_ids)
                        ).delete(synchronize_session=False)
                        WeeklyData.query.filter(
                            WeeklyData.teacher_id.in_(teacher_ids)
                        ).update({'teacher_id': None}, synchronize_session=False)
                        TeacherAccount.query.filter(
                            TeacherAccount.id.in_(teacher_ids)
                        ).delete(synchronize_session=False)
                    db.session.commit()
                    log_activity(
                        'admin',
                        f'حذف جميع حسابات المعلمين ({teacher_count})',
                        teacher_name='المدير',
                        action_type='حذف',
                        description=f'تم حذف جميع حسابات المعلمين وعددها {teacher_count} وتوزيعاتهم مع الاحتفاظ ببيانات الخطط الأسبوعية'
                    )
                    flash(f'تم حذف جميع حسابات المعلمين بنجاح ({teacher_count} حساب)')
            elif action == 'toggle_teacher':
                t_id = request.form.get('teacher_id')
                if t_id:
                    teacher = db.session.get(TeacherAccount, int(t_id))
                    if teacher:
                        teacher.is_active = not teacher.is_active
                        db.session.commit()
                        status = 'تفعيل' if teacher.is_active else 'تعطيل'
                        flash(f'تم {status} حساب: {teacher.name}')
            elif action == 'add_supervisor':
                s_name = request.form.get('supervisor_name', '').strip()
                s_username = request.form.get('supervisor_username', '').strip().lower()
                s_password = request.form.get('supervisor_password', '').strip()
                if s_name and s_username and s_password:
                    if s_username == 'admin':
                        flash('لا يمكن استخدام "admin" كاسم مستخدم للمشرف')
                    elif TeacherAccount.query.filter_by(username=s_username).first() or SupervisorAccount.query.filter_by(username=s_username).first():
                        flash(f'اسم المستخدم "{s_username}" موجود بالفعل')
                    else:
                        db.session.add(SupervisorAccount(name=s_name, username=s_username, password=s_password, school_id=1))
                        db.session.commit()
                        log_activity('admin', f'إضافة حساب مشرف: {s_name}')
                        flash(f'تم إضافة المشرف: {s_name}')
            elif action == 'reset_supervisor_password':
                s_id = request.form.get('supervisor_id')
                new_pass = request.form.get('new_password', '').strip()
                if s_id and new_pass:
                    supervisor = db.session.get(SupervisorAccount, int(s_id))
                    if supervisor:
                        supervisor.password = new_pass
                        db.session.commit()
                        log_activity('admin', f'إعادة تعيين كلمة مرور المشرف: {supervisor.name}')
                        flash(f'تم تغيير كلمة مرور: {supervisor.name}')
            elif action == 'delete_supervisor':
                s_id = request.form.get('supervisor_id')
                if s_id:
                    supervisor = db.session.get(SupervisorAccount, int(s_id))
                    if supervisor:
                        name = supervisor.name
                        db.session.delete(supervisor)
                        db.session.commit()
                        log_activity('admin', f'حذف حساب مشرف: {name}')
                        flash(f'تم حذف المشرف: {name}')
            elif action == 'toggle_supervisor':
                s_id = request.form.get('supervisor_id')
                if s_id:
                    supervisor = db.session.get(SupervisorAccount, int(s_id))
                    if supervisor:
                        supervisor.is_active = not supervisor.is_active
                        db.session.commit()
                        status = 'تفعيل' if supervisor.is_active else 'تعطيل'
                        flash(f'تم {status} حساب: {supervisor.name}')
            elif action == 'upload_logo':
                file = request.files.get('logo')
                if file:
                    fname = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    s = db.session.get(Setting, 'school_logo')
                    if s: s.value = fname
                    else: db.session.add(Setting(key='school_logo', value=fname))
                    db.session.commit()
                    flash('تم رفع الشعار')
        except Exception as e:
            db.session.rollback()
            flash(f"خطأ: {e}")
        return redirect(url_for('admin', **request.args))

    grades = sorted(Grade.query.all(), key=lambda g: natural_key(g.name))
    classes = sorted(Class.query.options(joinedload(Class.grade)).all(),
                     key=lambda c: natural_key(f"{c.grade.name if c.grade else ''} {c.name}"))
    settings = {s.key: s.value for s in Setting.query.all()}
    periods_per_day = get_periods_per_day(settings)

    sel_fixed_class_id = request.args.get('fixed_class_id')
    fixed_schedule = {day: {p: '' for p in range(1, periods_per_day + 1)} for day in DAYS_ORDER}
    if sel_fixed_class_id:
        for s in Subject.query.filter_by(class_id=int(sel_fixed_class_id)).all():
            if s.day in fixed_schedule and s.period in fixed_schedule[s.day]:
                fixed_schedule[s.day][s.period] = s.name

    sel_class_id = request.args.get('class_id')
    sel_week = str(safe_week(request.args.get('week', settings.get('current_week', '1'))))
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, periods_per_day + 1)} for day in DAYS_ORDER}
    if sel_class_id:
        for f in Subject.query.filter_by(class_id=int(sel_class_id)).all():
            if f.day in schedule and f.period in schedule[f.day]:
                schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=safe_week(sel_week)).all():
            if w.day in schedule and w.period in schedule[w.day]:
                schedule[w.day][w.period].update({'topic': w.topic, 'homework': w.homework})
                if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name

    l_week = str(safe_week(request.args.get('locked_week', settings.get('current_week', '1'))))
    locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=safe_week(l_week)).all()]

    c_week = safe_week(settings.get('current_week', '1'))
    classes_with_topics = {cid for (cid,) in db.session.query(WeeklyData.class_id).filter(
        WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.topic!='', WeeklyData.topic!=None).distinct().all()}
    completed = [c for c in classes if c.id in classes_with_topics]
    pending = [c for c in classes if c not in completed]
    percent = (len(completed)/len(classes)*100) if classes else 0
    total_periods = Subject.query.filter(Subject.school_id==1, Subject.period <= periods_per_day).count()
    filled_periods = WeeklyData.query.filter(WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.period <= periods_per_day, WeeklyData.topic!='', WeeklyData.topic!=None).count()
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    teachers = TeacherAccount.query.filter_by(school_id=1).order_by(TeacherAccount.name).all()
    supervisors = SupervisorAccount.query.filter_by(school_id=1).order_by(SupervisorAccount.name).all()
    subjects_by_class = {}
    all_subs = {}
    for sub in Subject.query.filter(Subject.school_id==1, Subject.period <= periods_per_day) \
            .order_by(Subject.day, Subject.period).all():
        all_subs.setdefault(sub.class_id, []).append(sub)
    for cls in classes:
        subs = all_subs.get(cls.id, [])
        if subs:
            subjects_by_class[str(cls.id)] = {
                'grade_name': cls.grade.name,
                'class_name': cls.name,
                'subjects': [{'day': s.day, 'period': s.period, 'name': s.name or ''} for s in subs]
            }
    subjects_json = json.dumps(subjects_by_class, ensure_ascii=False)

    # Build current assignments per teacher
    assignments_by_teacher = {}
    for a in TeacherAssignment.query.filter(
        TeacherAssignment.school_id==1, TeacherAssignment.period <= periods_per_day
    ).all():
        tid = str(a.teacher_id)
        if tid not in assignments_by_teacher:
            assignments_by_teacher[tid] = []
        assignments_by_teacher[tid].append({'class_id': a.class_id, 'day': a.day, 'period': a.period})
    assignments_json = json.dumps(assignments_by_teacher)

    # Build teachers name map {id: name} for conflict labels
    teachers_json = json.dumps({str(t.id): t.name for t in teachers})

    return render_template('admin.html', grades=grades, classes=classes, settings=settings, days_ar=DAYS_AR, days_order=DAYS_ORDER,
                         fixed_schedule=fixed_schedule, sel_fixed_class_id=sel_fixed_class_id, schedule=schedule,
                         selected_class_id=sel_class_id, selected_week=sel_week, locked_view_week=l_week, current_locked_days=locked_days,
                         completion_percent=round(percent,1), completed_classes=completed, pending_classes=pending, logs=logs,
                         total_periods=total_periods, filled_periods=filled_periods, teachers=teachers, supervisors=supervisors,
                         subjects_json=subjects_json, assignments_json=assignments_json, teachers_json=teachers_json,
                         periods_per_day=periods_per_day)

# ---------------------------------------------------------------------------
# Excel / CSV timetable import
# ---------------------------------------------------------------------------
_DAY_WORDS = {
    'Sunday':    ['الأحد', 'الاحد', 'أحد', 'احد', 'sunday', 'sun'],
    'Monday':    ['الاثنين', 'الإثنين', 'اثنين', 'إثنين', 'monday', 'mon'],
    'Tuesday':   ['الثلاثاء', 'ثلاثاء', 'الثلاثا', 'tuesday', 'tue', 'tues'],
    'Wednesday': ['الأربعاء', 'الاربعاء', 'أربعاء', 'اربعاء', 'wednesday', 'wed'],
    'Thursday':  ['الخميس', 'خميس', 'thursday', 'thu', 'thur', 'thurs'],
}
_DAY_LOOKUP = {w.lower(): d for d, words in _DAY_WORDS.items() for w in words}
_ARABIC_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

def _cell_text(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = str(v).strip()
    return '' if t.lower() in ('nan', 'none') else t

def _match_day(text):
    return _DAY_LOOKUP.get(' '.join(str(text).split()).lower())

def _as_period(text):
    t = str(text).translate(_ARABIC_DIGITS).strip()
    t = re.sub(r'^(ح|الحصة|حصة|p|period)\s*', '', t, flags=re.I)
    return int(t) if t.isdigit() and 0 < int(t) <= 12 else None

def parse_class_label(label):
    """'Grade 4 A' -> ('Grade 4', 'A');  'Grade 3 A IB' -> ('Grade 3 IB', 'A');
    'الرابع - ب' -> ('الرابع', 'ب');  'الصف الرابع أ' -> ('الصف الرابع', 'أ');  '10B' -> ('10', 'B')."""
    s = ' '.join(str(label).replace('\n', ' ').split())
    if not s:
        return None, None
    for sep in (' - ', ' – ', '-', '/'):
        if sep in s:
            g, c = s.rsplit(sep, 1)
            if g.strip() and c.strip():
                return g.strip(), c.strip().upper()
    letter = r'([A-Za-zء-ي])'
    m = re.match(r'^(.*?\d+)\s+' + letter + r'(?=\s|$)\s*(.*)$', s)          # Grade 4 A [IB]
    if m:
        grade = m.group(1).strip() + (' ' + m.group(3).strip() if m.group(3).strip() else '')
        return grade, m.group(2).upper()
    m = re.match(r'^(.*?\d+)' + letter + r'$', s)                           # 10B / Grade 4A
    if m:
        return m.group(1).strip(), m.group(2).upper()
    m = re.match(r'^(.+?)\s+' + letter + r'$', s)                           # الصف الرابع أ
    if m:
        return m.group(1).strip(), m.group(2).upper()
    return s, 'أ'

def _read_sheet_rows(file_storage):
    name = (file_storage.filename or '').lower()
    if name.endswith('.csv'):
        import csv
        raw = file_storage.read()
        for enc in ('utf-8-sig', 'cp1256', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        return [[_cell_text(c) for c in row] for row in csv.reader(io.StringIO(text))]
    import openpyxl
    wb = openpyxl.load_workbook(file_storage, read_only=True, data_only=True)
    ws = wb.worksheets[0]            # the timetable is always the first sheet
    rows = [[_cell_text(c) for c in row] for row in ws.iter_rows(values_only=True)]
    wb.close()
    return rows

def parse_timetable(rows, fallback_periods):
    """Returns (classes, periods_per_day) where classes = [(label, {(day, period): subject})]."""
    header_idx, col_map = None, {}
    for i, row in enumerate(rows[:15]):
        if sum(1 for c in row if _match_day(c)) >= 2:
            header_idx = i
            break

    if header_idx is not None:
        header = rows[header_idx]
        period_row = rows[header_idx + 1] if header_idx + 1 < len(rows) else []
        has_period_row = sum(1 for c in period_row[1:] if _as_period(c)) >= 3
        current_day, counter = None, 0
        for col in range(1, len(header)):
            day = _match_day(header[col])
            if day:
                current_day, counter = day, 0
            if not current_day:
                continue
            counter += 1
            period = _as_period(period_row[col]) if has_period_row and col < len(period_row) else None
            col_map[col] = (current_day, period or counter)
        data_rows = rows[header_idx + (2 if has_period_row else 1):]
    else:
        # Legacy layout: 2 title rows, then class + fixed blocks of N columns per day
        for day_index, day in enumerate(DAYS_ORDER):
            for p in range(1, fallback_periods + 1):
                col_map[1 + day_index * fallback_periods + (p - 1)] = (day, p)
        data_rows = rows[2:]

    classes = []
    for row in data_rows:
        label = row[0] if row else ''
        if not label or _match_day(label):
            continue
        slots = {}
        for col, (day, period) in col_map.items():
            if col < len(row) and row[col]:
                lines = [ln.strip() for ln in str(row[col]).splitlines() if ln.strip()]
                if lines:
                    slots[(day, period)] = lines[0][:200]   # 1st line = subject, 2nd = teacher
        if slots:
            classes.append((label, slots))
    periods = max((p for _, p in col_map.values()), default=fallback_periods)
    return classes, periods

@app.route('/admin/upload_master', methods=['POST'])
@admin_required
def upload_master():
    file = request.files.get('file')
    if not file or not file.filename:
        return redirect(url_for('admin'))
    try:
        rows = _read_sheet_rows(file)
        classes_in_file, detected_periods = parse_timetable(rows, get_periods_per_day())
        if not classes_in_file:
            flash('لم يتم العثور على فصول في الملف. تأكد أن العمود الأول يحتوي أسماء الفصول (مثل Grade 4 A) وأن صف العناوين يحتوي أسماء الأيام.')
            return redirect(url_for('admin'))

        # Keep the configured period count in sync with the file (e.g. 6 periods per day)
        detected_periods = max(1, min(12, detected_periods))
        periods_changed = detected_periods != get_periods_per_day()
        if periods_changed:
            setting = db.session.get(Setting, 'periods_per_day')
            if setting:
                setting.value = str(detected_periods)
            else:
                db.session.add(Setting(key='periods_per_day', value=str(detected_periods)))

        # Grades / classes: load once, create what is missing
        grades_by_name = {g.name: g for g in Grade.query.all()}
        classes_by_key = {(c.grade_id, c.name): c for c in Class.query.all()}
        parsed = []   # (class_obj, slots)
        seen_pairs = []
        for label, slots in classes_in_file:
            g_name, c_name = parse_class_label(label)
            if not g_name:
                continue
            grade = grades_by_name.get(g_name)
            if not grade:
                grade = Grade(name=g_name)
                db.session.add(grade)
                db.session.flush()
                grades_by_name[g_name] = grade
            cls = classes_by_key.get((grade.id, c_name))
            if not cls:
                cls = Class(name=c_name, grade_id=grade.id)
                db.session.add(cls)
                db.session.flush()
                classes_by_key[(grade.id, c_name)] = cls
            parsed.append((cls, slots))
            seen_pairs.append((g_name, c_name))

        class_ids = [c.id for c, _ in parsed]
        slots_by_class = {c.id: slots for c, slots in parsed}

        # Master schedule: replace in bulk
        Subject.query.filter(Subject.class_id.in_(class_ids)).delete(synchronize_session=False)
        subject_rows = [
            {'class_id': cid, 'day': day, 'period': period, 'name': name, 'school_id': 1}
            for cid, slots in slots_by_class.items() for (day, period), name in slots.items()
        ]
        if subject_rows:
            db.session.execute(insert(Subject), subject_rows)

        # Weekly rows (weeks 1-19): teacher-entered topic/homework is never overwritten
        ALL_WEEKS = range(1, 20)
        existing = {}
        for wid, cid, wk, day, period, subj, topic, hw in db.session.query(
                WeeklyData.id, WeeklyData.class_id, WeeklyData.week_number, WeeklyData.day,
                WeeklyData.period, WeeklyData.subject_name, WeeklyData.topic, WeeklyData.homework
        ).filter(WeeklyData.class_id.in_(class_ids), WeeklyData.school_id == 1).all():
            existing[(cid, wk, day, period)] = (wid, subj or '', bool((topic or '').strip() or (hw or '').strip()))

        updates, inserts = [], []
        for cid, slots in slots_by_class.items():
            for wk in ALL_WEEKS:
                for day in DAYS_ORDER:
                    for period in range(1, detected_periods + 1):
                        name = slots.get((day, period), '')
                        row = existing.get((cid, wk, day, period))
                        if row:
                            wid, old_name, protected = row
                            if not protected and old_name != name:
                                updates.append({'id': wid, 'subject_name': name})
                        elif name:
                            inserts.append({'class_id': cid, 'week_number': wk, 'day': day, 'period': period,
                                            'subject_name': name, 'topic': '', 'homework': '', 'school_id': 1})
        if updates:
            db.session.execute(update(WeeklyData), updates)
        if inserts:
            db.session.execute(insert(WeeklyData), inserts)

        db.session.commit()

        grade_count = len({g for g, _ in seen_pairs})
        msg = (f'تم استيراد {len(parsed)} فصل في {grade_count} صف — {len(subject_rows)} حصة '
               f'({detected_periods} حصص يومياً)، ونُشر الجدول في الأسابيع 1-19.')
        if periods_changed:
            msg += f' تم تحديث عدد الحصص اليومية في الإعدادات إلى {detected_periods}.'
        flash(msg)

        # Old imports stored "Grade 4 A" as a grade name; point them out so they can be deleted
        legacy = sorted({f'{g} {c}' for g, c in seen_pairs if f'{g} {c}' in grades_by_name}, key=natural_key)
        if legacy:
            flash('تنبيه: توجد صفوف قديمة من استيراد سابق بأسماء مكررة ('
                  + '، '.join(legacy[:8]) + ('…' if len(legacy) > 8 else '')
                  + '). احذفها من "إدارة الصفوف" إن لم تعد تحتاجها.')
        log_activity('admin', f'استيراد الجدول المدرسي: {len(parsed)} فصل', teacher_name='المدير',
                     action_type='استيراد', description=msg)
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"خطأ في قراءة الملف: {e}")
    return redirect(url_for('admin'))

@app.route('/admin/upload_teachers', methods=['POST'])
@admin_required
def upload_teachers():
    file = request.files.get('file')
    if not file:
        flash('لم يتم اختيار ملف')
        return redirect(url_for('admin'))
    try:
        import pandas as pd
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, header=None)
        else:
            df = pd.read_excel(file, header=None)

        added = 0
        skipped = 0
        for _, row in df.iterrows():
            name = str(row[0]).strip() if len(row) > 0 else ''
            username = str(row[1]).strip().lower() if len(row) > 1 else ''
            password = str(row[2]).strip() if len(row) > 2 else ''
            if not name or not username or not password:
                continue
            if name.lower() in ['nan', 'none', ''] or username in ['nan', 'none', '']:
                continue
            if username == 'admin':
                skipped += 1
                continue
            existing = TeacherAccount.query.filter_by(username=username).first()
            if existing:
                skipped += 1
                continue
            db.session.add(TeacherAccount(name=name, username=username, password=password, school_id=1))
            added += 1
        db.session.commit()
        log_activity('admin', f'استيراد {added} حساب معلم من Excel')
        flash(f'تم إضافة {added} معلم، تم تخطي {skipped} (موجودون مسبقاً)')
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"خطأ: {e}")
    return redirect(url_for('admin'))

@app.route('/teacher', methods=['GET', 'POST'])
@login_required
def teacher():
    settings = {s.key: s.value for s in Setting.query.all()}
    periods_per_day = get_periods_per_day(settings)
    g_id = request.args.get('grade_id')
    c_id = request.args.get('class_id')
    week = str(safe_week(request.args.get('week', settings.get('current_week', '1'))))
    if g_id in (None, '', 'None'):
        g_id = None
    if c_id in (None, '', 'None'):
        c_id = None

    if request.method == 'POST':
        data = request.json
        if c_id and week:
            # INTEGRITY CHECK 1: must be an authenticated session
            current_teacher_id = session.get('teacher_id')
            teacher_name = session.get('teacher_name', session.get('user_role', ''))
            user_role = session.get('user_role', '')
            if not user_role:
                return jsonify({'status': 'error', 'message': 'انتهت جلسة العمل — يرجى تسجيل الدخول مجدداً'})

            # ASSIGNMENT CHECK: enforce per-cell permissions for teachers
            if user_role != 'admin' and current_teacher_id:
                authorized_pairs = {
                    (a.day, a.period)
                    for a in TeacherAssignment.query.filter_by(
                        teacher_id=current_teacher_id, class_id=int(c_id), school_id=1
                    ).all()
                }
                # Only enforce if assignments are configured (at least 1 exists for this teacher anywhere)
                teacher_has_any = TeacherAssignment.query.filter_by(teacher_id=current_teacher_id, school_id=1).first()
                if teacher_has_any:
                    for e in data.get('entries', []):
                        if (e.get('day'), int(e.get('period'))) not in authorized_pairs:
                            return jsonify({'status': 'error', 'message': 'غير مصرح — هذه المادة ليست مخصصة لك'}), 403

            try:
                changed_count = 0
                cls_obj = db.session.get(Class, int(c_id))
                class_label = f'{cls_obj.grade.name} - {cls_obj.name}' if cls_obj else f'فصل {c_id}'
                change_details = []
                week_int = safe_week(week)

                # SPEED: lock and load every row of this class/week in ONE query (was one query per cell)
                existing_rows = {
                    (w.day, w.period): w
                    for w in WeeklyData.query.filter_by(class_id=int(c_id), week_number=week_int, school_id=1)
                    .with_for_update().all()
                }
                master_names = None

                for e in data.get('entries', []):
                    day = e.get('day')
                    period = int(e.get('period'))
                    if day not in DAYS_ORDER or period < 1 or period > periods_per_day:
                        return jsonify({'status': 'error', 'message': 'رقم الحصة خارج النطاق المسموح'}), 400
                    new_topic = (e.get('topic') or '').strip()
                    new_homework = (e.get('homework') or '').strip()

                    # RACE CONDITION GUARD: the rows were locked above with SELECT ... FOR UPDATE
                    w = existing_rows.get((day, period))

                    old_topic = (w.topic or '').strip() if w else ''
                    old_homework = (w.homework or '').strip() if w else ''

                    # VALUE DIFF: only proceed if something actually changed
                    topic_changed = new_topic != old_topic
                    homework_changed = new_homework != old_homework
                    if not topic_changed and not homework_changed:
                        continue

                    # Ensure WeeklyData record exists (create if missing)
                    if not w:
                        if master_names is None:
                            master_names = {(m.day, m.period): m.name for m in
                                            Subject.query.filter_by(class_id=int(c_id), school_id=1).all()}
                        sub_name = master_names.get((day, period)) or ''
                        w = WeeklyData(class_id=int(c_id), week_number=week_int,
                                       day=day, period=period, subject_name=sub_name, school_id=1)
                        db.session.add(w)
                        existing_rows[(day, period)] = w

                    # INTEGRITY CHECK 2: school_id must be 1 on every record we write
                    if w.school_id != 1:
                        w.school_id = 1

                    subject_label = w.subject_name or f'ح{period}'
                    day_ar = DAYS_AR.get(day, day)

                    # Build specific, human-readable description of what changed
                    parts = []
                    if topic_changed:
                        if old_topic and not new_topic:
                            parts.append(f'حذف الموضوع (كان: "{old_topic}")')
                        elif not old_topic:
                            parts.append(f'موضوع: "{new_topic}"')
                        else:
                            parts.append(f'موضوع: "{old_topic}" ← "{new_topic}"')
                    if homework_changed:
                        if old_homework and not new_homework:
                            parts.append(f'حذف الواجب (كان: "{old_homework}")')
                        elif not old_homework:
                            parts.append(f'واجب: "{new_homework}"')
                        else:
                            parts.append(f'واجب: "{old_homework}" ← "{new_homework}"')

                    change_details.append(f'{subject_label} ({day_ar} ح{period}): {" | ".join(parts)}')

                    # Write the change with explicit teacher_id + school_id
                    w.topic = new_topic
                    w.homework = new_homework
                    w.teacher_id = current_teacher_id  # may be None for admin — that is valid
                    w.updated_at = utc_now()
                    changed_count += 1

                # COMMIT FIRST — log is written only after a confirmed successful commit
                commit_ok = False
                commit_error = None
                try:
                    db.session.commit()
                    commit_ok = True
                except Exception as commit_exc:
                    db.session.rollback()
                    commit_error = str(commit_exc)
                    traceback.print_exc()

                if not commit_ok:
                    # Log the failure then return error to teacher
                    try:
                        log_activity('teacher',
                            f'{teacher_name} — فشل الحفظ — أسبوع {week} — {class_label}',
                            teacher_name=teacher_name, action_type='خطأ',
                            target_subject=class_label,
                            description=f'فشل DB commit | {teacher_name} | أسبوع {week} | {class_label} | {commit_error}')
                    except Exception:
                        pass
                    return jsonify({'status': 'error', 'message': f'فشل الحفظ في قاعدة البيانات — يرجى المحاولة مجدداً'})

                # Log ONLY after a confirmed commit, ONLY if something actually changed
                if changed_count > 0:
                    details_str = '، '.join(change_details[:15])
                    if len(change_details) > 15:
                        details_str += f' و{len(change_details) - 15} أخرى'
                    try:
                        log_activity('teacher',
                            f'{teacher_name} عدّل {changed_count} حصة — أسبوع {week} — {class_label}',
                            teacher_name=teacher_name, action_type='تعديل',
                            target_subject=class_label,
                            description=f'✓ تم الحفظ | {teacher_name} | أسبوع {week} | {class_label} | {details_str}')
                    except Exception:
                        pass  # log failure must never affect the data save result

                return jsonify({'status': 'success', 'saved': changed_count})

            except Exception as e:
                db.session.rollback()
                traceback.print_exc()
                return jsonify({'status': 'error', 'message': f'خطأ غير متوقع: {str(e)}'})
        return jsonify({'status': 'error', 'message': 'بيانات ناقصة'})

    grades = sorted(Grade.query.all(), key=lambda g: natural_key(g.name))
    classes = sorted(Class.query.filter_by(grade_id=int(g_id)).all(), key=lambda c: natural_key(c.name)) if g_id else []
    schedule = {
        day: {
            p: {'subject_name': '', 'topic': '', 'homework': ''}
            for p in range(1, periods_per_day + 1)
        }
        for day in DAYS_ORDER
    }
    if c_id:
        # FIX: always scope to school_id=1 on both Subject and WeeklyData reads
        for f in Subject.query.filter_by(class_id=int(c_id), school_id=1).all():
            if f.day in schedule and f.period in schedule[f.day]:
                schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(c_id), week_number=safe_week(week), school_id=1).all():
            if w.day in schedule and w.period in schedule[w.day]:
                schedule[w.day][w.period].update({'topic': w.topic or '', 'homework': w.homework or ''})
                if w.subject_name:
                    schedule[w.day][w.period]['subject_name'] = w.subject_name
        add_attachments_to_schedule(schedule, int(c_id), safe_week(week))

    locked = [ld.day_name for ld in LockedDay.query.filter_by(week_number=safe_week(week)).all()]

    # Compute assigned cells for the current teacher (admin bypasses all checks)
    is_admin_user = session.get('user_role') == 'admin'
    assigned_keys = set()
    if not is_admin_user and c_id:
        t_id = session.get('teacher_id')
        if t_id:
            for a in TeacherAssignment.query.filter_by(teacher_id=int(t_id), class_id=int(c_id), school_id=1).all():
                assigned_keys.add(f"{a.day}_{a.period}")

    # FIX 3: No-cache headers so browser always fetches fresh data from DB
    resp = make_response(render_template('teacher.html', grades=grades, classes=classes, schedule=schedule,
                                         selected_grade=g_id, selected_class=c_id, selected_week=week,
                                         days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings, locked_days=locked,
                                         assigned_keys=assigned_keys, is_admin_user=is_admin_user,
                                         periods_per_day=periods_per_day, attachment_max_mb=attachment_limit_mb()))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/admin/assignments', methods=['GET', 'POST'])
@admin_required
def admin_assignments():
    if request.method == 'POST':
        data = request.get_json()
        teacher_id = int(data.get('teacher_id'))
        cells = data.get('cells', [])
        periods_per_day = get_periods_per_day()
        try:
            TeacherAssignment.query.filter_by(teacher_id=teacher_id).delete()
            saved_count = 0
            for cell in cells:
                period = int(cell['period'])
                if cell['day'] not in DAYS_ORDER or period < 1 or period > periods_per_day:
                    continue
                db.session.add(TeacherAssignment(
                    teacher_id=teacher_id,
                    class_id=int(cell['class_id']),
                    day=cell['day'],
                    period=period,
                    school_id=1
                ))
                saved_count += 1
            db.session.commit()
            teacher = db.session.get(TeacherAccount, teacher_id)
            log_activity('admin', f'تحديث توزيع مواد: {teacher.name if teacher else teacher_id} — {saved_count} مادة',
                         action_type='توزيع', description=f'تم تعيين {saved_count} خلية للمعلم {teacher.name if teacher else teacher_id}')
            return jsonify({'status': 'ok', 'count': saved_count})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
    # GET: return assignments for a teacher
    teacher_id = request.args.get('teacher_id')
    if teacher_id:
        periods_per_day = get_periods_per_day()
        assignments = [
            {'class_id': a.class_id, 'day': a.day, 'period': a.period}
            for a in TeacherAssignment.query.filter(
                TeacherAssignment.teacher_id==int(teacher_id),
                TeacherAssignment.school_id==1,
                TeacherAssignment.period <= periods_per_day
            ).all()
        ]
        return jsonify({'assignments': assignments})
    return jsonify({'assignments': []})

@app.route('/admin/swap_schedule', methods=['POST'])
@admin_required
def swap_schedule():
    data = request.get_json()
    swap_type = data.get('type')
    class_id = int(data.get('class_id'))
    from_day = data.get('from_day')
    from_period = int(data.get('from_period'))
    to_day = data.get('to_day')
    to_period = int(data.get('to_period'))

    if swap_type == 'master':
        src = Subject.query.filter_by(class_id=class_id, day=from_day, period=from_period, school_id=1).first()
        dst = Subject.query.filter_by(class_id=class_id, day=to_day, period=to_period, school_id=1).first()
        src_name = src.name if src else ''
        dst_name = dst.name if dst else ''

        if src and dst:
            src.name, dst.name = dst_name, src_name
        elif src and not dst:
            db.session.add(Subject(class_id=class_id, day=to_day, period=to_period, name=src_name, school_id=1))
            db.session.delete(src)
        elif dst and not src:
            db.session.add(Subject(class_id=class_id, day=from_day, period=from_period, name=dst_name, school_id=1))
            db.session.delete(dst)

        src_wd_all = WeeklyData.query.filter_by(class_id=class_id, day=from_day, period=from_period, school_id=1).all()
        dst_wd_all = WeeklyData.query.filter_by(class_id=class_id, day=to_day, period=to_period, school_id=1).all()
        src_map = {w.week_number: w for w in src_wd_all}
        dst_map = {w.week_number: w for w in dst_wd_all}
        all_weeks = set(list(src_map.keys()) + list(dst_map.keys()))
        for wk in all_weeks:
            sw = src_map.get(wk)
            dw = dst_map.get(wk)
            s_subj = sw.subject_name if sw else ''
            s_topic = sw.topic if sw else ''
            s_hw = sw.homework if sw else ''
            d_subj = dw.subject_name if dw else ''
            d_topic = dw.topic if dw else ''
            d_hw = dw.homework if dw else ''
            if sw and dw:
                sw.subject_name, sw.topic, sw.homework = d_subj, d_topic, d_hw
                dw.subject_name, dw.topic, dw.homework = s_subj, s_topic, s_hw
            elif sw and not dw:
                db.session.add(WeeklyData(class_id=class_id, week_number=wk, day=to_day, period=to_period,
                                           subject_name=s_subj, topic=s_topic, homework=s_hw, school_id=1))
                db.session.delete(sw)
            elif dw and not sw:
                db.session.add(WeeklyData(class_id=class_id, week_number=wk, day=from_day, period=from_period,
                                           subject_name=d_subj, topic=d_topic, homework=d_hw, school_id=1))
                db.session.delete(dw)

        swap_attachments(class_id, from_day, from_period, to_day, to_period)
        db.session.commit()
        log_activity('admin', f'نقل مادة في الجدول الأساسي: {DAYS_AR.get(from_day,from_day)} ح{from_period} ↔ {DAYS_AR.get(to_day,to_day)} ح{to_period}',
                     teacher_name='المدير', action_type='نقل', target_subject=f'فصل {class_id}',
                     description=f'نقل مادة في الجدول الأساسي من {DAYS_AR.get(from_day,from_day)} ح{from_period} إلى {DAYS_AR.get(to_day,to_day)} ح{to_period}')
        return jsonify({'success': True, 'message': 'تم نقل المادة وجميع بيانات الدروس بنجاح'})

    elif swap_type == 'weekly':
        week_number = int(data.get('week_number'))
        src_subj = Subject.query.filter_by(class_id=class_id, day=from_day, period=from_period, school_id=1).first()
        dst_subj = Subject.query.filter_by(class_id=class_id, day=to_day, period=to_period, school_id=1).first()
        s_name = src_subj.name if src_subj else ''
        d_name = dst_subj.name if dst_subj else ''
        if src_subj and dst_subj:
            src_subj.name, dst_subj.name = d_name, s_name
        elif src_subj and not dst_subj:
            db.session.add(Subject(class_id=class_id, day=to_day, period=to_period, name=s_name, school_id=1))
            db.session.delete(src_subj)
        elif dst_subj and not src_subj:
            db.session.add(Subject(class_id=class_id, day=from_day, period=from_period, name=d_name, school_id=1))
            db.session.delete(dst_subj)

        src_wd = WeeklyData.query.filter_by(class_id=class_id, week_number=week_number, day=from_day, period=from_period, school_id=1).first()
        dst_wd = WeeklyData.query.filter_by(class_id=class_id, week_number=week_number, day=to_day, period=to_period, school_id=1).first()
        src_subject = src_wd.subject_name if src_wd else ''
        src_topic = src_wd.topic if src_wd else ''
        src_homework = src_wd.homework if src_wd else ''
        dst_subject = dst_wd.subject_name if dst_wd else ''
        dst_topic = dst_wd.topic if dst_wd else ''
        dst_homework = dst_wd.homework if dst_wd else ''

        if src_wd and dst_wd:
            src_wd.subject_name, src_wd.topic, src_wd.homework = dst_subject, dst_topic, dst_homework
            dst_wd.subject_name, dst_wd.topic, dst_wd.homework = src_subject, src_topic, src_homework
        elif src_wd and not dst_wd:
            db.session.add(WeeklyData(class_id=class_id, week_number=week_number, day=to_day, period=to_period,
                                       subject_name=src_subject, topic=src_topic, homework=src_homework, school_id=1))
            db.session.delete(src_wd)
        elif dst_wd and not src_wd:
            db.session.add(WeeklyData(class_id=class_id, week_number=week_number, day=from_day, period=from_period,
                                       subject_name=dst_subject, topic=dst_topic, homework=dst_homework, school_id=1))
            db.session.delete(dst_wd)

        swap_attachments(class_id, from_day, from_period, to_day, to_period, week_number)
        db.session.commit()
        log_activity('admin', f'نقل درس أسبوعي: {DAYS_AR.get(from_day,from_day)} ح{from_period} ↔ {DAYS_AR.get(to_day,to_day)} ح{to_period} (أسبوع {week_number})',
                     teacher_name='المدير', action_type='نقل', target_subject=f'فصل {class_id}',
                     description=f'نقل درس أسبوعي مع التحضير والواجب من {DAYS_AR.get(from_day,from_day)} ح{from_period} إلى {DAYS_AR.get(to_day,to_day)} ح{to_period}')
        return jsonify({'success': True, 'message': 'تم نقل بيانات الدرس بالكامل بنجاح (المادة + التحضير + الواجب)'})

    return jsonify({'success': False, 'message': 'نوع غير معروف'}), 400

@app.route('/admin/activity_log')
@admin_required
def activity_log():
    filter_teacher = request.args.get('teacher', '').strip()
    filter_type = request.args.get('type', '').strip()
    filter_date = request.args.get('date', '').strip()
    page = int(request.args.get('page', '1'))
    per_page = 50

    query = ActivityLog.query
    if filter_teacher:
        query = query.filter(ActivityLog.teacher_name.ilike(f'%{filter_teacher}%'))
    if filter_type:
        query = query.filter(ActivityLog.action_type == filter_type)
    if filter_date:
        try:
            from datetime import timedelta
            date_obj = datetime.strptime(filter_date, '%Y-%m-%d')
            query = query.filter(
                ActivityLog.timestamp >= date_obj,
                ActivityLog.timestamp < date_obj + timedelta(days=1)
            )
        except ValueError:
            pass

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    logs = query.order_by(ActivityLog.timestamp.desc()).offset((page - 1) * per_page).limit(per_page).all()
    teachers = TeacherAccount.query.filter_by(school_id=1).order_by(TeacherAccount.name).all()
    settings = {s.key: s.value for s in Setting.query.all()}

    return render_template('activity_log.html', logs=logs, settings=settings,
                         filter_teacher=filter_teacher, filter_type=filter_type, filter_date=filter_date,
                         page=page, total_pages=total_pages, total=total, teachers=teachers)

@app.route('/student')
def student_landing():
    settings = {s.key: s.value for s in Setting.query.all()}
    grades = sorted(Grade.query.options(joinedload(Grade.classes)).all(), key=lambda g: natural_key(g.name))
    return render_template('student_landing.html', grades=grades, settings=settings)

@app.route('/student/<int:g_id>/<int:c_id>')
def student(g_id, c_id):
    settings = {s.key: s.value for s in Setting.query.all()}
    periods_per_day = get_periods_per_day(settings)
    grade = db.session.get(Grade, g_id)
    cls = db.session.get(Class, c_id)
    published_weeks = [wp.week_number for wp in WeekPublication.query.filter_by(class_id=c_id)
                        .order_by(WeekPublication.week_number.desc()).all()]

    requested = request.args.get('week')
    week_int = safe_week(requested) if requested and safe_week(requested) in published_weeks else (published_weeks[0] if published_weeks else None)

    if week_int is None:
        return render_template('student.html', not_published=True, published_weeks=[],
                                settings=settings, grade_name=grade.name if grade else '',
                                class_name=cls.name if cls else '', g_id=g_id, c_id=c_id,
                                periods_per_day=periods_per_day)

    week = str(week_int)
    schedule = {
        day: {
            p: {'subject_name': '', 'topic': '', 'homework': ''}
            for p in range(1, periods_per_day + 1)
        }
        for day in DAYS_ORDER
    }
    for f in Subject.query.filter_by(class_id=c_id).all():
        if f.day in schedule and f.period in schedule[f.day]:
            schedule[f.day][f.period]['subject_name'] = f.name
    for w in WeeklyData.query.filter_by(class_id=c_id, week_number=week_int).all():
        if w.day in schedule and w.period in schedule[w.day]:
            schedule[w.day][w.period].update({'topic': w.topic or '', 'homework': w.homework or ''})
            if w.subject_name:
                schedule[w.day][w.period]['subject_name'] = w.subject_name
    add_attachments_to_schedule(schedule, c_id, week_int)
    return render_template('student.html', schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER,
                            settings=settings, week=week, published_weeks=published_weeks, not_published=False,
                            grade_name=grade.name if grade else '', class_name=cls.name if cls else '',
                             g_id=g_id, c_id=c_id, periods_per_day=periods_per_day)

@app.route('/teacher/attachment', methods=['POST'])
@login_required
def upload_attachment():
    try:
        class_id = int(request.form.get('class_id', ''))
        period = int(request.form.get('period', ''))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'بيانات الحصة ناقصة'}), 400
    week_int = safe_week(request.form.get('week'))
    day = request.form.get('day', '')
    if day not in DAYS_ORDER or period < 1 or period > get_periods_per_day():
        return jsonify({'status': 'error', 'message': 'رقم الحصة خارج النطاق المسموح'}), 400
    if not db.session.get(Class, class_id):
        return jsonify({'status': 'error', 'message': 'الفصل غير موجود'}), 404
    if not teacher_can_edit_cell(class_id, day, period):
        return jsonify({'status': 'error', 'message': 'غير مصرح — هذه المادة ليست مخصصة لك'}), 403
    if session.get('user_role') != 'admin' and LockedDay.query.filter_by(week_number=week_int, day_name=day).first():
        return jsonify({'status': 'error', 'message': 'هذا اليوم مغلق من الإدارة'}), 403

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'status': 'error', 'message': 'اختر ملفاً أولاً'}), 400
    display_name = clean_display_filename(f.filename)
    ext = display_name.rsplit('.', 1)[-1].lower() if '.' in display_name else ''
    if ext not in ALLOWED_ATTACHMENT_EXT:
        return jsonify({'status': 'error', 'message': 'نوع الملف غير مدعوم. المسموح: PDF و Word و PowerPoint و Excel والصور والصوت والفيديو و TXT و ZIP'}), 400

    client = object_storage()
    limit_mb = attachment_limit_mb()
    # Stream the upload to a temp file so large files never sit fully in memory
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext)
    try:
        f.save(tmp)
        tmp.close()
        size = os.path.getsize(tmp.name)
        if size == 0:
            return jsonify({'status': 'error', 'message': 'الملف فارغ'}), 400
        if size > limit_mb * MB:
            return jsonify({'status': 'error', 'message': f'حجم الملف أكبر من {limit_mb} ميجابايت'}), 400

        new_key, data = None, None
        if client:
            new_key = f'attachments/class-{class_id}/week-{week_int}/{day}-{period}/{uuid.uuid4().hex}.{ext}'
            try:
                client.upload_from_filename(new_key, tmp.name)
            except Exception:
                traceback.print_exc()
                new_key = None
        if not new_key:
            if size > DB_STORAGE_MAX_MB * MB:
                return jsonify({'status': 'error', 'message': 'تعذر الوصول لمساحة التخزين — حاول مرة أخرى'}), 503
            with open(tmp.name, 'rb') as fh:
                data = fh.read()
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass

    att = PeriodAttachment.query.filter_by(class_id=class_id, week_number=week_int, day=day, period=period).first()
    replaced = att is not None
    old_key = att.storage_key if att else None
    if not att:
        att = PeriodAttachment(class_id=class_id, week_number=week_int, day=day, period=period, school_id=1)
        db.session.add(att)
    att.original_name = display_name
    att.mimetype = mimetypes.guess_type('x.' + ext)[0] or 'application/octet-stream'
    att.size_bytes = size
    att.storage_key = new_key
    att.data = data
    att.teacher_id = session.get('teacher_id')
    att.uploaded_at = utc_now()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        traceback.print_exc()
        delete_stored_objects([new_key])
        return jsonify({'status': 'error', 'message': 'فشل حفظ الملف — حاول مرة أخرى'}), 500
    if old_key and old_key != new_key:
        delete_stored_objects([old_key])

    actor = session.get('teacher_name') or 'المدير'
    log_activity(session.get('user_role'), f'{actor} {"استبدل" if replaced else "أرفق"} ملف "{display_name}" — {DAYS_AR.get(day, day)} ح{period} — أسبوع {week_int}',
                 teacher_name=actor, action_type='مرفق', target_subject=f'فصل {class_id}',
                 description=f'مرفق: {display_name} ({size // 1024} KB) | {DAYS_AR.get(day, day)} ح{period} | أسبوع {week_int}')
    return jsonify({'status': 'success', 'attachment': attachment_payload(att)})

@app.route('/teacher/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
def delete_attachment(att_id):
    att = db.session.get(PeriodAttachment, att_id)
    if not att:
        return jsonify({'status': 'error', 'message': 'الملف غير موجود'}), 404
    if not teacher_can_edit_cell(att.class_id, att.day, att.period):
        return jsonify({'status': 'error', 'message': 'غير مصرح بحذف هذا الملف'}), 403
    if session.get('user_role') != 'admin' and LockedDay.query.filter_by(week_number=att.week_number, day_name=att.day).first():
        return jsonify({'status': 'error', 'message': 'هذا اليوم مغلق من الإدارة'}), 403
    name, day, period, week_int, class_id = att.original_name, att.day, att.period, att.week_number, att.class_id
    key = att.storage_key
    db.session.delete(att)
    db.session.commit()
    delete_stored_objects([key])
    actor = session.get('teacher_name') or 'المدير'
    log_activity(session.get('user_role'), f'{actor} حذف ملف "{name}" — {DAYS_AR.get(day, day)} ح{period} — أسبوع {week_int}',
                 teacher_name=actor, action_type='مرفق', target_subject=f'فصل {class_id}')
    return jsonify({'status': 'success'})

@app.route('/files/<int:att_id>')
def download_attachment(att_id):
    att = db.session.get(PeriodAttachment, att_id)
    if not att:
        abort(404)
    # Students/parents can only download files of weeks the school has published
    if session.get('user_role') not in ('admin', 'teacher', 'supervisor'):
        if not WeekPublication.query.filter_by(class_id=att.class_id, week_number=att.week_number).first():
            abort(404)
    mimetype = att.mimetype or 'application/octet-stream'
    if att.storage_key:
        client = object_storage()
        if not client:
            abort(503)
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        try:
            client.download_to_filename(att.storage_key, tmp.name)
        except Exception:
            traceback.print_exc()
            os.remove(tmp.name)
            abort(404)
        resp = send_file(tmp.name, mimetype=mimetype, as_attachment=True, download_name=att.original_name)
        resp.call_on_close(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))
    else:
        resp = send_file(io.BytesIO(att.data or b''), mimetype=mimetype,
                         as_attachment=True, download_name=att.original_name)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, no-store'
    return resp

@app.errorhandler(413)
def too_large(_e):
    if request.path.startswith('/teacher/attachment'):
        return jsonify({'status': 'error', 'message': f'حجم الملف أكبر من {attachment_limit_mb()} ميجابايت'}), 413
    return 'الملف أكبر من الحد المسموح', 413

@app.route('/admin/audit_report')
@review_access_required
def audit_report():
    current = db.session.get(Setting, 'current_week')
    week_int = safe_week(request.args.get('week', current.value if current else '1'))
    week = str(week_int)
    periods_per_day = get_periods_per_day()
    classes = Class.query.options(joinedload(Class.grade)).all()
    report = []
    class_status = []
    published_ids = {wp.class_id for wp in WeekPublication.query.filter_by(week_number=week_int).all()}
    subjects_by_class = {}
    for subj in Subject.query.filter(Subject.school_id == 1, Subject.period <= periods_per_day) \
            .order_by(Subject.day, Subject.period).all():
        subjects_by_class.setdefault(subj.class_id, []).append(subj)
    filled = {
        (w.class_id, w.day, w.period)
        for w in WeeklyData.query.filter_by(week_number=week_int, school_id=1).all()
        if w.topic and w.homework
    }
    classes = sorted(classes, key=lambda c: natural_key(f"{c.grade.name if c.grade else ''} {c.name}"))
    for c in classes:
        subjects = subjects_by_class.get(c.id, [])
        missing = 0
        for subj in subjects:
            if (c.id, subj.day, subj.period) not in filled:
                missing += 1
                report.append({
                    'subject': subj.name,
                    'grade': f"{c.grade.name} - {c.name}",
                    'day': DAYS_AR.get(subj.day, subj.day),
                    'period': subj.period
                })
        class_status.append({
            'id': c.id,
            'name': f"{c.grade.name} - {c.name}" if c.grade else c.name,
            'total': len(subjects),
            'missing': missing,
            'published': c.id in published_ids
        })
    return render_template('audit_report.html', report=report, week=week, class_status=class_status,
                            user_role=session.get('user_role'), display_name=session.get('supervisor_name'))

@app.route('/admin/publish_week', methods=['POST'])
@review_access_required
def publish_week():
    week_int = safe_week(request.form.get('week'))
    checked_ids = set(int(x) for x in request.form.getlist('class_ids') if x.isdigit())
    all_classes = Class.query.all()
    published_count = 0
    for c in all_classes:
        existing = WeekPublication.query.filter_by(class_id=c.id, week_number=week_int).first()
        if c.id in checked_ids:
            if not existing:
                db.session.add(WeekPublication(class_id=c.id, week_number=week_int, school_id=1))
            published_count += 1
        else:
            if existing:
                db.session.delete(existing)
    db.session.commit()
    actor_role = session.get('user_role', 'admin')
    actor_name = session.get('supervisor_name') or 'المدير'
    log_activity(actor_role, f'اعتماد جدول الأسبوع {week_int} لأولياء الأمور', teacher_name=actor_name,
                 action_type='اعتماد', description=f'تم اعتماد الجدول لـ {published_count} فصل من أصل {len(all_classes)}')
    return redirect(url_for('audit_report', week=week_int))

@app.route('/admin/delete_date/<key>', methods=['POST'])
@admin_required
def delete_date(key):
    s = db.session.get(Setting, key)
    if s: s.value = ''; db.session.commit()
    return redirect(url_for('admin'))

def seed_db():
    try:
        db.session.execute(db.text(
            "INSERT INTO school (id, name, slug, admin_username, password) "
            "VALUES (1, 'مدارس الثقافة الرقمية', 'digital-culture', 'admin', 'admin') "
            "ON CONFLICT (id) DO NOTHING"
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        admin_pass = db.session.get(Setting, 'admin_password')
        if not admin_pass:
            db.session.add(Setting(key='admin_password', value='fast490'))
            db.session.commit()
    except Exception:
        db.session.rollback()

# Run schema checks once when the worker starts, so the first login is not delayed by them.
try:
    with app.app_context():
        run_startup_migrations()
except Exception:
    traceback.print_exc()
    _tables_ensured = False

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_db()
    port = int(os.getenv('FLASK_PORT', '5000'))
    app.run(host='0.0.0.0', port=port)