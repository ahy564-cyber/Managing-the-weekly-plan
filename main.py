from flask import Flask, render_template, request, redirect, url_for, g, session, flash, jsonify
import sqlite3
import os
import time
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SESSION_SECRET', 'super-secret-key-999')
DATABASE = 'school.db'

# Simple bypass logic: Store start time of the session
BYPASS_START_TIME = time.time()
BYPASS_DURATION = 300 # 5 minutes

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
        
        # Reset database by dropping and recreating config table
        cursor.execute('DROP TABLE IF EXISTS config')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Ensure schedule table exists
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
        
        # Insert default values
        cursor.execute("INSERT INTO config (key, value) VALUES ('current_week', '1')")
        cursor.execute("INSERT INTO config (key, value) VALUES ('admin_password', 'admin123')")
        db.commit()
        print("Database Reset: Default values inserted.")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 5-minute bypass check
        current_time = time.time()
        is_bypassed = (current_time - BYPASS_START_TIME) < BYPASS_DURATION
        
        if session.get('user_role') != 'admin' and not is_bypassed:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        print(f"Login attempt with: '{password}'")
        
        db = get_db()
        row = db.execute("SELECT value FROM config WHERE key = 'admin_password'").fetchone()
        admin_pass = row['value'] if row else 'admin123'
        
        print(f"Actual admin password in DB: '{admin_pass}'")
        
        if password == admin_pass:
            session.clear() # Clear any old session data
            session['user_role'] = 'admin'
            print("Login Successful: User is admin.")
            return redirect(url_for('admin'))
        else:
            flash('كلمة المرور غير صحيحة')
            print("Login Failed: Incorrect password.")
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
    selected_week = request.args.get('week', config_week)
    
    if request.method == 'POST':
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

@app.route('/student')
def student():
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = int(row['value']) if row else 1
    
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
@admin_required
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

    row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = row['value'] if row else '1'
    entries = db.execute("SELECT * FROM schedule WHERE week_number = ? ORDER BY day, period", (current_week,)).fetchall()
    return render_template('admin.html', current_week=current_week, days_ar=DAYS_AR, days_order=DAYS_ORDER, entries=entries)

if __name__ == '__main__':
    # Initialize DB every time for debug session
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
