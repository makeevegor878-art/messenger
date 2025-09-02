# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit, join_room
from models import db, User, Chat, Message
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Создаём таблицы
with app.app_context():
    db.create_all()

    # Пример: создать тестовый чат, если нет
    if Chat.query.count() == 0:
        test_chat = Chat(name="Общий чат")
        db.session.add(test_chat)
        db.session.commit()


# --- Маршруты ---
@app.route('/')
@login_required
def index():
    chats = Chat.query.all()
    return render_template('chat.html', user=current_user, chats=chats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect('/')
        else:
            flash("Неверный логин или пароль")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash("Пользователь уже существует")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect('/')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

# --- Socket.IO ---
@socketio.on('join')
def on_join(data):
    chat_id = data['chat_id']
    join_room(chat_id)

@socketio.on('send_message')
def handle_message(data):
    chat_id = data['chat_id']
    user_id = session.get('_user_id')
    content = data.get('content', '')
    file_url = data.get('file_url', '')

    # Сохраняем в БД
    msg = Message(chat_id=chat_id, user_id=user_id, content=content, file_url=file_url)
    db.session.add(msg)
    db.session.commit()

    # Отправляем всем в чат
    emit('receive_message', {
        'username': current_user.username,
        'content': content,
        'file_url': file_url,
        'timestamp': msg.timestamp.strftime("%H:%M")
    }, room=chat_id, include_self=True)

# --- Загрузка файлов ---
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return 'No file', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    # Разрешённые типы
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx'}
    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed:
        filename = f"{current_user.id}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return {'url': f'/static/uploads/{filename}'}
    return 'Invalid file type', 400

# --- Запуск с ngrok ---
if __name__ == '__main__':
    from pyngrok import ngrok

    # Открываем доступ к порту 5000
    public_url = ngrok.connect(5000)
    print(f" * Публичный URL: {public_url}")

    # Запускаем сервер
    socketio.run(app, host='127.0.0.1', port=5000)
