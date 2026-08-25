import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'yellow_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Простая база данных в памяти
users = {}  # {username: password}
friends = {} # {username: [list_of_friends]}
messages = [] # [{sender, receiver, filename}]

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = session['user']
    user_friends = friends.get(user, [])
    user_videos = [m for m in messages if m['receiver'] == user]
    return render_template('dashboard.html', user=user, friends=user_friends, videos=user_videos)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if username in users:
            return "Пользователь уже существует!"
        users[username] = password
        friends[username] = []
        session['user'] = username
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if users.get(username) == password:
            session['user'] = username
            return redirect(url_for('home'))
        return "Неверный логин или пароль!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/add_friend', methods=['POST'])
def add_friend():
    if 'user' not in session:
        return redirect(url_for('login'))
    friend_name = request.form['friend_name'].strip()
    if friend_name in users and friend_name != session['user']:
        if friend_name not in friends[session['user']]:
            friends[session['user']].append(friend_name)
    return redirect(url_for('home'))

@app.route('/send_video', methods=['POST'])
def send_video():
    if 'user' not in session:
        return redirect(url_for('login'))
    receiver = request.form['receiver']
    file = request.files['video']
    if file and receiver in friends[session['user']]:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        messages.append({'sender': session['user'], 'receiver': receiver, 'filename': filename})
    return redirect(url_for('home'))

@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)