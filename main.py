from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-fast490')

# PostgreSQL Configuration
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Only add sslmode if not local replit dev DB
engine_options = {"pool_pre_ping": True}
# Neon requires sslmode=require for connection stability in prod
# Local helium DB does NOT support SSL
if db_url and "127.0.0.1" not in db_url and "localhost" not in db_url and "helium" not in db_url:
    if "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url += f"{separator}sslmode=require"
    engine_options["connect_args"] = {"sslmode": "require"}
else:
    # Disable SSL for local dev DB
    if db_url and "sslmode" not in db_url:
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
    classes = db.relationship('Class', backref='grade_obj', cascade="all, delete-orphan", lazy=True)

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
        stored = Setting.query.get('admin_password')
        if password == (stored.value if stored else 'fast490'):
            session.clear()
            session['user_role'] = 'admin'
            return redirect(url_for('admin'))
        flash('كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('teacher'))

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_grade':
            name = request.form.get('name')
            if name:
                db.session.add(Grade(name=name))
                flash('تم إضافة الصف بنجاح')
        elif action == 'delete_grade':
            gid = request.form.get('grade_id')
            grade = Grade.query.get(gid)
            if grade:
                db.session.delete(grade)
                flash('تم حذف الصف بنجاح')
        elif action == 'add_class':
            name = request.form.get('name')
            gid = request.form.get('grade_id')
            if name and gid:
                db.session.add(Class(name=name, grade_id=int(gid)))
                flash('تم إضافة الفصل بنجاح')
        elif action == 'delete_class':
            cid = request.form.get('class_id')
            cls = Class.query.get(cid)
            if cls:
                db.session.delete(cls)
                flash('تم حذف الفصل بنجاح')
        elif action == 'add_subject':
            cid = request.form.get('class_id')
            day = request.form.get('day')
            period = request.form.get('period')
            name = request.form.get('name')
            if cid and day and period and name:
                db.session.add(Subject(class_id=int(cid), day=day, period=int(period), name=name))
                flash('تم حفظ المادة بنجاح')
        elif action == 'delete_subject':
            sid = request.form.get('subject_id')
            sub = Subject.query.get(sid)
            if sub:
                db.session.delete(sub)
                flash('تم حذف المادة بنجاح')
        elif action == 'update_settings':
            for key in ['period1_date', 'period2_date', 'final_date', 'current_week', 'school_name']:
                val = request.form.get(key)
                if val is not None:
                    s = Setting.query.get(key)
                    if s: s.value = val
                    else: db.session.add(Setting(key=key, value=val))
            db.session.commit()
            flash('تم تحديث الإعدادات بنجاح')
        elif action == 'upload_logo':
            file = request.files.get('logo')
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                s = Setting.query.get('school_logo')
                if s: s.value = filename
                else: db.session.add(Setting(key='school_logo', value=filename))
                db.session.commit()
                flash('تم رفع الشعار بنجاح')
        elif action == 'save_override':
            cid = request.form.get('class_id')
            week = request.form.get('week')
            day = request.form.get('day')
            period = request.form.get('period')
            subject_name = request.form.get('subject_name')
            if cid and week and day and period:
                exists = WeeklyData.query.filter_by(class_id=int(cid), week_number=int(week), day=day, period=int(period)).first()
                if exists:
                    exists.subject_name = subject_name
                else:
                    db.session.add(WeeklyData(class_id=int(cid), week_number=int(week), day=day, period=int(period), subject_name=subject_name))
                flash('تم حفظ التعديل الأسبوعي بنجاح')
        
        db.session.commit()
        return redirect(url_for('admin'))

    grades = Grade.query.order_by(Grade.name).all()
    # Explicitly query grade names to avoid template issues
    classes_raw = db.session.query(Class, Grade.name).join(Grade, Class.grade_id == Grade.id).order_by(Grade.name, Class.name).all()
    classes = []
    for c, g_name in classes_raw:
        c.grade_name = g_name
        classes.append(c)
        
    all_settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
    
    subjects_raw = db.session.query(Subject, Class.name, Grade.name).join(Class, Subject.class_id == Class.id).join(Grade, Class.grade_id == Grade.id).all()
    subjects = []
    for s, c_name, g_name in subjects_raw:
        s.class_name = f"{g_name} - {c_name}"
        subjects.append(s)
    
    sel_class_id = request.args.get('class_id')
    sel_week = request.args.get('week', settings_dict.get('current_week', '1'))
    
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    # Fix DataError by ensuring class_id is a valid integer string
    if sel_class_id and sel_class_id.isdigit():
        fixed = Subject.query.filter_by(class_id=int(sel_class_id)).all()
        for f in fixed: schedule[f.day][f.period]['subject_name'] = f.name
        
        weekly = WeeklyData.query.filter_by(class_id=int(sel_class_id), week_number=int(sel_week)).all()
        for w in weekly:
            day_data = schedule[w.day][w.period]
            day_data.update({'topic': w.topic, 'homework': w.homework})
            if w.subject_name:
                day_data['subject_name'] = w.subject_name
    
    return render_template('admin.html', grades=grades, classes=classes, settings=settings_dict, subjects=subjects, 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, schedule=schedule, 
                         selected_class_id=sel_class_id, selected_week=sel_week)

@app.route('/admin/delete_date/<date_type>', methods=['POST'])
@admin_required
def delete_date(date_type):
    if date_type in ['period1_date', 'period2_date', 'final_date']:
        s = Setting.query.get(date_type)
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
    
    if request.method == 'POST':
        data = request.json
        if class_id and class_id.isdigit():
            for entry in data.get('entries', []):
                exists = WeeklyData.query.filter_by(class_id=int(class_id), week_number=int(week), day=entry['day'], period=int(entry['period'])).first()
                if exists:
                    exists.topic = entry['topic']
                    exists.homework = entry['homework']
                else:
                    db.session.add(WeeklyData(class_id=int(class_id), week_number=int(week), day=entry['day'], 
                                            period=int(entry['period']), topic=entry['topic'], homework=entry['homework']))
            db.session.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Invalid class_id'}), 400

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
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings_dict)

@app.route('/student/<int:grade_id>/<int:class_id>')
def student(grade_id, class_id):
    all_settings = Setting.query.all()
    settings_dict = {s.key: s.value for s in all_settings}
    week = settings_dict.get('current_week', '1')
    
    grade = Grade.query.get(grade_id)
    cls = Class.query.get(class_id)
    
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
            db.create_all()
            print("Successfully connected to PostgreSQL and initialized schema.")
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True)
