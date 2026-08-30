import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'yellownet_enterprise_production_key_2026'
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = os.path.join('static', 'uploads')
AVATAR_FOLDER = os.path.join('static', 'avatars')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm', 'png', 'jpg', 'jpeg', 'gif'}

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
    
    # Таблица пользователей с био и аватаркой
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        username TEXT UNIQUE NOT NULL, 
                        email TEXT NOT NULL, 
                        phone TEXT NOT NULL, 
                        password TEXT NOT NULL,
                        bio TEXT DEFAULT 'Добро пожаловать в мой профиль YellowNet!', 
                        avatar TEXT DEFAULT 'default.png',
                        joined_date DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица друзей
    cursor.execute('''CREATE TABLE IF NOT EXISTS friends (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user_id INTEGER, 
                        friend_username TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Таблица видеопостов (с поддержкой глобальной ленты и лайков)
    cursor.execute('''CREATE TABLE IF NOT EXISTS videos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        sender TEXT, 
                        receiver TEXT, 
                        filename TEXT, 
                        likes INTEGER DEFAULT 0, 
                        is_global INTEGER DEFAULT 0, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица личных сообщений чата
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        sender TEXT, 
                        receiver TEXT, 
                        text TEXT, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица системных уведомлений
    cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user TEXT, 
                        message TEXT, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
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
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return render_template('login.html', error="Заполните все поля!")
            
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
            # Автоматическая регистрация при первом входе для удобства
            try:
                cursor.execute("INSERT INTO users (username, email, phone, password) VALUES (?, ?, ?, ?)",
                               (username, f"{username}@yellownet.local", "000000000", password))
                conn.commit()
                conn.close()
                session['user'] = username
                return redirect(url_for('dashboard'))
            except Exception as e:
                conn.close()
                return render_template('login.html', error="Ошибка создания аккаунта")
                
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '').strip()
    
    if not username or not email or not password:
        return render_template('login.html', error="Заполните обязательные поля регистрации!")
        
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
        return render_template('login.html', error="Такое имя пользователя уже занято!")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
        
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

    # Загружаем видео (личные для пользователя или глобальные)
    cursor.execute("""SELECT id, filename, sender, likes, timestamp, is_global 
                      FROM videos WHERE receiver = ? OR is_global = 1 ORDER BY id DESC""", (username,))
    videos = cursor.fetchall()

    cursor.execute("SELECT message, timestamp FROM notifications WHERE user = ? ORDER BY id DESC LIMIT 15", (username,))
    notifications = cursor.fetchall()
    
    stats = {"friends": len(friends), "videos": len(videos)}
    conn.close()
    
    return render_template('dashboard.html', user=username, bio=bio, avatar=avatar, 
                           friends=friends, videos=videos, notifications=notifications, stats=stats)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    username = session['user']
    bio = request.form.get('bio', '').strip()
    file = request.files.get('avatar_file')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    if bio:
        cursor.execute("UPDATE users SET bio = ? WHERE username = ?", (bio, username))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        avatar_name = f"{username}_{filename}"
        file.save(os.path.join(app.config['AVATAR_FOLDER'], avatar_name))
        cursor.execute("UPDATE users SET avatar = ? WHERE username = ?", (avatar_name, username))
        
    conn.commit()
    conn.close()
    flash("Профиль успешно обновлен!", "success")
    return redirect(url_for('dashboard'))

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    friend_name = request.form.get('friend_name', '').strip()
    username = session['user']
    
    if friend_name == username:
        flash("Нельзя добавить самого себя в друзья!", "error")
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
                           (friend_name, f"🤝 Пользователь @{username} добавил вас в друзья!"))
            conn.commit()
            flash(f"@{friend_name} успешно добавлен в список друзей!", "success")
        else:
            flash("Этот пользователь уже у вас в друзьях", "info")
    else:
        flash("Пользователь с таким именем не найден в системе", "error")
        
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'user' not in session:
        return redirect(url_for('login'))
        
    receiver = request.form.get('receiver', '').strip()
    is_global = 1 if request.form.get('is_global') == 'on' else 0
    file = request.files.get('video_file')
    sender = session['user']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_filename = f"{sender}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], save_filename))

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO videos (sender, receiver, filename, is_global) VALUES (?, ?, ?, ?)", 
                       (sender, receiver if not is_global else "ALL", save_filename, is_global))
        
        if not is_global and receiver:
            cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", 
                           (receiver, f"🎬 Новое личное видео от @{sender}!"))
        conn.commit()
        conn.close()
        flash("Видео успешно опубликовано в ленте!", "success")
    else:
        flash("Ошибка при загрузке файла (проверьте формат)", "error")
        
    return redirect(url_for('dashboard'))

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"})
        
    data = request.get_json()
    receiver = data.get('receiver')
    text = data.get('text', '').strip()
    sender = session['user']
    
    if not text or not receiver:
        return jsonify({"status": "error", "message": "Empty data"})
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)", (sender, receiver, text))
    cursor.execute("INSERT INTO notifications (user, message) VALUES (?, ?)", 
                   (receiver, f"💬 Новое сообщение от @{sender}"))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/get_messages/<friend>', methods=['GET'])
def get_messages(friend):
    if 'user' not in session:
        return jsonify([])
        
    username = session['user']
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""SELECT sender, text, timestamp FROM messages 
                      WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?) 
                      ORDER BY id ASC""", (username, friend, friend, username))
    
    msgs = [{"sender": row[0], "text": row[1], "time": row[2][11:16]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(msgs)

@app.route('/like_video/<int:video_id>', methods=['POST'])
def like_video(video_id):
    if 'user' not in session:
        return jsonify({"status": "error"})
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE videos SET likes = likes + 1 WHERE id = ?", (video_id,))
    cursor.execute("SELECT likes FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    likes = row[0] if row else 0
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "likes": likes})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
