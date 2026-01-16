import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps

app = Flask(__name__)
app.secret_key = "school_secret_key_2026" # مفتاح الأمان

# كلمات المرور (يمكنك تغييرها من هنا)
ADMIN_PASSWORD = "admin"
TEACHER_PASSWORD = "teacher"

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('school_system.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, current_week INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, day TEXT, period INTEGER, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, week INTEGER, subject_id INTEGER, topic TEXT, homework TEXT, UNIQUE(week, subject_id))')
    c.execute('SELECT count(*) FROM settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO settings (current_week) VALUES (1)')
    conn.commit()
    conn.close()

init_db()

# --- حماية الصفحات ---
def login_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

# --- المسارات (Routes) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['role'] = 'admin'
            return redirect(url_for('admin_view'))
        elif password == TEACHER_PASSWORD:
            session['role'] = 'teacher'
            return redirect(url_for('teacher_view'))
        else:
            flash('كلمة المرور غير صحيحة!')
    return '''
        <div dir="rtl" style="text-align:center; padding:50px; font-family:Arial;">
            <h2>تسجيل الدخول للنظام</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="أدخل كلمة المرور" required style="padding:10px;">
                <button type="submit" style="padding:10px 20px;">دخول</button>
            </form>
        </div>
    '''

@app.route('/')
def student_view():
    conn = sqlite3.connect('school_system.db')
    c = conn.cursor()
    c.execute('SELECT current_week FROM settings')
    current_week = c.fetchone()[0]
    query = '''
        SELECT s.day, s.period, s.name, t.topic, t.homework 
        FROM subjects s 
        LEFT JOIN tasks t ON s.id = t.subject_id AND t.week = ?
        ORDER BY CASE s.day 
            WHEN 'الأحد' THEN 1 WHEN 'الاثنين' THEN 2 WHEN 'الثلاثاء' THEN 3 
            WHEN 'الأربعاء' THEN 4 WHEN 'الخميس' THEN 5 END, s.period
    '''
    c.execute(query, (current_week,))
    raw_data = c.fetchall()
    schedule = {}
    for row in raw_data:
        day, period, name, topic, homework = row
        if day not in schedule: schedule[day] = {}
        schedule[day][period] = {'name': name, 'topic': topic, 'homework': homework}
    conn.close()
    return render_template('student.html', schedule=schedule, week=current_week)

@app.route('/admin', methods=['GET', '