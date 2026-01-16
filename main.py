from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DATABASE = 'school.db'

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
        # Configuration table (e.g., current week)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Schedule table
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
        # Default current week if not set
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
    current_week = int(db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()['value'])
    rows = db.execute("SELECT * FROM schedule WHERE week_number = ?", (current_week,)).fetchall()
    
    # Organize data for the template: schedule[day][period]
    schedule_data = {day: {p: {} for p in range(1, 9)} for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']}
    for row in rows:
        if row['day'] in schedule_data and 1 <= row['period'] <= 8:
            schedule_data[row['day']][row['period']] = {
                'subject': row['subject'],
                'topic': row['topic'],
                'homework': row['homework']
            }
            
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_str = today.strftime("%A")
    
    return render_template('student.html', 
                         week=current_week, 
                         schedule=schedule_data, 
                         date=date_str, 
                         day=day_str)

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
            
            # Check if entry exists to update or insert
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

    current_week = db.execute("SELECT value FROM config WHERE key = 'current_week'").fetchone()['value']
    return render_template('admin.html', current_week=current_week)

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
