from flask import Flask, render_template, request, redirect, url_for, g, session, flash, jsonify
import sqlite3
import os
import time
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-999')
DATABASE = 'school.db'

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
        
        # Reset and create tables
        cursor.execute('DROP TABLE IF EXISTS config')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        cursor.execute('DROP TABLE IF EXISTS subjects')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT,
                period INTEGER,
                subject_name TEXT
            )
        ''')
        
        cursor.execute('DROP TABLE IF EXISTS tasks')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                week_number INTEGER,
                topic TEXT,
                homework TEXT,
                FOREIGN KEY (subject_id) REFERENCES subjects(id)
            )
        ''')
        
        # Insert default values
        cursor.execute("INSERT INTO config (key, value) VALUES ('current_week', '1')")
        cursor.execute("INSERT INTO config (key, value) VALUES ('admin_password', 'admin123')")
        db.commit()
        print("Database Restructured: Subjects and Tasks tables created.")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Temporarily removed password protection as requested
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        db = get_db()
        row = db.execute("SELECT value FROM config WHERE key = 'admin_password'").fetchone()
        admin_pass = row['value'] if row else 'admin123'
        
        if password == admin_pass:
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

@app.route('/', methods=['GET', 'POST'])
def index():
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    config_week = row['value'] if row else '1'
    selected_week = int(request.args.get('week', config_week))
    
    if request.method == 'POST':
        data = request.json
        if data and 'entries' in data:
            for entry in data['entries']:
                subject_id = entry.get('subject_id')
                week = entry.get('week')
                topic = entry.get('topic')
                homework = entry.get('homework')
                
                # Check if task exists for this subject/week
                existing = db.execute("SELECT id FROM tasks WHERE subject_id = ? AND week_number = ?", 
                                    (subject_id, week)).fetchone()
                if existing:
                    db.execute("UPDATE tasks SET topic=?, homework=? WHERE id=?", (topic, homework, existing['id']))
                else:
                    db.execute("INSERT INTO tasks (subject_id, week_number, topic, homework) VALUES (?, ?, ?, ?)",
                              (subject_id, week, topic, homework))
            db.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 400

    # Get all subjects
    subjects_rows = db.execute("SELECT * FROM subjects").fetchall()
    
    # Get tasks for selected week
    tasks_rows = db.execute("SELECT * FROM tasks WHERE week_number = ?", (selected_week,)).fetchall()
    tasks_map = {row['subject_id']: row for row in tasks_rows}
    
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    for sub in subjects_rows:
        day = sub['day']
        period = sub['period']
        sub_id = sub['id']
        task = tasks_map.get(sub_id, {})
        
        if day in schedule_data and 1 <= period <= 8:
            schedule_data[day][period] = {
                'subject_id': sub_id,
                'subject': sub['subject_name'],
                'topic': task.get('topic', ''),
                'homework': task.get('homework', '')
            }
            
    return render_template('teacher.html', 
                         selected_week=selected_week, 
                         schedule=schedule_data, 
                         days_order=DAYS_ORDER,
                         days_ar=DAYS_AR)

@app.route('/student')
def student():
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = int(row['value']) if row else 1
    
    subjects_rows = db.execute("SELECT * FROM subjects").fetchall()
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
                'subject': sub['subject_name'],
                'topic': task.get('topic', ''),
                'homework': task.get('homework', '')
            }
            
    today = datetime.now()
    days_map_full = {
        'Sunday': 'الأحد', 'Monday': 'الاثنين', 'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء', 'Thursday': 'الخميس', 'Friday': 'الجمعة', 'Saturday': 'السبت'
    }
    day_str_en = today.strftime("%A")
    day_str_ar = days_map_full.get(day_str_en, day_str_en)
    date_str = today.strftime("%Y-%m-%d")
    
    return render_template('student.html', 
                         week=current_week, 
                         schedule=schedule_data, 
                         days_order=DAYS_ORDER,
                         days_ar=DAYS_AR,
                         date=date_str, 
                         day=day_str_ar)

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    db = get_db()
    if request.method == 'POST':
        if 'update_week' in request.form:
            new_week = request.form.get('current_week')
            db.execute("UPDATE config SET value = ? WHERE key = 'current_week'", (new_week,))
            db.commit()
        elif 'add_subject' in request.form:
            day = request.form.get('day')
            period = request.form.get('period')
            subject_name = request.form.get('subject_name')
            
            existing = db.execute("SELECT id FROM subjects WHERE day = ? AND period = ?", (day, period)).fetchone()
            if existing:
                db.execute("UPDATE subjects SET subject_name=? WHERE id=?", (subject_name, existing['id']))
            else:
                db.execute("INSERT INTO subjects (day, period, subject_name) VALUES (?, ?, ?)", (day, period, subject_name))
            db.commit()
        elif 'delete_subject' in request.form:
            sub_id = request.form.get('subject_id')
            db.execute("DELETE FROM subjects WHERE id = ?", (sub_id,))
            db.execute("DELETE FROM tasks WHERE subject_id = ?", (sub_id,))
            db.commit()
            
        return redirect(url_for('admin'))

    row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = row['value'] if row else '1'
    subjects = db.execute("SELECT * FROM subjects ORDER BY day, period").fetchall()
    return render_template('admin.html', current_week=current_week, days_ar=DAYS_AR, days_order=DAYS_ORDER, entries=subjects)

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
