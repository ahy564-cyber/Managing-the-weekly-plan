from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import os
import json
import io
from datetime import datetime
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
    "connect_args": {"connect_timeout": 5}
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DAYS_AR = {'Sunday': 'الأحد', 'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس'}
DAYS_ORDER = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday']

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

class TeacherAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    school_id = db.Column(db.Integer, nullable=True, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(50))
    action = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def log_activity(role, action):
    try:
        log = ActivityLog(user_role=role, action=action, timestamp=datetime.utcnow())
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
            log_activity('admin', 'تم تسجيل الدخول للوحة التحكم')
            return redirect(url_for('admin'))
        if username:
            teacher = TeacherAccount.query.filter_by(username=username, is_active=True).first()
            if teacher and teacher.password == password:
                session.clear()
                session['user_role'] = 'teacher'
                session['teacher_id'] = teacher.id
                session['teacher_name'] = teacher.name
                log_activity('teacher', f'تسجيل دخول المعلم: {teacher.name}')
                return redirect(url_for('teacher'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_activity(session.get('user_role', 'guest'), 'تم تسجيل الخروج')
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
                        log_activity('admin', f'إضافة صف جديد: {name}')
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
                        log_activity('admin', f'تعديل اسم الصف من {old_name} إلى {new_name}')
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
                        log_activity('admin', f'حذف صف: {name}')
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
                        log_activity('admin', f'حذف فصل: {name}')
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
                                    db.session.query(WeeklyData).filter_by(
                                        class_id=class_id, day=day, period=period
                                    ).filter(
                                        db.or_(
                                            WeeklyData.topic == None,
                                            WeeklyData.topic == '',
                                        ),
                                        db.or_(
                                            WeeklyData.homework == None,
                                            WeeklyData.homework == '',
                                        )
                                    ).update({"subject_name": name}, synchronize_session=False)
                        db.session.commit()
                        log_activity('admin', f'حفظ الجدول الأساسي للفصل: {cls.grade.name} - {cls.name}')
                        flash('تم الحفظ بنجاح — لم يتم تعديل الحصص التي أدخل المعلمون بياناتها')
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
                    w_int = int(week)
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
                    week_num = int(week)
                    for day in DAYS_ORDER:
                        for period in range(1, 9):
                            subject_name = request.form.get(f'override_{day}_{period}', '')
                            wd = WeeklyData.query.filter_by(class_id=class_id, week_number=week_num, day=day, period=period).first()
                            if wd:
                                wd.subject_name = subject_name
                            elif subject_name:
                                db.session.add(WeeklyData(class_id=class_id, week_number=week_num, day=day, period=period, subject_name=subject_name, topic='', homework='', school_id=1))
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
    sel_week = request.args.get('week', settings.get('current_week', '1'))
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_class_id:
        for f in Subject.query.filter_by(class_id=int(sel_class_id)).all():
            schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=int(sel_week)).all():
            schedule[w.day][w.period].update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name

    l_week = request.args.get('locked_week', settings.get('current_week', '1'))
    locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(l_week)).all()]

    c_week = int(settings.get('current_week', '1'))
    completed = [c for c in classes if WeeklyData.query.filter(WeeklyData.class_id==c.id, WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.topic!='', WeeklyData.topic!=None).first()]
    pending = [c for c in classes if c not in completed]
    percent = (len(completed)/len(classes)*100) if classes else 0
    total_periods = Subject.query.filter_by(school_id=1).count()
    filled_periods = WeeklyData.query.filter(WeeklyData.week_number==c_week, WeeklyData.school_id==1, WeeklyData.topic!='', WeeklyData.topic!=None).count()
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()
    teachers = TeacherAccount.query.filter_by(school_id=1).order_by(TeacherAccount.name).all()

    return render_template('admin.html', grades=grades, classes=classes, settings=settings, days_ar=DAYS_AR, days_order=DAYS_ORDER,
                         fixed_schedule=fixed_schedule, sel_fixed_class_id=sel_fixed_class_id, schedule=schedule,
                         selected_class_id=sel_class_id, selected_week=sel_week, locked_view_week=l_week, current_locked_days=locked_days,
                         completion_percent=round(percent,1), completed_classes=completed, pending_classes=pending, logs=logs,
                         total_periods=total_periods, filled_periods=filled_periods, teachers=teachers)

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
        
        settings = {s.key: s.value for s in Setting.query.all()}
        current_week = int(settings.get('current_week', '1'))
        
        import_count = 0
        for _, row in df.iterrows():
            grade_name = str(row[0])
            if not grade_name or grade_name.lower() in ['nan', 'none', '']: continue
            
            # Clean newlines from grade name as well
            grade_name = grade_name.replace('\n', ' ').strip()
            
            # Use Grade Name as Class Name if not specified, or split if "Grade - Class"
            if ' - ' in grade_name:
                parts = grade_name.split(' - ')
                g_n, c_n = parts[0].strip(), parts[1].strip()
            else:
                g_n, c_n = grade_name, "أ" # Default to 'A' if only grade is provided

            cls = get_or_create_class(g_n, c_n)
            
            for day_en, col_range in day_mappings.items():
                for idx, col_idx in enumerate(col_range):
                    period_num = idx + 1
                    if col_idx < len(row):
                        subject_name = str(row[col_idx]).replace('\n', ' ').strip()
                        if subject_name and subject_name.lower() not in ['nan', 'none', '']:
                            # UPSERT logic for Master Schedule
                            db.session.query(Subject).filter_by(class_id=cls.id, day=day_en, period=period_num).delete()
                            db.session.add(Subject(class_id=cls.id, day=day_en, period=period_num, name=subject_name, school_id=1))
                            
                            w_entry = WeeklyData.query.filter_by(class_id=cls.id, week_number=current_week, day=day_en, period=period_num).first()
                            if w_entry:
                                if not (w_entry.topic and w_entry.topic.strip()) and not (w_entry.homework and w_entry.homework.strip()):
                                    w_entry.subject_name = subject_name
                                w_entry.school_id = 1
                            else:
                                db.session.add(WeeklyData(class_id=cls.id, week_number=current_week, day=day_en, period=period_num, subject_name=subject_name, school_id=1))
                            
                            import_count += 1
        
        db.session.commit()
        flash(f'تم استيراد {import_count} حصة بنجاح')
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
    week = request.args.get('week', settings.get('current_week', '1'))
    if g_id in (None, '', 'None'):
        g_id = None
    if c_id in (None, '', 'None'):
        c_id = None
    
    if request.method == 'POST':
        data = request.json
        if c_id and week:
            try:
                saved_count = 0
                current_teacher_id = session.get('teacher_id')
                teacher_name = session.get('teacher_name', session.get('user_role', 'unknown'))
                for e in data.get('entries', []):
                    day = e.get('day')
                    period = int(e.get('period'))
                    topic = e.get('topic', '')
                    homework = e.get('homework', '')
                    w = WeeklyData.query.filter_by(class_id=int(c_id), week_number=int(week), day=day, period=period).first()
                    if not w:
                        master_sub = Subject.query.filter_by(class_id=int(c_id), day=day, period=period).first()
                        sub_name = master_sub.name if master_sub else ''
                        w = WeeklyData(class_id=int(c_id), week_number=int(week), day=day, period=period, subject_name=sub_name, school_id=1)
                        db.session.add(w)
                    w.topic = topic
                    w.homework = homework
                    w.teacher_id = current_teacher_id
                    w.updated_at = datetime.utcnow()
                    saved_count += 1
                db.session.commit()
                log_activity(teacher_name, f'حفظ {saved_count} حصة — الأسبوع {week}')
                return jsonify({'status': 'success', 'saved': saved_count})
            except Exception as e:
                db.session.rollback()
                traceback.print_exc()
                return jsonify({'status': 'error', 'message': str(e)})
        return jsonify({'status': 'error', 'message': 'Missing data'})

    grades = Grade.query.all()
    classes = Class.query.filter_by(grade_id=int(g_id)).all() if g_id else []
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if c_id:
        for f in Subject.query.filter_by(class_id=int(c_id)).all():
            schedule[f.day][f.period]['subject_name'] = f.name
        for w in WeeklyData.query.filter_by(class_id=int(c_id), week_number=int(week)).all():
            schedule[w.day][w.period].update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name
    
    locked = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(week)).all()]
    return render_template('teacher.html', grades=grades, classes=classes, schedule=schedule, selected_grade=g_id, selected_class=c_id, selected_week=week, days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings, locked_days=locked)

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
        return jsonify({'success': True, 'message': 'تم نقل بيانات الدرس بالكامل بنجاح (المادة + التحضير + الواجب)'})

    return jsonify({'success': False, 'message': 'نوع غير معروف'}), 400

@app.route('/student/<int:g_id>/<int:c_id>')
@login_required
def student(g_id, c_id):
    settings = {s.key: s.value for s in Setting.query.all()}
    week = settings.get('current_week', '1')
    grade = db.session.get(Grade, g_id)
    cls = db.session.get(Class, c_id)
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    for f in Subject.query.filter_by(class_id=c_id).all():
        schedule[f.day][f.period]['subject_name'] = f.name
    for w in WeeklyData.query.filter_by(class_id=c_id, week_number=int(week)).all():
        schedule[w.day][w.period].update({'topic': w.topic, 'homework': w.homework})
        if w.subject_name: schedule[w.day][w.period]['subject_name'] = w.subject_name
    return render_template('student.html', schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings, week=week, grade_name=grade.name if grade else '', class_name=cls.name if cls else '')

@app.route('/admin/audit_report')
@admin_required
def audit_report():
    week = request.args.get('week', '1')
    if not week or not week.strip():
        week = '1'
    classes = Class.query.options(joinedload(Class.grade)).all()
    report = []
    for c in classes:
        subjects = Subject.query.filter_by(class_id=c.id, school_id=1).all()
        for subj in subjects:
            wd = WeeklyData.query.filter_by(class_id=c.id, week_number=int(week), day=subj.day, period=subj.period, school_id=1).first()
            if not wd or not wd.topic or not wd.homework:
                report.append({
                    'subject': subj.name,
                    'grade': f"{c.grade.name} - {c.name}",
                    'day': DAYS_AR.get(subj.day, subj.day),
                    'period': subj.period
                })
    return render_template('audit_report.html', report=report, week=week)

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
