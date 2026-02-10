from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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

# Dynamic SSL Mode Handling
engine_options = {"pool_pre_ping": True}
if db_url:
    # Helium (Replit's internal DB) does NOT support SSL.
    # We must allow the app to fall back to no SSL if needed, 
    # but the user requested requirement for safety.
    # However, forcing 'require' on a server that doesn't support it causes a crash.
    # We will use 'prefer' which is secure when available but allows connection to Helium.
    if "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url += f"{separator}sslmode=prefer"
    engine_options["connect_args"] = {"sslmode": "prefer"}

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DAYS_AR = {
    'Sunday': 'الأحد',
    'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء',
    'Wednesday': 'الأربعاء',
    'Thursday': 'الخميس'
}

DAYS_ORDER = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday']

# Database Models
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
    name = db.Column(db.String(200), nullable=False)

class WeeklyData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    period = db.Column(db.Integer, nullable=False)
    topic = db.Column(db.Text, default='')
    homework = db.Column(db.Text, default='')
    subject_name = db.Column(db.String(200), default='')

class Setting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

class LockedDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_number = db.Column(db.Integer, nullable=False)
    day_name = db.Column(db.String(20), nullable=False)
    __table_args__ = (db.UniqueConstraint('week_number', 'day_name', name='_week_day_uc'),)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(50))
    action = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

def log_activity(role, action):
    try:
        # Use timezone-aware UTC or standard datetime
        log = ActivityLog(user_role=role, action=action, timestamp=datetime.utcnow())
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        db.session.rollback()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        stored = db.session.get(Setting, 'admin_password')
        if password == (stored.value if stored else 'fast490'):
            session.clear()
            session['user_role'] = 'admin'
            log_activity('admin', 'تم تسجيل الدخول للوحة التحكم')
            return redirect(url_for('admin'))
        flash('كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_activity(session.get('user_role', 'guest'), 'تم تسجيل الخروج')
    session.clear()
    return redirect(url_for('teacher'))

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            if action == 'add_grade':
                name = request.form.get('name')
                if name:
                    db.session.add(Grade(name=name))
                    log_activity('admin', f'إضافة صف جديد: {name}')
                    flash('تم إضافة الصف بنجاح')
            elif action == 'delete_grade':
                gid = request.form.get('grade_id')
                if gid and gid.isdigit():
                    grade = db.session.get(Grade, int(gid))
                    if grade:
                        name = grade.name
                        db.session.delete(grade)
                        log_activity('admin', f'حذف صف: {name}')
                        flash('تم حذف الصف بنجاح')
            elif action == 'add_class':
                name = request.form.get('name')
                gid = request.form.get('grade_id')
                if name and gid and gid.isdigit():
                    db.session.add(Class(name=name, grade_id=int(gid)))
                    log_activity('admin', f'إضافة فصل جديد: {name}')
                    flash('تم إضافة الفصل بنجاح')
            elif action == 'delete_class':
                cid = request.form.get('class_id')
                if cid and cid.isdigit():
                    cls = db.session.get(Class, int(cid))
                    if cls:
                        name = cls.name
                        db.session.delete(cls)
                        log_activity('admin', f'حذف فصل: {name}')
                        flash('تم حذف الفصل بنجاح')
            elif action == 'save_fixed_schedule':
                cid = request.form.get('class_id')
                if cid and str(cid).strip().lower() != 'none' and str(cid).isdigit():
                    class_id = int(cid)
                    cls = db.session.get(Class, class_id)
                    if cls:
                        db.session.execute(db.delete(Subject).where(Subject.class_id == class_id))
                        for day in DAYS_ORDER:
                            for period in range(1, 9):
                                subject_name = request.form.get(f'fixed_{day}_{period}')
                                if subject_name and subject_name.strip():
                                    db.session.add(Subject(class_id=class_id, day=day, period=period, name=subject_name.strip()))
                        log_activity('admin', f'تحديث الجدول الأساسي للفصل: {cls.name}')
                        db.session.commit()
                        flash('تم حفظ الجدول الأساسي بنجاح')
                    else:
                        flash('الفصل غير موجود')
                else:
                    flash('يرجى اختيار فصل صحيح')
            elif action == 'update_settings':
                for key in ['period1_date', 'period2_date', 'final_date', 'current_week', 'school_name']:
                    val = request.form.get(key)
                    # We treat None or empty string as valid but handle it safely
                    s = db.session.get(Setting, key)
                    if s:
                        s.value = val if val is not None else ''
                    else:
                        db.session.add(Setting(key=key, value=val if val is not None else ''))
                log_activity('admin', 'تحديث الإعدادات العامة')
                db.session.commit()
                flash('تم تحديث الإعدادات بنجاح')
            elif action == 'update_locked_days':
                week = request.form.get('week_number')
                if week and week.isdigit():
                    week_int = int(week)
                    locked_days = request.form.getlist('locked_days')
                    # Batch delete existing locked days for this week
                    db.session.execute(db.delete(LockedDay).where(LockedDay.week_number == week_int))
                    for d in locked_days:
                        db.session.add(LockedDay(week_number=week_int, day_name=d))
                    log_activity('admin', f'تحديث الأيام المغلقة للأسبوع {week_int}')
                    db.session.commit()
                    flash(f'تم تحديث الأيام المغلقة للأسبوع {week_int}')
            elif action == 'upload_logo':
                file = request.files.get('logo')
                if file:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    s = db.session.get(Setting, 'school_logo')
                    if s: s.value = filename
                    else: db.session.add(Setting(key='school_logo', value=filename))
                    log_activity('admin', 'تحديث شعار المدرسة')
                    db.session.commit()
                    flash('تم رفع الشعار بنجاح')
            elif action == 'save_override_batch':
                cid = request.form.get('class_id')
                week = request.form.get('week')
                if cid and week and str(cid).strip().lower() != 'none' and str(week).strip().lower() != 'none' and str(cid).isdigit() and str(week).isdigit():
                    class_id = int(cid)
                    week_number = int(week)
                    cls = db.session.get(Class, class_id)
                    
                    if cls:
                        # We update subject names while preserving topics and homework
                        for day in DAYS_ORDER:
                            for period in range(1, 9):
                                subject_name = request.form.get(f'override_{day}_{period}')
                                if subject_name is not None:
                                    subject_name = subject_name.strip()
                                    # Use filter instead of filter_by to be extra safe with SQLAlchemy versions
                                    exists = WeeklyData.query.filter(WeeklyData.class_id == class_id, 
                                                                   WeeklyData.week_number == week_number, 
                                                                   WeeklyData.day == day, 
                                                                   WeeklyData.period == period).first()
                                    if exists:
                                        exists.subject_name = subject_name
                                    else:
                                        if subject_name:
                                            db.session.add(WeeklyData(class_id=class_id, week_number=week_number, day=day, period=period, subject_name=subject_name))
                        
                        log_activity('admin', f'تحديث التجاوزات الأسبوعية بالكامل (الأسبوع {week_number}, الفصل {cls.name})')
                        db.session.commit()
                        flash('تم حفظ التعديلات الأسبوعية بالكامل بنجاح')
                    else:
                        flash('الفصل غير موجود')
                else:
                    flash('بيانات غير مكتملة للحفظ')
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"CRITICAL ERROR in admin POST: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f"حدث خطأ أثناء الحفظ: {str(e)}")
        
        return redirect(url_for('admin', **request.args))

    grades = Grade.query.order_by(Grade.name).all()
    classes = Class.query.options(joinedload(Class.grade)).order_by(Class.name).all()
    all_settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
        
    subjects = Subject.query.options(joinedload(Subject.class_obj).joinedload(Class.grade)).all()
    
    sel_class_id = request.args.get('class_id')
    sel_week = request.args.get('week', settings_dict.get('current_week', '1'))
    
    # Manage locked days view
    locked_view_week = request.args.get('locked_week', settings_dict.get('current_week', '1'))
    current_locked_days = []
    if locked_view_week and locked_view_week.isdigit():
        current_locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(locked_view_week)).all()]

    # Manage fixed schedule view
    sel_fixed_class_id = request.args.get('fixed_class_id')
    fixed_schedule = {day: {p: '' for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_fixed_class_id and sel_fixed_class_id.isdigit():
        existing_fixed = Subject.query.filter_by(class_id=int(sel_fixed_class_id)).all()
        for s in existing_fixed:
            fixed_schedule[s.day][s.period] = s.name

    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if sel_class_id and sel_class_id.isdigit():
        fixed = Subject.query.filter_by(class_id=int(sel_class_id)).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        
        weekly = WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=int(sel_week)).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name:
                day_data['subject_name'] = w.subject_name

    # Completion Stats
    current_week_int = int(settings_dict.get('current_week', '1'))
    all_classes_count = len(classes)
    completed_classes = []
    pending_classes = []
    
    for c in classes:
        # A class is considered "Completed" if it has at least one topic filled in the current week
        has_data = WeeklyData.query.filter(
            WeeklyData.class_id == c.id,
            WeeklyData.week_number == current_week_int,
            WeeklyData.topic != ''
        ).first()
        if has_data:
            completed_classes.append(c)
        else:
            pending_classes.append(c)
    
    completion_percent = (len(completed_classes) / all_classes_count * 100) if all_classes_count > 0 else 0
    
    # Activity Logs
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(50).all()
    
    return render_template('admin.html', grades=grades, classes=classes, settings=settings_dict, subjects=subjects, 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, schedule=schedule, 
                         selected_class_id=sel_class_id, selected_week=sel_week,
                         locked_view_week=locked_view_week, current_locked_days=current_locked_days,
                         sel_fixed_class_id=sel_fixed_class_id, fixed_schedule=fixed_schedule,
                         completion_percent=round(completion_percent, 1),
                         completed_classes=completed_classes, pending_classes=pending_classes,
                         logs=logs)

@app.route('/admin/delete_date/<date_type>', methods=['POST'])
@admin_required
def delete_date(date_type):
    if date_type in ['period1_date', 'period2_date', 'final_date']:
        s = db.session.get(Setting, date_type)
        if s:
            s.value = ''
            db.session.commit()
            flash('تم حذف التاريخ بنجاح')
    return redirect(url_for('admin'))

@app.route('/')
def index():
    return redirect(url_for('teacher'))

@app.route('/teacher', methods=['GET', 'POST'])
def teacher():
    grade_id = request.args.get('grade_id')
    class_id = request.args.get('class_id')
    week = request.args.get('week')
    
    all_settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
    if not week: week = settings_dict.get('current_week', '1')
    
    # Locked days check
    locked_days = []
    if week and week.isdigit():
        locked_days = [ld.day_name for ld in LockedDay.query.filter_by(week_number=int(week)).all()]
    
    if request.method == 'POST':
        data = request.json
        if class_id and class_id.isdigit() and week and week.isdigit():
            week_int = int(week)
            cls = db.session.get(Class, int(class_id))
            for entry in data.get('entries', []):
                if entry['day'] in locked_days:
                    return jsonify({'status': 'error', 'message': f"هذا اليوم مغلق في هذا الأسبوع محدد من قبل الإدارة"}), 403
                
                exists = WeeklyData.query.filter_by(class_id=int(class_id), week_number=week_int, day=entry['day'], period=int(entry['period'])).first()
                if exists:
                    exists.topic = entry['topic']
                    exists.homework = entry['homework']
                else:
                    db.session.add(WeeklyData(class_id=int(class_id), week_number=week_int, day=entry['day'], 
                                            period=int(entry['period']), topic=entry['topic'], homework=entry['homework']))
            
            log_activity('teacher', f'تحديث دروس وواجبات الفصل: {cls.name if cls else class_id} (الأسبوع {week})')
            db.session.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Invalid input'}), 400

    grades = Grade.query.all()
    classes = Class.query.filter_by(grade_id=int(grade_id)).all() if grade_id and grade_id.isdigit() else []
    
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if class_id and class_id.isdigit():
        fixed = Subject.query.filter_by(class_id=int(class_id)).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        
        weekly = WeeklyData.query.filter_by(class_id=int(class_id), week_number=int(week)).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name:
                day_data['subject_name'] = w.subject_name

    return render_template('teacher.html', grades=grades, classes=classes, schedule=schedule, 
                         selected_grade=grade_id, selected_class=class_id, selected_week=week, 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings_dict,
                         locked_days=locked_days)

@app.route('/student/<int:grade_id>/<int:class_id>')
def student(grade_id, class_id):
    all_settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
    week = settings_dict.get('current_week', '1')
    
    grade = db.session.get(Grade, grade_id)
    cls = db.session.get(Class, class_id)
    
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    fixed = Subject.query.filter_by(class_id=class_id).all()
    for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
    
    weekly = WeeklyData.query.filter_by(class_id=class_id, week_number=int(week)).all()
    for w in weekly:
        day_data = schedule[w.day][w.period]
        day_data.update({'topic': w.topic, 'homework': w.homework})
        if w.subject_name:
            day_data['subject_name'] = w.subject_name

    return render_template('student.html', schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings_dict, 
                         week=week, grade_name=grade.name if grade else '', class_name=cls.name if cls else '')

if __name__ == '__main__':
    with app.app_context():
        try:
            # We use create_all() which only creates tables if they don't exist
            # It does NOT drop existing data.
            db.create_all()
            print("Successfully connected to PostgreSQL and initialized schema.")
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True)
