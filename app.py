import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'yellownet_super_secret_key'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            friend_username TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            filename TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Неверный логин или пароль")

    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email = request.form.get('email')
    phone = request.form.get('phone')
    password = request.form.get('password')

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, phone, password) VALUES (?, ?, ?, ?)",
                       (username, email, phone, password))
        conn.commit()
        conn.close()
        session['user'] = username
        return redirect(url_for('dashboard'))
    except sqlite3.IntegrityError:
        return render_template('login.html', error="Пользователь с таким логином уже существует")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    username = session['user']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id, email, phone FROM users WHERE username = ?", (username,))
    user_info = cursor.fetchone()
    
    if not user_info:
        session.pop('user', None)
        conn.close()
        return redirect(url_for('login'))

    user_id = user_info[0]

    cursor.execute("SELECT friend_username FROM friends WHERE user_id = ?", (user_id,))
    friends = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT filename, sender, timestamp FROM videos WHERE receiver = ? ORDER BY id DESC", (username,))
    inbox_videos = cursor.fetchall()

    cursor.execute("SELECT message, timestamp FROM notifications WHERE user = ? ORDER BY id DESC", (username,))
    notifications = cursor.fetchall()

    conn.close()

    return render_template('dashboard.html', 
                           user=username, 
                           user_info=user_info, 
                           friends=friends, 
                           videos=inbox_videos, 
                           notifications=notifications)

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'user' not in session:
        return redirect(url_for('login'))

    friend_name = request.form.get('friend_name').strip()
    username = session['user']

    if friend_name == username:
        flash("Нельзя добавить самого себя!")
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (friend_name,))
    target_user = cursor.fetchone()

    if target_user:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        my_id = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM friends WHERE user_id = ? AND friend_username = ?", (my_id, friend_name))
        exists = cursor.fetchone()

        if not exists:
            cursor.execute("INSERT INTO friends (user_id, friend_username) VALUES (?, ?)", (my_id, friend_name))
            cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", 
                           (friend_name, f"Пользователь @{username} добавил вас в друзья!"))
            conn.commit()
            flash(f"Пользователь @{friend_name} успешно добавлен!")
        else:
            flash("Этот пользователь уже в вашем списке друзей.")
    else:
        flash("Пользователь с таким никнеймом не найден.")

    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'user' not in session:
        return redirect(url_for('login'))

    receiver = request.form.get('receiver')
    file = request.files.get('video_file')
    sender = session['user']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_filename = f"{sender}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_filename))

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO videos (sender, receiver, filename) VALUES (?, ?, ?)", 
                       (sender, receiver, save_filename))
        cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", 
                       (receiver, f"Вам пришло новое видео от @{sender}!"))
        conn.commit()
        conn.close()

        flash("Видео успешно отправлено!")
    else:
        flash("Ошибка загрузки. Поддерживаются форматы: mp4, avi, mov, webm.")

    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
