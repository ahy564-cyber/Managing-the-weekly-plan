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
import re
import traceback

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-fast490')

db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine_options = {"pool_pre_ping": True}
if db_url:
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

class Setting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    school_id = db.Column(db.Integer, nullable=True)

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
        log = ActivityLog(user_role=role, action=action, timestamp=datetime.utcnow())
        db.session.add(log)
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
    return render_template('index.html')

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
                        db.session.add(Grade(name=name))
                        db.session.commit()
                        log_activity('admin', f'إضافة صف جديد: {name}')
                        flash('تم إضافة الصف بنجاح')
                    except Exception as e:
                        db.session.rollback()
                        flash(f"خطأ: {e}")
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
                                    db.session.add(Subject(class_id=class_id, day=day, period=period, name=name))
                                    db.session.query(WeeklyData).filter_by(class_id=class_id, day=day, period=period).update({"subject_name": name})
                        db.session.commit()
                        flash('تم الحفظ بنجاح')
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
                        db.session.add(LockedDay(week_number=w_int, day_name=d))
                    db.session.commit()
                    flash('تم تحديث القفل')
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
    completed = [c for c in classes if WeeklyData.query.filter(WeeklyData.class_id==c.id, WeeklyData.week_number==c_week, WeeklyData.topic!='', WeeklyData.topic!=None).first()]
    pending = [c for c in classes if c not in completed]
    percent = (len(completed)/len(classes)*100) if classes else 0
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(20).all()

    return render_template('admin.html', grades=grades, classes=classes, settings=settings, days_ar=DAYS_AR, days_order=DAYS_ORDER,
                         fixed_schedule=fixed_schedule, sel_fixed_class_id=sel_fixed_class_id, schedule=schedule,
                         selected_class_id=sel_class_id, selected_week=sel_week, locked_view_week=l_week, current_locked_days=locked_days,
                         completion_percent=round(percent,1), completed_classes=completed, pending_classes=pending, logs=logs)

@app.route('/admin/upload_master', methods=['POST'])
@admin_required
def upload_master():
    file = request.files.get('file')
    if not file: return redirect(url_for('admin'))
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file, skiprows=2)
        else:
            df = pd.read_excel(file, skiprows=2)
        
        df.columns = [str(c).strip() for c in df.columns]
        c_col = next((c for c in df.columns if 'الفصل' in c or 'الحصة' in c), df.columns[0])
        
        import_count = 0
        # Process all rows in the file
        for _, row in df.iterrows():
            class_info = str(row[c_col]).strip()
            if not class_info or class_info.lower() == 'nan': continue
            
            if ' - ' in class_info:
                parts = class_info.split(' - ')
                grade_name = parts[0].strip()
                class_name = parts[1].strip()
            else:
                grade_name = "Default Grade"
                class_name = class_info

            cls = get_or_create_class(grade_name, class_name)
            
            for col in df.columns:
                if col == c_col: continue
                target_day = next((en for en, ar in DAYS_AR.items() if ar in col), None)
                p_match = re.search(r'(\d+)', col)
                
                if target_day and p_match:
                    p = int(p_match.group(1))
                    if 1 <= p <= 8:
                        sub = str(row[col]).strip()
                        if sub and sub.lower() != 'nan':
                            db.session.query(Subject).filter_by(class_id=cls.id, day=target_day, period=p).delete()
                            db.session.add(Subject(class_id=cls.id, day=target_day, period=p, name=sub))
                            db.session.query(WeeklyData).filter_by(class_id=cls.id, day=target_day, period=p).update({"subject_name": sub})
                            import_count += 1
        db.session.commit()
        flash(f'تم استيراد {import_count} حصة بنجاح من الملف بالكامل')
    except Exception as e:
        db.session.rollback()
        flash(f"خطأ: {e}")
    return redirect(url_for('admin'))

@app.route('/teacher', methods=['GET', 'POST'])
def teacher():
    settings = {s.key: s.value for s in Setting.query.all()}
    g_id = request.args.get('grade_id')
    c_id = request.args.get('class_id')
    week = request.args.get('week', settings.get('current_week', '1'))
    
    if request.method == 'POST':
        data = request.json
        if c_id and week:
            try:
                for e in data.get('entries', []):
                    day = e.get('day')
                    period = int(e.get('period'))
                    topic = e.get('topic', '')
                    homework = e.get('homework', '')
                    w = WeeklyData.query.filter_by(class_id=int(c_id), week_number=int(week), day=day, period=period).first()
                    if not w:
                        master_sub = Subject.query.filter_by(class_id=int(c_id), day=day, period=period).first()
                        sub_name = master_sub.name if master_sub else ''
                        w = WeeklyData(class_id=int(c_id), week_number=int(week), day=day, period=period, subject_name=sub_name)
                        db.session.add(w)
                    w.topic = topic
                    w.homework = homework
                db.session.commit()
                return jsonify({'status': 'success'})
            except Exception as e:
                db.session.rollback()
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

@app.route('/student/<int:g_id>/<int:c_id>')
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
    classes = Class.query.options(joinedload(Class.grade)).all()
    report = []
    for c in classes:
        missing = WeeklyData.query.filter(WeeklyData.class_id==c.id, WeeklyData.week_number==int(week), (WeeklyData.topic=='') | (WeeklyData.topic==None) | (WeeklyData.homework=='') | (WeeklyData.homework==None)).all()
        report.append({'class': c, 'missing': len(missing)})
    return render_template('audit_report.html', report=report, week=week)

@app.route('/admin/delete_date/<key>', methods=['POST'])
@admin_required
def delete_date(key):
    s = db.session.get(Setting, key)
    if s: s.value = ''; db.session.commit()
    return redirect(url_for('admin'))

with app.app_context():
    db.create_all()
    if not Setting.query.get('admin_password'):
        db.session.add(Setting(key='admin_password', value='fast490'))
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
