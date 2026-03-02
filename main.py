from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import os
import json
import pandas as pd
import io
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
    # To support both local development and production environments,
    # we use 'prefer' which attempts SSL but falls back gracefully if unsupported.
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
    school_id = db.Column(db.Integer, nullable=True)

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
                    try:
                        new_grade = Grade(name=name, school_id=None)
                        db.session.add(new_grade)
                        db.session.commit()
                        log_activity('admin', f'إضافة صف جديد: {name}')
                        flash('تم إضافة الصف بنجاح')
                    except Exception as e:
                        db.session.rollback()
                        print(f"Error adding grade: {e}")
                        flash(f"خطأ في إضافة الصف: {e}")
            elif action == 'delete_grade':
                gid = request.form.get('grade_id')
                if gid and gid.isdigit():
                    grade_id = int(gid)
                    grade = db.session.get(Grade, grade_id)
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
            elif action == 'add_class':
                name = request.form.get('name')
                gid = request.form.get('grade_id')
                if name and gid and gid.isdigit():
                    try:
                        new_class = Class(name=name, grade_id=int(gid), school_id=None)
                        db.session.add(new_class)
                        db.session.commit()
                        log_activity('admin', f'إضافة فصل جديد: {name}')
                        flash('تم إضافة الفصل بنجاح')
                    except Exception as e:
                        db.session.rollback()
                        print(f"Error adding class: {e}")
                        flash(f"خطأ في إضافة الفصل: {e}")
            elif action == 'delete_class':
                cid = request.form.get('class_id')
                if cid and cid.isdigit():
                    class_id = int(cid)
                    # Explicitly delete related data to ensure cascade-like behavior
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
                if cid and str(cid).strip().lower() != 'none':
                    try:
                        class_id = int(cid)
                        cls = db.session.get(Class, class_id)
                        if cls:
                            # Handle master swaps first (topic/homework migration)
                            master_swaps = request.form.getlist('master_swaps[]')
                            for swap_json in master_swaps:
                                try:
                                    swap = json.loads(swap_json)
                                    f_day, f_period = swap['from_day'], int(swap['from_period'])
                                    t_day, t_period = swap['to_day'], int(swap['to_period'])
                                    
                                    from_entries = WeeklyData.query.filter_by(class_id=class_id, day=f_day, period=f_period).all()
                                    to_entries = WeeklyData.query.filter_by(class_id=class_id, day=t_day, period=t_period).all()
                                    
                                    temp_from = []
                                    for e in from_entries:
                                        temp_from.append({'week': e.week_number, 'topic': e.topic, 'hw': e.homework})
                                        db.session.delete(e)
                                        
                                    temp_to = []
                                    for e in to_entries:
                                        temp_to.append({'week': e.week_number, 'topic': e.topic, 'hw': e.homework})
                                        db.session.delete(e)
                                    
                                    db.session.flush() 
                                    
                                    for e in temp_from:
                                        db.session.add(WeeklyData(class_id=class_id, week_number=e['week'], day=t_day, period=t_period, topic=e['topic'], homework=e['hw']))
                                    for e in temp_to:
                                        db.session.add(WeeklyData(class_id=class_id, week_number=e['week'], day=f_day, period=f_period, topic=e['topic'], homework=e['hw']))
                                        
                                except Exception as e:
                                    print(f"Error processing master swap: {e}")
                            
                            # Clean and insert master subjects
                            db.session.query(Subject).filter_by(class_id=class_id).delete()
                            db.session.flush()
                            
                            added_count = 0
                            for day in DAYS_ORDER:
                                for period in range(1, 9):
                                    subject_name = request.form.get(f'fixed_{day}_{period}')
                                    if subject_name is not None:
                                        subject_name = subject_name.strip()
                                        
                                        # Force sync labels in WeeklyData for all weeks
                                        db.session.query(WeeklyData).filter(
                                            WeeklyData.class_id == class_id,
                                            WeeklyData.day == day,
                                            WeeklyData.period == period
                                        ).update({"subject_name": subject_name}, synchronize_session=False)
                                        
                                        if subject_name:
                                            # Explicitly set school_id=None to avoid constraint issues if default is missing
                                            db.session.add(Subject(class_id=class_id, day=day, period=period, name=subject_name, school_id=None))
                                            added_count += 1
                            
                            db.session.commit()
                            log_activity('admin', f'تحديث الجدول الأساسي للفصل: {cls.name} ({added_count} مادة)')
                            flash('تم حفظ الجدول الأساسي بنجاح')
                        else:
                            flash('الفصل غير موجود')
                    except Exception as e:
                        db.session.rollback()
                        print(f"ERROR in save_fixed_schedule: {e}")
                        import traceback
                        traceback.print_exc()
                        flash(f"حدث خطأ أثناء الحفظ: {str(e)}")
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
                if cid and week and str(cid).strip().lower() != 'none' and str(week).strip().lower() != 'none':
                    try:
                        class_id = int(cid)
                        week_number = int(week)
                        cls = db.session.get(Class, class_id)
                        
                        if cls:
                            # Handle swaps if any
                            swaps = request.form.getlist('swaps[]')
                            for swap_json in swaps:
                                swap = json.loads(swap_json)
                                f_day, f_period = swap['from_day'], int(swap['from_period'])
                                t_day, t_period = swap['to_day'], int(swap['to_period'])
                                
                                # Find both entries
                                entry_from = WeeklyData.query.filter_by(class_id=class_id, week_number=week_number, day=f_day, period=f_period).first()
                                entry_to = WeeklyData.query.filter_by(class_id=class_id, week_number=week_number, day=t_day, period=t_period).first()
                                
                                if entry_from or entry_to:
                                    # Swap topics and homework
                                    f_topic = entry_from.topic if entry_from else ''
                                    f_hw = entry_from.homework if entry_from else ''
                                    t_topic = entry_to.topic if entry_to else ''
                                    t_hw = entry_to.homework if entry_to else ''
                                    
                                    if entry_from:
                                        entry_from.topic = t_topic
                                        entry_from.homework = t_hw
                                    elif t_topic or t_hw:
                                        new_entry_f = WeeklyData(class_id=class_id, week_number=week_number, day=f_day, period=f_period, topic=t_topic, homework=t_hw)
                                        db.session.add(new_entry_f)
                                        
                                    if entry_to:
                                        entry_to.topic = f_topic
                                        entry_to.homework = f_hw
                                    elif f_topic or f_hw:
                                        new_entry_t = WeeklyData(class_id=class_id, week_number=week_number, day=t_day, period=t_period, topic=f_topic, homework=f_hw)
                                        db.session.add(new_entry_t)

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
                    except ValueError:
                        flash('بيانات غير صالحة للحفظ')
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

    current_week_int = int(settings_dict.get('current_week', '1'))
    all_classes_count = len(classes)
    completed_classes = []
    pending_classes = []
    
    for c in classes:
        # A class is considered "Completed" if it has at least one topic AND homework filled in the current week
        has_data = WeeklyData.query.filter(
            WeeklyData.class_id == c.id,
            WeeklyData.week_number == current_week_int,
            WeeklyData.topic != '',
            WeeklyData.topic != None,
            WeeklyData.homework != '',
            WeeklyData.homework != None
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

@app.route('/admin/audit_report')
@admin_required
def audit_report_view():
    week = request.args.get('week', db.session.get(Setting, 'current_week').value if db.session.get(Setting, 'current_week') else '1')
    try:
        week_int = int(week)
    except ValueError:
        week_int = 1
        
    classes_list = Class.query.options(joinedload(Class.grade)).all()
    report = []
    
    for c in classes_list:
        # Get all subjects for this class from Master Schedule
        subjects = Subject.query.filter_by(class_id=c.id).all()
        for s in subjects:
            # Check for current week's completion
            override = WeeklyData.query.filter_by(class_id=c.id, week_number=week_int, day=s.day, period=s.period).first()
            
            subject_name = override.subject_name if (override and override.subject_name) else s.name
            topic = override.topic if override else ''
            homework = override.homework if override else ''
            
            # Missing if topic OR homework is empty for a scheduled master subject
            if not topic or not topic.strip() or not homework or not homework.strip():
                report.append({
                    'subject': subject_name,
                    'grade': f"{c.grade.name} - {c.name}",
                    'day': DAYS_AR.get(s.day, s.day),
                    'period': s.period
                })
                
    return render_template('audit_report.html', report=report, week=week_int)

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
    
    if not grade or not cls:
        return "الصف أو الفصل غير موجود", 404
        
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

# Audit report logic moved to audit_report_view

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

@app.route('/admin/upload_master', methods=['POST'])
@admin_required
def upload_master():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('لم يتم اختيار ملف')
        return redirect(url_for('admin'))
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        df.columns = [str(c).strip() for c in df.columns]
        
        class_col = df.columns[0]
        for col in df.columns:
            if any(kw in col.lower() for kw in ['صف', 'فصل', 'grade', 'class']):
                class_col = col
                break
        
        import_count = 0
        for _, row in df.iterrows():
            class_full_name = str(row[class_col]).strip()
            if not class_full_name or class_full_name.lower() == 'nan':
                continue
                
            cls = None
            if ' - ' in class_full_name:
                parts = class_full_name.split(' - ', 1)
                g_name, c_name = parts[0].strip(), parts[1].strip()
                cls = get_or_create_class(g_name, c_name)
            else:
                cls = Class.query.filter(Class.name == class_full_name).first()
                if not cls:
                    cls = get_or_create_class('عام', class_full_name)
                
            if not cls:
                continue
                
            for col in df.columns:
                if col == class_col: continue
                
                subject_name = str(row[col]).strip()
                if not subject_name or subject_name.lower() == 'nan':
                    subject_name = "" 
                
                target_day = None
                target_period = None
                
                for day_en, day_ar in DAYS_AR.items():
                    if day_ar in col or day_en.lower() in col.lower():
                        target_day = day_en
                        break
                
                import re
                nums = re.findall(r'\d+', col)
                if nums:
                    target_period = int(nums[0])
                
                if target_day and target_period and 1 <= target_period <= 8:
                    db.session.query(Subject).filter_by(class_id=cls.id, day=target_day, period=target_period).delete()
                    if subject_name:
                        db.session.add(Subject(class_id=cls.id, day=target_day, period=target_period, name=subject_name))
                    db.session.query(WeeklyData).filter_by(class_id=cls.id, day=target_day, period=target_period).update({"subject_name": subject_name})
                    import_count += 1
                
        db.session.commit()
        log_activity('admin', f'تم استيراد الجدول من Excel ({import_count} حصة)')
        flash(f'تم استيراد {import_count} حصة بنجاح وتحديث الصفوف والفصول')
        
    except Exception as e:
        db.session.rollback()
        print(f'Excel Upload Error: {e}')
        flash(f'خطأ في معالجة الملف: {str(e)}')
        
    return redirect(url_for('admin'))
    
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Mapping Logic: Rows are Grade/Class, Columns are Day/Period
        # Expected Format: First column is Grade/Class name
        # Other columns should match Day_Period pattern or be identified by order
        
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        
        # Find the class column (usually the first one or named 'الصف', 'الفصل', 'Grade', 'Class')
        class_col = df.columns[0]
        for col in df.columns:
            if any(kw in col for kw in ['صف', 'فصل', 'grade', 'class']):
                class_col = col
                break
        
        import_count = 0
        for _, row in df.iterrows():
            class_full_name = str(row[class_col]).strip()
            if not class_full_name or class_full_name.lower() == 'nan':
                continue
                
            # Try to find class. Format could be "Grade - Class" or just "Class"
            cls = None
            if ' - ' in class_full_name:
                g_name, c_name = class_full_name.split(' - ', 1)
                cls = Class.query.join(Grade).filter(Grade.name == g_name, Class.name == c_name).first()
            
            if not cls:
                cls = Class.query.filter(Class.name == class_full_name).first()
                
            if not cls:
                # If class doesn't exist, skip or handle (here we skip for safety)
                continue
                
            # Map periods
            # We look for columns that might indicate day and period
            # Common patterns: "الأحد 1", "Sunday 1", "1", etc.
            for col in df.columns:
                if col == class_col: continue
                
                subject_name = str(row[col]).strip()
                if not subject_name or subject_name.lower() == 'nan':
                    subject_name = "" # Empty slot
                
                # Try to parse day and period from column name
                target_day = None
                target_period = None
                
                # Check for day name in column
                for day_en, day_ar in DAYS_AR.items():
                    if day_ar in col or day_en.lower() in col.lower():
                        target_day = day_en
                        break
                
                # Check for period number in column
                import re
                nums = re.findall(r'\d+', col)
                if nums:
                    target_period = int(nums[0])
                
                if target_day and target_period and 1 <= target_period <= 8:
                    # Clear existing and add new
                    db.session.query(Subject).filter_by(class_id=cls.id, day=target_day, period=target_period).delete()
                    if subject_name:
                        db.session.add(Subject(class_id=cls.id, day=target_day, period=target_period, name=subject_name))
                    # Sync subject_name in WeeklyData for existing entries
                    db.session.query(WeeklyData).filter_by(class_id=cls.id, day=target_day, period=target_period).update({"subject_name": subject_name})
                    import_count += 1
                
        db.session.commit()
        log_activity('admin', f'تم استيراد الجدول من Excel ({import_count} حصة)')
        flash(f'تم استيراد {import_count} حصة بنجاح')
        
    except Exception as e:
        db.session.rollback()
        print(f"Excel Upload Error: {e}")
        flash(f'خطأ أثناء معالجة الملف: {str(e)}')
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        try:
            # We use create_all() which only creates tables if they don't exist
            # It does NOT drop existing data.
            db.create_all()
            print("Successfully connected to PostgreSQL and initialized schema.")
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
    # If using in-memory SQLite, recreate tables
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
