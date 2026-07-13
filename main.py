from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import func
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
                        for cls_obj in grade.classes:
                            db.session.execute(db.delete(Subject).where(Subject.class_id == cls_obj.id))
                            db.session.execute(db.delete(WeeklyData).where(WeeklyData.class_id == cls_obj.id))
                            db.session.delete(cls_obj)
                        db.session.delete(grade)
                        db.session.commit()
                        log_activity('admin', f'حذف صف: {name}', teacher_name='المدير', action_type='حذف', description=f'حذف صف: {name} وجميع فصوله وبياناته')
                        flash('تم حذف الصف بنجاح')
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
                    cls = db.session.get(Class, class_id)
                    if cls:
                        db.session.query(Subject).filter_by(class_id=class_id).delete()
                        for day in DAYS_ORDER:
                            for period in range(1, 9):
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
                for key in ['period1_date', 'period2_date', 'final_date', 'current_week', 'school_name']:
                    val = request.form.get(key)
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
                    for day in DAYS_ORDER:
                        for period in range(1, 9):
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
                if t_id:
                    teacher = db.session.get(TeacherAccount, int(t_id))
                    if teacher:
                        name = teacher.name
                        db.session.delete(teacher)
                        db.session.commit()
                        log_activity('admin', f'حذف حساب معلم: {name}')
                        flash(f'تم حذف المعلم: {name}')
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

    grades = Grade.query.order_by(Grade.name).all()
    classes = Class.query.options(joinedload(Class.grade)).order_by(Class.name).all()
    settings = {s.key: s.value for s in Setting.query.all()}

    sel_fixed_class_id = request.args.get('fixed_class_id')
    fixed_schedule = {day: {p: '' for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_fixed_class_id:
        for s in Subject.query.filter_by(class_id=int(sel_fixed_class_id)).all():
            fixed_schedule[s.day][s.period] = s.name

    sel_class_id = request.args.get('class_id')
    sel_week = str(safe_week(request.args.get('week', settings.get('current_week', '1'))))
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_class_id:
        for f in Subject.query.filter_by(class_id=int(sel_class_id)).all():
            schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=safe_week(sel_week)).all():
            schedule[w.day][w.period].update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name

    l_week = str(safe_week(request.args.get('locked_week', settings.get('current_week', '1'))))
    locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=safe_week(l_week)).all()]

    c_week = safe_week(settings.get('current_week', '1'))
    completed = [c for c in classes if WeeklyData.query.filter(WeeklyData.class_id==c.id, WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.topic!='', WeeklyData.topic!=None).first()]
    pending = [c for c in classes if c not in completed]
    percent = (len(completed)/len(classes)*100) if classes else 0
    total_periods = Subject.query.filter_by(school_id=1).count()
    filled_periods = WeeklyData.query.filter(WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.topic!='', WeeklyData.topic!=None).count()
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    teachers = TeacherAccount.query.filter_by(school_id=1).order_by(TeacherAccount.name).all()
    supervisors = SupervisorAccount.query.filter_by(school_id=1).order_by(SupervisorAccount.name).all()
    subjects_by_class = {}
    for cls in classes:
        subs = Subject.query.filter_by(class_id=cls.id, school_id=1).order_by(Subject.day, Subject.period).all()
        if subs:
            subjects_by_class[str(cls.id)] = {
                'grade_name': cls.grade.name,
                'class_name': cls.name,
                'subjects': [{'day': s.day, 'period': s.period, 'name': s.name or ''} for s in subs]
            }
    subjects_json = json.dumps(subjects_by_class, ensure_ascii=False)

    # Build current assignments per teacher
    assignments_by_teacher = {}
    for a in TeacherAssignment.query.filter_by(school_id=1).all():
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
                         subjects_json=subjects_json, assignments_json=assignments_json, teachers_json=teachers_json)

@app.route('/admin/upload_master', methods=['POST'])
@admin_required
def upload_master():
    file = request.files.get('file')
    if not file: return redirect(url_for('admin'))
    try:
        # Hard-Coded Mapping: Start from Row 3 (skiprows=2)
        import pandas as pd
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, skiprows=2, header=None)
        else:
            df = pd.read_excel(file, skiprows=2, header=None)

        # Clean data: remove newlines and strip whitespace
        df = df.map(lambda x: str(x).replace('\n', ' ').strip() if pd.notnull(x) else '')

        # Every 8 columns is a new day (1-8 Sun, 9-16 Mon, etc.)
        day_mappings = {
            'Sunday': range(1, 9),
            'Monday': range(9, 17),
            'Tuesday': range(17, 25),
            'Wednesday': range(25, 33),
            'Thursday': range(33, 41)
        }

        ALL_WEEKS = list(range(1, 20))  # Weeks 1-19

        import_count = 0
        for _, row in df.iterrows():
            grade_name = str(row[0])
            if not grade_name or grade_name.lower() in ['nan', 'none', '']: continue

            grade_name = grade_name.replace('\n', ' ').strip()

            if ' - ' in grade_name:
                parts = grade_name.split(' - ')
                g_n, c_n = parts[0].strip(), parts[1].strip()
            else:
                g_n, c_n = grade_name, "أ"

            cls = get_or_create_class(g_n, c_n)

            # Pre-load all existing WeeklyData for this class (all weeks) for fast lookup
            existing_wd = {}
            for w in WeeklyData.query.filter_by(class_id=cls.id, school_id=1).all():
                existing_wd[(w.week_number, w.day, w.period)] = w

            for day_en, col_range in day_mappings.items():
                for idx, col_idx in enumerate(col_range):
                    period_num = idx + 1
                    if col_idx < len(row):
                        subject_name = str(row[col_idx]).replace('\n', ' ').strip()
                        if subject_name and subject_name.lower() not in ['nan', 'none', '']:
                            # Update Subject master table (UPSERT)
                            db.session.query(Subject).filter_by(class_id=cls.id, day=day_en, period=period_num).delete()
                            db.session.add(Subject(class_id=cls.id, day=day_en, period=period_num, name=subject_name, school_id=1))

                            # FIX: Seed WeeklyData for ALL 19 weeks — not just current_week
                            # Teacher-entered data (topic + homework) is always protected
                            for wk in ALL_WEEKS:
                                key = (wk, day_en, period_num)
                                w_entry = existing_wd.get(key)
                                if w_entry:
                                    # Only update subject_name if teacher hasn't filled topic/homework
                                    if not (w_entry.topic and w_entry.topic.strip()) and \
                                       not (w_entry.homework and w_entry.homework.strip()):
                                        w_entry.subject_name = subject_name
                                else:
                                    new_w = WeeklyData(class_id=cls.id, week_number=wk, day=day_en,
                                                       period=period_num, subject_name=subject_name, school_id=1)
                                    db.session.add(new_w)
                                    existing_wd[key] = new_w  # track for current loop

                            import_count += 1

        db.session.commit()
        flash(f'تم استيراد {import_count} حصة بنجاح (تم نشر المادة في الأسابيع 1-19)')
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        flash(f"خطأ: {e}")
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

                for e in data.get('entries', []):
                    day = e.get('day')
                    period = int(e.get('period'))
                    new_topic = (e.get('topic') or '').strip()
                    new_homework = (e.get('homework') or '').strip()

                    # RACE CONDITION GUARD: SELECT FOR UPDATE locks the row for this transaction.
                    # A concurrent save will block here until this transaction commits/rolls back,
                    # then read the already-committed values — value diffing will then detect no change.
                    w = WeeklyData.query.filter_by(
                        class_id=int(c_id), week_number=week_int,
                        day=day, period=period, school_id=1
                    ).with_for_update().first()

                    old_topic = (w.topic or '').strip() if w else ''
                    old_homework = (w.homework or '').strip() if w else ''

                    # VALUE DIFF: only proceed if something actually changed
                    topic_changed = new_topic != old_topic
                    homework_changed = new_homework != old_homework
                    if not topic_changed and not homework_changed:
                        continue

                    # Ensure WeeklyData record exists (create if missing)
                    if not w:
                        master_sub = Subject.query.filter_by(
                            class_id=int(c_id), day=day, period=period, school_id=1).first()
                        sub_name = master_sub.name if master_sub else ''
                        w = WeeklyData(class_id=int(c_id), week_number=week_int,
                                       day=day, period=period, subject_name=sub_name, school_id=1)
                        db.session.add(w)
                        db.session.flush()

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

    grades = Grade.query.all()
    classes = Class.query.filter_by(grade_id=int(g_id)).all() if g_id else []
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if c_id:
        # FIX: always scope to school_id=1 on both Subject and WeeklyData reads
        for f in Subject.query.filter_by(class_id=int(c_id), school_id=1).all():
            schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(c_id), week_number=safe_week(week), school_id=1).all():
            schedule[w.day][w.period].update({'topic': w.topic or '', 'homework': w.homework or ''})
            if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name

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
                                         assigned_keys=assigned_keys, is_admin_user=is_admin_user))
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
        try:
            TeacherAssignment.query.filter_by(teacher_id=teacher_id).delete()
            for cell in cells:
                db.session.add(TeacherAssignment(
                    teacher_id=teacher_id,
                    class_id=int(cell['class_id']),
                    day=cell['day'],
                    period=int(cell['period']),
                    school_id=1
                ))
            db.session.commit()
            teacher = db.session.get(TeacherAccount, teacher_id)
            log_activity('admin', f'تحديث توزيع مواد: {teacher.name if teacher else teacher_id} — {len(cells)} مادة',
                         action_type='توزيع', description=f'تم تعيين {len(cells)} خلية للمعلم {teacher.name if teacher else teacher_id}')
            return jsonify({'status': 'ok', 'count': len(cells)})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
    # GET: return assignments for a teacher
    teacher_id = request.args.get('teacher_id')
    if teacher_id:
        assignments = [
            {'class_id': a.class_id, 'day': a.day, 'period': a.period}
            for a in TeacherAssignment.query.filter_by(teacher_id=int(teacher_id), school_id=1).all()
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
    grades = Grade.query.all()
    return render_template('student_landing.html', grades=grades, settings=settings)

@app.route('/student/<int:g_id>/<int:c_id>')
def student(g_id, c_id):
    settings = {s.key: s.value for s in Setting.query.all()}
    grade = db.session.get(Grade, g_id)
    cls = db.session.get(Class, c_id)
    published_weeks = [wp.week_number for wp in WeekPublication.query.filter_by(class_id=c_id)
                        .order_by(WeekPublication.week_number.desc()).all()]

    requested = request.args.get('week')
    week_int = safe_week(requested) if requested and safe_week(requested) in published_weeks else (published_weeks[0] if published_weeks else None)

    if week_int is None:
        return render_template('student.html', not_published=True, published_weeks=[],
                                settings=settings, grade_name=grade.name if grade else '',
                                class_name=cls.name if cls else '', g_id=g_id, c_id=c_id)

    week = str(week_int)
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    for f in Subject.query.filter_by(class_id=c_id).all():
        schedule[f.day][f.period]['subject_name'] = f.name
    for w in WeeklyData.query.filter_by(class_id=c_id, week_number=week_int).all():
        schedule[w.day][w.period].update({'topic': w.topic or '', 'homework': w.homework or ''})
        if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name
    return render_template('student.html', schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER,
                            settings=settings, week=week, published_weeks=published_weeks, not_published=False,
                            grade_name=grade.name if grade else '', class_name=cls.name if cls else '',
                            g_id=g_id, c_id=c_id)

@app.route('/admin/audit_report')
@review_access_required
def audit_report():
    week_int = safe_week(request.args.get('week', '1'))
    week = str(week_int)
    classes = Class.query.options(joinedload(Class.grade)).all()
    report = []
    class_status = []
    published_ids = {wp.class_id for wp in WeekPublication.query.filter_by(week_number=week_int).all()}
    for c in classes:
        subjects = Subject.query.filter_by(class_id=c.id, school_id=1).all()
        missing = 0
        for subj in subjects:
            wd = WeeklyData.query.filter_by(class_id=c.id, week_number=week_int, day=subj.day, period=subj.period, school_id=1).first()
            if not wd or not wd.topic or not wd.homework:
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_db()
    port = int(os.getenv('FLASK_PORT', '5000'))
    app.run(host='0.0.0.0', port=port)