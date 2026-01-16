from flask import Flask, render_template, request, redirect, url_for, g, session, flash, jsonify
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

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = dict_factory
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
        
        cursor.execute('CREATE TABLE IF NOT EXISTS grades (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)')
        cursor.execute('CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, grade_id INTEGER, FOREIGN KEY(grade_id) REFERENCES grades(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER, day TEXT, period INTEGER, name TEXT, FOREIGN KEY(class_id) REFERENCES classes(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS weekly_data (id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER, week_number INTEGER, day TEXT, period INTEGER, topic TEXT, homework TEXT, subject_name TEXT, FOREIGN KEY(class_id) REFERENCES classes(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password', 'admin123')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('school_logo', '')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('period1_date', '')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('period2_date', '')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('final_date', '')")
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('current_week', '1')")
        db.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        db = get_db()
        stored = db.execute("SELECT value FROM settings WHERE key = 'admin_password'").fetchone()
        if password == (stored['value'] if stored else 'admin123'):
            session['user_role'] = 'admin'
            return redirect(url_for('admin'))
        flash('كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_grade':
            db.execute("INSERT INTO grades (name) VALUES (?)", (request.form.get('name'),))
        elif action == 'add_class':
            db.execute("INSERT INTO classes (name, grade_id) VALUES (?, ?)", (request.form.get('name'), request.form.get('grade_id')))
        elif action == 'add_subject':
            db.execute("INSERT INTO subjects (class_id, day, period, name) VALUES (?, ?, ?, ?)", 
                      (request.form.get('class_id'), request.form.get('day'), request.form.get('period'), request.form.get('name')))
        elif action == 'update_settings':
            for key in ['period1_date', 'period2_date', 'final_date', 'current_week']:
                db.execute("UPDATE settings SET value = ? WHERE key = ?", (request.form.get(key), key))
        elif action == 'upload_logo':
            file = request.files.get('logo')
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                db.execute("UPDATE settings SET value = ? WHERE key = 'school_logo'", (filename,))
        db.commit()
        return redirect(url_for('admin'))

    grades = db.execute("SELECT * FROM grades").fetchall()
    classes = db.execute("SELECT classes.*, grades.name as grade_name FROM classes JOIN grades ON classes.grade_id = grades.id").fetchall()
    settings = {row['key']: row['value'] for row in db.execute("SELECT * FROM settings").fetchall()}
    subjects = db.execute("SELECT subjects.*, classes.name as class_name FROM subjects JOIN classes ON subjects.class_id = classes.id").fetchall()
    
    return render_template('admin.html', grades=grades, classes=classes, settings=settings, subjects=subjects, days_ar=DAYS_AR, days_order=DAYS_ORDER)

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    grade_id = request.args.get('grade_id')
    class_id = request.args.get('class_id')
    week = request.args.get('week')
    
    settings = {row['key']: row['value'] for row in db.execute("SELECT * FROM settings").fetchall()}
    if not week: week = settings.get('current_week', '1')
    
    if request.method == 'POST':
        data = request.json
        for entry in data.get('entries', []):
            db.execute("""INSERT INTO weekly_data (class_id, week_number, day, period, topic, homework, subject_name) 
                          VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                       (class_id, week, entry['day'], entry['period'], entry['topic'], entry['homework'], entry['subject_name']))
        db.commit()
        return jsonify({'status': 'success'})

    grades = db.execute("SELECT * FROM grades").fetchall()
    classes = db.execute("SELECT * FROM classes WHERE grade_id = ?", (grade_id,)).fetchall() if grade_id else []
    
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    if class_id:
        fixed = db.execute("SELECT * FROM subjects WHERE class_id = ?", (class_id,)).fetchall()
        for f in fixed: schedule[f['day']][f['period']]['subject_name'] = f['name']
        
        weekly = db.execute("SELECT * FROM weekly_data WHERE class_id = ? AND week_number = ?", (class_id, week)).fetchall()
        for w in weekly:
            schedule[w['day']][w['period']].update({'topic': w['topic'], 'homework': w['homework'], 'subject_name': w['subject_name']})

    return render_template('teacher.html', grades=grades, classes=classes, schedule=schedule, 
                         selected_grade=grade_id, selected_class=class_id, selected_week=week, 
                         days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings)

@app.route('/student/<int:grade_id>/<int:class_id>')
def student(grade_id, class_id):
    db = get_db()
    settings = {row['key']: row['value'] for row in db.execute("SELECT * FROM settings").fetchall()}
    week = settings.get('current_week', '1')
    
    schedule = {day: {p: {'subject_name': '', 'topic': '', 'homework': ''} for p in range(1, 9)} for day in DAYS_ORDER}
    fixed = db.execute("SELECT * FROM subjects WHERE class_id = ?", (class_id,)).fetchall()
    for f in fixed: schedule[f['day']][f['period']]['subject_name'] = f['name']
    
    weekly = db.execute("SELECT * FROM weekly_data WHERE class_id = ? AND week_number = ?", (class_id, week)).fetchall()
    for w in weekly:
        schedule[w['day']][w['period']].update({'topic': w['topic'], 'homework': w['homework'], 'subject_name': w['subject_name']})

    return render_template('student.html', schedule=schedule, days_ar=DAYS_AR, days_order=DAYS_ORDER, settings=settings, week=week)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
