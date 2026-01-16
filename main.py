from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DATABASE = 'school.db'

# Mapping of English days to Arabic for backend/frontend consistency
DAYS_AR = {
    'Sunday': 'الأحد',
    'Monday': 'الاثنين',
    'Tuesday': 'الثلاثاء',
    'Wednesday': 'الأربعاء',
    'Thursday': 'الخميس'
}

# The user requested Sunday to Thursday (الأحد to الخميس)
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
        db.commit()

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
    
    # Organize data: schedule[day_eng][period]
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in DAYS_ORDER}
    for row in rows:
        if row['day'] in schedule_data and 1 <= row['period'] <= 8:
            schedule_data[row['day']][row['period']] = {
                'subject': row['subject'],
                'topic': row['topic'],
                'homework': row['homework']
            }
            
    today = datetime.now()
    # Basic Arabic translation for the current day display
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
            topic = request.form.get('topic')
            homework = request.form.get('homework')
            
            existing = db.execute("SELECT id FROM schedule WHERE week_number = ? AND day = ? AND period = ?", 
                                (week, day, period)).fetchone()
            if existing:
                db.execute('''UPDATE schedule SET subject=?, topic=?, homework=? 
                             WHERE week_number=? AND day=? AND period=?''',
                          (subject, topic, homework, week, day, period))
            else:
                db.execute('''INSERT INTO schedule (week_number, day, period, subject, topic, homework)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (week, day, period, subject, topic, homework))
            db.commit()
        return redirect(url_for('admin'))

    current_week_row = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()
    current_week = current_week_row['value'] if current_week_row else '1'
    return render_template('admin.html', current_week=current_week, days_ar=DAYS_AR, days_order=DAYS_ORDER)

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
