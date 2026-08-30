import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'yellownet_super_secret_pro_key'
app.permanent_session_lifetime = timedelta(days=31)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
AVATAR_FOLDER = os.path.join('static', 'avatars')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['AVATAR_FOLDER'] = AVATAR_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AVATAR_FOLDER, exist_ok=True)

@app.before_request
def make_session_permanent():
    session.permanent = True

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Обновленная таблица пользователей (добавлено bio и avatar)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, 
                        email TEXT NOT NULL, phone TEXT NOT NULL, password TEXT NOT NULL,
                        bio TEXT DEFAULT 'Привет! Я в YellowNet.', avatar TEXT DEFAULT 'default.png')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS friends (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, friend_username TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(id))''')
    # В видео добавлены лайки
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, 
                        filename TEXT, likes INTEGER DEFAULT 0, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, message TEXT, 
                        is_read INTEGER DEFAULT 0, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    if 'user' in session: return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user:
            if user[4] == password:
                session['user'] = username
                conn.close()
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                return render_template('login.html', error="Неверный пароль!")
        else:
            cursor.execute("INSERT INTO users (username, email, phone, password) VALUES (?, ?, ?, ?)",
                           (username, "auto@yellownet.com", "000", password))
            conn.commit()
            conn.close()
            session['user'] = username
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username').strip()
    email = request.form.get('email').strip()
    phone = request.form.get('phone').strip()
    password = request.form.get('password').strip()
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
        return render_template('login.html', error="Логин уже занят")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login'))
    username = session['user']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, bio, avatar FROM users WHERE username = ?", (username,))
    user_info = cursor.fetchone()
    if not user_info:
        session.pop('user', None)
        return redirect(url_for('login'))
        
    user_id, bio, avatar = user_info
    
    cursor.execute("SELECT friend_username FROM friends WHERE user_id = ?", (user_id,))
    friends = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT id, filename, sender, likes, timestamp FROM videos WHERE receiver = ? ORDER BY id DESC", (username,))
    videos = cursor.fetchall()

    cursor.execute("SELECT message, timestamp FROM notifications WHERE user = ? ORDER BY id DESC LIMIT 10", (username,))
    notifications = cursor.fetchall()
    
    stats = {"friends": len(friends), "videos": len(videos)}
    conn.close()
    
    return render_template('dashboard.html', user=username, bio=bio, avatar=avatar, 
                           friends=friends, videos=videos, notifications=notifications, stats=stats)

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'user' not in session: return redirect(url_for('login'))
    friend_name = request.form.get('friend_name').strip()
    username = session['user']
    if friend_name == username: 
        flash("Нельзя добавить себя!", "error")
        return redirect(url_for('dashboard'))

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (friend_name,))
    
    if cursor.fetchone():
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        my_id = cursor.fetchone()[0]
        cursor.execute("SELECT * FROM friends WHERE user_id = ? AND friend_username = ?", (my_id, friend_name))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO friends (user_id, friend_username) VALUES (?, ?)", (my_id, friend_name))
            cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", 
                           (friend_name, f"🚀 @{username} теперь ваш друг!"))
            conn.commit()
            flash(f"@{friend_name} добавлен в друзья!", "success")
        else:
            flash("Пользователь уже в друзьях", "info")
    else:
        flash("Пользователь не найден", "error")
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'user' not in session: return redirect(url_for('login'))
    receiver = request.form.get('receiver')
    file = request.files.get('video_file')
    sender = session['user']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_filename = f"{sender}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_filename))

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO videos (sender, receiver, filename) VALUES (?, ?, ?)", (sender, receiver, save_filename))
        cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", (receiver, f"🎬 Новое видео от @{sender}!"))
        conn.commit()
        conn.close()
        flash("Видео успешно отправлено!", "success")
    else:
        flash("Ошибка формата файла", "error")
    return redirect(url_for('dashboard'))

@app.route('/like_video/<int:video_id>', methods=['POST'])
def like_video(video_id):
    if 'user' not in session: return jsonify({"status": "error"})
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE videos SET likes = likes + 1 WHERE id = ?", (video_id,))
    cursor.execute("SELECT likes FROM videos WHERE id = ?", (video_id,))
    likes = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "likes": likes})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
