from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import os
import json
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-fast490')

# PostgreSQL Configuration
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine_options = {"pool_pre_ping": True}
if db_url:
    if "127.0.0.1" not in db_url and "localhost" not in db_url and "helium" not in db_url:
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}sslmode=require"
        engine_options["connect_args"] = {"sslmode": "require"}
    else:
        if "sslmode" not in db_url:
            separator = "&" if "?" in db_url else "?"
            db_url += f"{separator}sslmode=disable"
        engine_options["connect_args"] = {"sslmode": "disable"}

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DAYS_AR = {'Sunday': 'الأحد', 'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء', 'Wednesday': 'الأربعاء', 'Thursday': 'الخميس'}
DAYS_ORDER = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday']

# Database Models
class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    logo = db.Column(db.String(200))
    admin_username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    grades = db.relationship('Grade', backref='school', cascade="all, delete-orphan", lazy=True)
    settings = db.relationship('Setting', backref='school', cascade="all, delete-orphan", lazy=True)
    locked_days = db.relationship('LockedDay', backref='school', cascade="all, delete-orphan", lazy=True)
    activity_logs = db.relationship('ActivityLog', backref='school', cascade="all, delete-orphan", lazy=True)

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    classes = db.relationship('Class', backref='grade', cascade="all, delete-orphan", lazy=True)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey('grade.id'), nullable=False)
    subjects = db.relationship('Subject', backref='class_obj', cascade="all, delete-orphan", lazy=True)
    weekly_data = db.relationship('WeeklyData', backref='class_obj', cascade="all, delete-orphan", lazy=True)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)

class WeeklyData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.Text, default='')
    homework = db.Column(db.Text, default='')
    subject_name = db.Column(db.String(200), default='')

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text)

class LockedDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    day_name = db.Column(db.String(20), nullable=False)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    user_role = db.Column(db.String(50))
    action = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def log_activity(school_id, role, action):
    try:
        log = ActivityLog(school_id=school_id, user_role=role, action=action)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin' or not session.get('school_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'super_admin':
            return redirect(url_for('super_admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/super-admin/login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        if request.form.get('username') == 'ahmed' and request.form.get('password') == 'fast490':
            session['user_role'] = 'super_admin'
            return redirect(url_for('super_admin_dashboard'))
        flash('خطأ في البيانات')
    return render_template('super_admin_login.html')

@app.route('/super-admin')
@super_admin_required
def super_admin_dashboard():
    schools = School.query.all()
    return render_template('super_admin.html', schools=schools)

@app.route('/super-admin/add-school', methods=['POST'])
@super_admin_required
def add_school():
    name = request.form.get('name')
    slug = request.form.get('slug')
    user = request.form.get('username')
    pw = request.form.get('password')
    if name and slug and user and pw:
        new_school = School(name=name, slug=slug, admin_username=user, password=pw)
        db.session.add(new_school)
        db.session.commit()
        flash('تم إضافة المدرسة بنجاح')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super-admin/toggle-school/<int:id>')
@super_admin_required
def toggle_school(id):
    s = School.query.get_or_404(id)
    s.is_active = not s.is_active
    db.session.commit()
    return redirect(url_for('super_admin_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        password = request.form.get('password')
        school = School.query.filter_by(admin_username=user, password=password, is_active=True).first()
        if school:
            session.clear()
            session['user_role'] = 'admin'
            session['school_id'] = school.id
            log_activity(school.id, 'admin', 'تم تسجيل الدخول للوحة التحكم')
            return redirect(url_for('admin', school_slug=school.slug))
        flash('بيانات الدخول غير صحيحة أو المدرسة غير نشطة')
    return render_template('login.html')

@app.route('/<school_slug>/admin', methods=['GET', 'POST'])
@admin_required
def admin(school_slug):
    school = School.query.filter_by(slug=school_slug, is_active=True).first_or_404()
    if session.get('school_id') != school.id:
        abort(403)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_grade':
            name = request.form.get('name')
            if name:
                db.session.add(Grade(name=name, school_id=school.id))
                log_activity(school.id, 'admin', f'إضافة صف جديد: {name}')
                flash('تم إضافة الصف بنجاح')
        elif action == 'delete_grade':
            gid = request.form.get('grade_id')
            if gid and str(gid).strip().isdigit():
                grade = Grade.query.filter_by(id=int(gid), school_id=school.id).first()
                if grade:
                    name = grade.name
                    db.session.delete(grade)
                    log_activity(school.id, 'admin', f'حذف صف: {name}')
                    flash('تم حذف الصف بنجاح')
        elif action == 'add_class':
            name = request.form.get('name')
            gid = request.form.get('grade_id')
            if name and gid and str(gid).strip().isdigit():
                db.session.add(Class(name=name, grade_id=int(gid), school_id=school.id))
                log_activity(school.id, 'admin', f'إضافة فصل جديد: {name}')
                flash('تم إضافة الفصل بنجاح')
        elif action == 'delete_class':
            cid = request.form.get('class_id')
            if cid and str(cid).strip().isdigit():
                cls = Class.query.filter_by(id=int(cid), school_id=school.id).first()
                if cls:
                    name = cls.name
                    db.session.delete(cls)
                    log_activity(school.id, 'admin', f'حذف فصل: {name}')
                    flash('تم حذف الفصل بنجاح')
        elif action == 'save_fixed_schedule':
            cid = request.form.get('class_id')
            if cid and str(cid).strip().isdigit():
                class_id = int(cid)
                cls = Class.query.filter_by(id=class_id, school_id=school.id).first()
                if cls:
                    Subject.query.filter_by(class_id=class_id, school_id=school.id).delete()
                    for day in DAYS_ORDER:
                        for period in range(1, 9):
                            subject_name = request.form.get(f'fixed_{day}_{period}')
                            if subject_name and subject_name.strip():
                                db.session.add(Subject(class_id=class_id, day=day, period=period, name=subject_name.strip(), school_id=school.id))
                    log_activity(school.id, 'admin', f'تحديث الجدول الأساسي للفصل: {cls.name}')
                    db.session.commit()
                    flash('تم حفظ الجدول الأساسي بنجاح')
        elif action == 'update_settings':
            for key in ['period1_date', 'period2_date', 'final_date', 'current_week', 'school_name']:
                val = request.form.get(key)
                if val is not None:
                    s = Setting.query.filter_by(key=key, school_id=school.id).first()
                    if s: s.value = val
                    else: db.session.add(Setting(key=key, value=val, school_id=school.id))
            log_activity(school.id, 'admin', 'تحديث الإعدادات العامة')
            db.session.commit()
            flash('تم تحديث الإعدادات بنجاح')
        elif action == 'update_locked_days':
            week = request.form.get('week_number')
            if week and str(week).strip().isdigit():
                week_int = int(week)
                locked_days = request.form.getlist('locked_days')
                LockedDay.query.filter_by(week_number=week_int, school_id=school.id).delete()
                for d in locked_days:
                    db.session.add(LockedDay(week_number=week_int, day_name=d, school_id=school.id))
                log_activity(school.id, 'admin', f'تحديث الأيام المغلقة للأسبوع {week_int}')
                db.session.commit()
                flash(f'تم تحديث الأيام المغلقة للأسبوع {week_int}')
        elif action == 'upload_logo':
            file = request.files.get('logo')
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                s = Setting.query.filter_by(key='school_logo', school_id=school.id).first()
                if s: s.value = filename
                else: db.session.add(Setting(key='school_logo', value=filename, school_id=school.id))
                log_activity(school.id, 'admin', 'تحديث شعار المدرسة')
                db.session.commit()
                flash('تم رفع الشعار بنجاح')
        elif action == 'save_override_batch':
            cid = request.form.get('class_id')
            week = request.form.get('week')
            if cid and week and str(cid).strip().isdigit() and str(week).strip().isdigit():
                class_id = int(cid)
                week_number = int(week)
                cls = Class.query.filter_by(id=class_id, school_id=school.id).first()
                if cls:
                    for day in DAYS_ORDER:
                        for period in range(1, 9):
                            subject_name = request.form.get(f'override_{day}_{period}')
                            if subject_name is not None:
                                subject_name = subject_name.strip()
                                exists = WeeklyData.query.filter_by(class_id=class_id, week_number=week_number, day=day, period=period, school_id=school.id).first()
                                if exists:
                                    exists.subject_name = subject_name
                                else:
                                    if subject_name:
                                        db.session.add(WeeklyData(class_id=class_id, week_number=week_number, day=day, period=period, subject_name=subject_name, school_id=school.id))
                    log_activity(school.id, 'admin', f'تحديث التجاوزات الأسبوعية بالكامل (الأسبوع {week_number}, الفصل {cls.name})')
                    db.session.commit()
                    flash('تم حفظ التعديلات الأسبوعية بالكامل بنجاح')
        db.session.commit()
        return redirect(url_for('admin', school_slug=school.slug, **request.args))

    grades = Grade.query.filter_by(school_id=school.id).order_by(Grade.name).all()
    classes = Class.query.options(joinedload(Class.grade)).filter_by(school_id=school.id).order_by(Class.name).all()
    all_settings = Setting.query.filter_by(school_id=school.id).all()
    settings_dict = {s.key: s.value for s in all_settings}
    
    sel_class_id = request.args.get('class_id')
    sel_week = request.args.get('week', settings_dict.get('current_week', '1'))
    locked_view_week = request.args.get('locked_week', settings_dict.get('current_week', '1'))
    current_locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(locked_view_week) if (locked_view_week and str(locked_view_week).strip().isdigit()) else 1, school_id=school.id).all()]
    
    sel_fixed_class_id = request.args.get('fixed_class_id')
    fixed_schedule = {day: {p: '' for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_fixed_class_id and str(sel_fixed_class_id).strip().isdigit():
        existing_fixed = Subject.query.filter_by(class_id=int(sel_fixed_class_id), school_id=school.id).all()
        for s in existing_fixed: fixed_schedule[s.day][s.period] = s.name

    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_class_id and str(sel_class_id).strip().isdigit():
        fixed = Subject.query.filter_by(class_id=int(sel_class_id), school_id=school.id).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        weekly = WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=int(sel_week) if (sel_week and str(sel_week).strip().isdigit()) else 1, school_id=school.id).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: day_data['subject_name'] = w.subject_name

    current_week_str = settings_dict.get('current_week', '1')
    current_week_int = int(current_week_str) if (current_week_str and current_week_str.strip().isdigit()) else 1
    all_classes_count = len(classes)
    completed_classes = []
    pending_classes = []
    for c in classes:
        has_data = WeeklyData.query.filter(WeeklyData.class_id == c.id, WeeklyData.week_number == current_week_int, WeeklyData.topic != '', WeeklyData.school_id == school.id).first()
        if has_data: completed_classes.append(c)
        else: pending_classes.append(c)
    
    completion_percent = (len(completed_classes) / all_classes_count * 100) if all_classes_count > 0 else 0
    logs = ActivityLog.query.filter_by(school_id=school.id).order_by(ActivityLog.timestamp.desc()).limit(50).all()
    
    return render_template('admin.html', school=school, grades=grades, classes=classes, settings=settings_dict, subjects=[], 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, schedule=schedule, 
                         selected_class_id=sel_class_id, selected_week=sel_week,
                         locked_view_week=locked_view_week, current_locked_days=current_locked_days,
                         sel_fixed_class_id=sel_fixed_class_id, fixed_schedule=fixed_schedule,
                         completion_percent=round(completion_percent, 1),
                         completed_classes=completed_classes, pending_classes=pending_classes, logs=logs)

@app.route('/<school_slug>/teacher', methods=['GET', 'POST'])
def teacher(school_slug):
    school = School.query.filter_by(slug=school_slug, is_active=True).first_or_404()
    grade_id = request.args.get('grade_id')
    class_id = request.args.get('class_id')
    week = request.args.get('week')
    all_settings = Setting.query.filter_by(school_id=school.id).all()
    settings_dict = {s.key: s.value for s in all_settings}
    if not week: week = settings_dict.get('current_week', '1')
    locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(week) if (week and str(week).strip().isdigit()) else 1, school_id=school.id).all()]
    
    if request.method == 'POST':
        data = request.json
        if class_id and str(class_id).strip().isdigit() and week and str(week).strip().isdigit():
            week_int = int(week)
            cls = Class.query.filter_by(id=int(class_id), school_id=school.id).first()
            if cls:
                for entry in data.get('entries', []):
                    if entry['day'] in locked_days:
                        return jsonify({'status': 'error', 'message': f"هذا اليوم مغلق في هذا الأسبوع محدد من قبل الإدارة"}), 403
                    exists = WeeklyData.query.filter_by(class_id=cls.id, week_number=week_int, day=entry['day'], period=int(entry['period']), school_id=school.id).first()
                    if exists:
                        exists.topic = entry['topic']
                        exists.homework = entry['homework']
                    else:
                        db.session.add(WeeklyData(class_id=cls.id, week_number=week_int, day=entry['day'], period=int(entry['period']), topic=entry['topic'], homework=entry['homework'], school_id=school.id))
                log_activity(school.id, 'teacher', f'تحديث دروس وواجبات الفصل: {cls.name} (الأسبوع {week})')
                db.session.commit()
                return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400

    grades = Grade.query.filter_by(school_id=school.id).all()
    classes = Class.query.filter_by(grade_id=int(grade_id), school_id=school.id).all() if grade_id and str(grade_id).strip().isdigit() else []
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if class_id and str(class_id).strip().isdigit():
        fixed = Subject.query.filter_by(class_id=int(class_id), school_id=school.id).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        weekly = WeeklyData.query.filter_by(class_id=int(class_id), week_number=int(week) if (week and str(week).strip().isdigit()) else 1, school_id=school.id).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: day_data['subject_name'] = w.subject_name
    return render_template('teacher.html', school=school, grades=grades, classes=classes, schedule=schedule, 
                         selected_grade=grade_id, selected_class=class_id, selected_week=week, 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings_dict, locked_days=locked_days)

@app.route('/<school_slug>/student/<int:grade_id>/<int:class_id>')
def student(school_slug, grade_id, class_id):
    school = School.query.filter_by(slug=school_slug, is_active=True).first_or_404()
    all_settings = Setting.query.filter_by(school_id=school.id).all()
    settings_dict = {s.key: s.value for s in all_settings}
    week = settings_dict.get('current_week', '1')
    grade = Grade.query.filter_by(id=grade_id, school_id=school.id).first()
    cls = Class.query.filter_by(id=class_id, school_id=school.id).first()
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if cls:
        fixed = Subject.query.filter_by(class_id=cls.id, school_id=school.id).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        weekly = WeeklyData.query.filter_by(class_id=cls.id, week_number=int(week) if (week and str(week).strip().isdigit()) else 1, school_id=school.id).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name: day_data['subject_name'] = w.subject_name
    return render_template('student.html', school=school, schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings_dict, 
                         week=week, grade_name=grade.name if grade else '', class_name=cls.name if cls else '')

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            print("Successfully connected to PostgreSQL and initialized schema.")
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True)
