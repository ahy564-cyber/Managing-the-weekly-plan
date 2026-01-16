from flask import Flask, render_template, request, redirect, url_for, g, session, flash, jsonify
import sqlite3
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'dev-secret-key')
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_number INTEGER,
                day TEXT,
                period INTEGER,
                subject TEXT,
                topic TEXT,
                homework TEXT
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('current_week', '1')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('admin_password', 'admin123')")
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('teacher_password', 'teacher123')")
        db.commit()

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session:
                return redirect(url_for('login'))
            if role and session['user_role'] != role:
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        db = get_db()
        admin_pass = db.execute("SELECT value FROM config WHERE key = 'admin_password'").fetchone()['value']
        teacher_pass = db.execute("SELECT value FROM config WHERE key = 'teacher_password'").fetchone()['value']
        
        if password == admin_pass:
            session['user_role'] = 'admin'
            return redirect(url_for('admin'))
        elif password == teacher_pass:
            session['user_role'] = 'teacher'
            return redirect(url_for('teacher_portal'))
        else:
            flash('كلمة المرور غير صحيحة')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_role', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    db = get_db()
    current_week = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()['value']
    return render_template('index.html', current_week=current_week)

@app.route('/student')
def student():
    db = get_db()
    current_week_row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = int(current_week_row['value']) if current_week_row else 1
    
    rows = db.execute("SELECT * FROM schedule WHERE week_number = ?", (current_week,)).fetchall()
    
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    for row in rows:
        if row['day'] in schedule_data and 1 <= row['period'] <= 8:
            schedule_data[row['day']][row['period']] = {
                'subject': row['subject'],
                'topic': row['topic'],
                'homework': row['homework']
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
@login_required(role='admin')
def admin():
    db = get_db()
    if request.method == 'POST':
        if 'update_week' in request.form:
            new_week = request.form.get('current_week')
            db.execute("UPDATE config SET value = ? WHERE key = 'current_week'", (new_week,))
            db.commit()
        elif 'add_entry' in request.form:
            week = request.form.get('week')
            day = request.form.get('day')
            period = request.form.get('period')
            subject = request.form.get('subject')
            
            existing = db.execute("SELECT id FROM schedule WHERE week_number = ? AND day = ? AND period = ?", 
                                (week, day, period)).fetchone()
            if existing:
                db.execute("UPDATE schedule SET subject=? WHERE id=?", (subject, existing['id']))
            else:
                db.execute("INSERT INTO schedule (week_number, day, period, subject) VALUES (?, ?, ?, ?)",
                          (week, day, period, subject))
            db.commit()
        elif 'delete_entry' in request.form:
            entry_id = request.form.get('entry_id')
            db.execute("DELETE FROM schedule WHERE id = ?", (entry_id,))
            db.commit()
            
        return redirect(url_for('admin'))

    current_week = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()['value']
    entries = db.execute("SELECT * FROM schedule WHERE week_number = ? ORDER BY day, period", (current_week,)).fetchall()
    return render_template('admin.html', current_week=current_week, days_ar=DAYS_AR, days_order=DAYS_ORDER, entries=entries)

@app.route('/teacher', methods=['GET', 'POST'])
@login_required(role='teacher')
def teacher_portal():
    db = get_db()
    config_week = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()['value']
    selected_week = request.args.get('week', config_week)
    
    if request.method == 'POST':
        # Bulk save logic
        data = request.json
        if data and 'entries' in data:
            for entry in data['entries']:
                db.execute("UPDATE schedule SET topic=?, homework=? WHERE id=?", 
                          (entry.get('topic'), entry.get('homework'), entry.get('id')))
            db.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 400

    rows = db.execute("SELECT * FROM schedule WHERE week_number = ?", (selected_week,)).fetchall()
    
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    for row in rows:
        if row['day'] in schedule_data and 1 <= row['period'] <= 8:
            schedule_data[row['day']][row['period']] = {
                'id': row['id'],
                'subject': row['subject'],
                'topic': row['topic'],
                'homework': row['homework']
            }
            
    return render_template('teacher.html', 
                         selected_week=int(selected_week), 
                         schedule=schedule_data, 
                         days_order=DAYS_ORDER,
                         days_ar=DAYS_AR)

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
