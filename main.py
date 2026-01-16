from flask import Flask, render_template, request, redirect, url_for, g, session, flash, jsonify, send_from_directory
import sqlite3
import os
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-999')
DATABASE = 'school.db'
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

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grade_id INTEGER,
                name TEXT,
                FOREIGN KEY (grade_id) REFERENCES grades(id),
                UNIQUE(grade_id, name)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER,
                day TEXT,
                period INTEGER,
                subject_name TEXT,
                FOREIGN KEY (class_id) REFERENCES classes(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                week_number INTEGER,
                topic TEXT,
                homework TEXT,
                override_subject TEXT,
                FOREIGN KEY (subject_id) REFERENCES subjects(id)
            )
        ''')
        
        # Ensure default values
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('current_week', '1')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('admin_password', 'admin123')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('exam_date_1', '')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('exam_date_2', '')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('exam_date_final', '')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('school_logo', '')")
        db.commit()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # TEMPORARY BYPASS: Access granted to everyone for now
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        entered_password = request.form.get('password')
        db = get_db()
        row = db.execute("SELECT value FROM config WHERE key = 'admin_password'").fetchone()
        stored_password = row['value'] if row else 'admin123'
        
        if entered_password == stored_password:
            session.clear()
            session['user_role'] = 'admin'
            return redirect(url_for('admin'))
        else:
            flash('كلمة المرور غير صحيحة')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def get_common_data():
    db = get_db()
    config_rows = db.execute("SELECT key, value FROM config").fetchall()
    config = {row['key']: row['value'] for row in config_rows}
    return config

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    config = get_common_data()
    
    # Selection logic
    grade_id = request.args.get('grade_id', type=int)
    class_id = request.args.get('class_id', type=int)
    week = request.args.get('week', config.get('current_week', 1), type=int)

    if request.method == 'POST':
        data = request.json
        if data and 'entries' in data:
            for entry in data['entries']:
                sid = entry.get('subject_id')
                w = entry.get('week')
                topic = entry.get('topic')
                hw = entry.get('homework')
                ovr = entry.get('override_subject')
                
                existing = db.execute("SELECT id FROM tasks WHERE subject_id = ? AND week_number = ?", 
                                    (sid, w)).fetchone()
                if existing:
                    db.execute("UPDATE tasks SET topic=?, homework=?, override_subject=? WHERE id=?", (topic, hw, ovr, existing['id']))
                else:
                    db.execute("INSERT INTO tasks (subject_id, week_number, topic, homework, override_subject) VALUES (?, ?, ?, ?, ?)",
                              (sid, w, topic, hw, ovr))
            db.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 400

    grades = db.execute("SELECT * FROM grades").fetchall()
    classes = db.execute("SELECT * FROM classes WHERE grade_id = ?", (grade_id,)).fetchall() if grade_id else []
    
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    if class_id:
        subjects_rows = db.execute("SELECT * FROM subjects WHERE class_id = ?", (class_id,)).fetchall()
        tasks_rows = db.execute("SELECT * FROM tasks WHERE week_number = ?", (week,)).fetchall()
        tasks_map = {row['subject_id']: row for row in tasks_rows}
        
        for sub in subjects_rows:
            day = sub['day']
            period = sub['period']
            sub_id = sub['id']
            task = tasks_map.get(sub_id, {})
            
            if day in schedule_data and 1 <= period <= 8:
                schedule_data[day][period] = {
                    'subject_id': sub_id,
                    'subject': task.get('override_subject') or sub['subject_name'],
                    'original_subject': sub['subject_name'],
                    'topic': task.get('topic', ''),
                    'homework': task.get('homework', ''),
                    'is_overridden': bool(task.get('override_subject'))
                }

    return render_template('teacher.html', 
                         grades=grades, classes=classes,
                         selected_grade=grade_id, selected_class=class_id, selected_week=week,
                         schedule=schedule_data, days_order=DAYS_ORDER, days_ar=DAYS_AR, config=config)

@app.route('/student/<int:grade_id>/<int:class_id>')
def student_view(grade_id, class_id):
    db = get_db()
    config = get_common_data()
    current_week = int(config.get('current_week', 1))
    
    grade = db.execute("SELECT name FROM grades WHERE id = ?", (grade_id,)).fetchone()
    cls = db.execute("SELECT name FROM classes WHERE id = ?", (class_id,)).fetchone()
    
    if not grade or not cls:
        return "الصف أو الفصل غير موجود", 404

    subjects_rows = db.execute("SELECT * FROM subjects WHERE class_id = ?", (class_id,)).fetchall()
    tasks_rows = db.execute("SELECT * FROM tasks WHERE week_number = ?", (current_week,)).fetchall()
    tasks_map = {row['subject_id']: row for row in tasks_rows}
    
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    for sub in subjects_rows:
        day = sub['day']
        period = sub['period']
        sub_id = sub['id']
        task = tasks_map.get(sub_id, {})
        
        if day in schedule_data and 1 <= period <= 8:
            schedule_data[day][period] = {
                'subject': task.get('override_subject') or sub['subject_name'],
                'topic': task.get('topic', ''),
                'homework': task.get('homework', '')
            }
            
    today = datetime.now()
    days_map_full = {'Sunday':'الأحد','Monday':'الاثنين','Tuesday':'الثلاثاء','Wednesday':'الأربعاء','Thursday':'الخميس'}
    day_str_ar = days_map_full.get(today.strftime("%A"), "")
    
    return render_template('student.html', 
                         grade_name=grade['name'], class_name=cls['name'],
                         week=current_week, schedule=schedule_data, 
                         days_order=DAYS_ORDER, days_ar=DAYS_AR,
                         date=today.strftime("%Y-%m-%d"), day=day_str_ar, config=config)

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    db = get_db()
    if request.method == 'POST':
        if 'add_grade' in request.form:
            db.execute("INSERT OR IGNORE INTO grades (name) VALUES (?)", (request.form.get('grade_name'),))
        elif 'add_class' in request.form:
            db.execute("INSERT OR IGNORE INTO classes (grade_id, name) VALUES (?, ?)", 
                      (request.form.get('grade_id'), request.form.get('class_name')))
        elif 'copy_class' in request.form:
            from_id = request.form.get('from_class_id')
            to_id = request.form.get('to_class_id')
            if from_id and to_id and from_id != to_id:
                # Clear target first
                db.execute("DELETE FROM subjects WHERE class_id = ?", (to_id,))
                # Copy subjects
                db.execute('''INSERT INTO subjects (class_id, day, period, subject_name)
                              SELECT ?, day, period, subject_name FROM subjects WHERE class_id = ?''', (to_id, from_id))
        elif 'update_week' in request.form:
            db.execute("UPDATE config SET value = ? WHERE key = 'current_week'", (request.form.get('current_week'),))
        elif 'update_exams' in request.form:
            for k in ['exam_date_1', 'exam_date_2', 'exam_date_final']:
                db.execute("UPDATE config SET value = ? WHERE key = ?", (request.form.get(k), k))
        elif 'clear_exam' in request.form:
            db.execute("UPDATE config SET value = '' WHERE key = ?", (request.form.get('exam_key'),))
        elif 'upload_logo' in request.form:
            file = request.files.get('logo')
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                db.execute("UPDATE config SET value = ? WHERE key = 'school_logo'", (filename,))
        elif 'add_subject' in request.form:
            cid, day, p, name = request.form.get('class_id'), request.form.get('day'), request.form.get('period'), request.form.get('subject_name')
            existing = db.execute("SELECT id FROM subjects WHERE class_id=? AND day=? AND period=?", (cid, day, p)).fetchone()
            if existing: db.execute("UPDATE subjects SET subject_name=? WHERE id=?", (name, existing['id']))
            else: db.execute("INSERT INTO subjects (class_id, day, period, subject_name) VALUES (?, ?, ?, ?)", (cid, day, p, name))
        elif 'delete_subject' in request.form:
            sid = request.form.get('subject_id')
            db.execute("DELETE FROM subjects WHERE id=?", (sid,))
            db.execute("DELETE FROM tasks WHERE subject_id=?", (sid,))
        
        db.commit()
        return redirect(url_for('admin', grade_id=request.form.get('grade_id'), class_id=request.form.get('class_id')))

    config = get_common_data()
    grades = db.execute("SELECT * FROM grades").fetchall()
    selected_grade = request.args.get('grade_id', type=int)
    classes = db.execute("SELECT * FROM classes WHERE grade_id = ?", (selected_grade,)).fetchall() if selected_grade else []
    selected_class = request.args.get('class_id', type=int)
    subjects = db.execute("SELECT * FROM subjects WHERE class_id = ?", (selected_class,)).fetchall() if selected_class else []
    all_classes = db.execute("SELECT c.*, g.name as gname FROM classes c JOIN grades g ON c.grade_id = g.id").fetchall()
    
    return render_template('admin.html', config=config, grades=grades, classes=classes, all_classes=all_classes,
                         selected_grade=selected_grade, selected_class=selected_class,
                         entries=subjects, days_ar=DAYS_AR, days_order=DAYS_ORDER)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
