from flask import Flask, render_template
import sqlite3
import os

app = Flask(__name__)
DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return "<h1>Welcome to the School System</h1><p>Go to <a href='/student'>Student</a>, <a href='/teacher'>Teacher</a>, or <a href='/admin'>Admin</a> pages.</p>"

@app.route('/student')
def student():
    return render_template('student.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/teacher')
def teacher():
    return render_template('teacher.html')

if __name__ == '__main__':
    # Initialize DB (create file if not exists)
    if not os.path.exists(DATABASE):
        conn = get_db_connection()
        conn.close()
    app.run(host='0.0.0.0', port=5000)
