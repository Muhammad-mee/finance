import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='../templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it')

# --- Настройка подключения к БД ---
# Автоматический поиск URL базы данных во всех возможных переменных Vercel
db_url = (
    os.environ.get('NEON_URL') or 
    os.environ.get('POSTGRES_URL') or 
    os.environ.get('POSTGRES_URL_NON_POOLING') or 
    os.environ.get('STORAGE_URL') or 
    os.environ.get('DATABASE_URL') or 
    ''
)

# Корректировка формата для SQLAlchemy
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url and "sslmode" not in db_url and "sqlite" not in db_url:
    delimiter = "&" if "?" in db_url else "?"
    db_url += f"{delimiter}sslmode=require"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Исправление протокола postgres:// на postgresql://
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Добавление SSL-режима при необходимости
if db_url and "sslmode" not in db_url and "sqlite" not in db_url:
    delimiter = "&" if "?" in db_url else "?"
    db_url += f"{delimiter}sslmode=require"

# Если URL пустой, используем временную SQLite, чтобы Vercel не падал при сборке
app.config['SQLALCHEMY_DATABASE_URI'] = db_url if db_url else 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Модели БД ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    avatar_url = db.Column(db.String(500), default='https://via.placeholder.com/150')

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    updated_by = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_name = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Первоначальная инициализация таблиц и аккаунтов ---
def init_db():
    with app.app_context():
        try:
            db.create_all()
            
            # Создаем системных пользователей
            if not User.query.filter_by(username='admin').first():
                admin = User(username='admin', password_hash=generate_password_hash('admin123'), role='admin')
                guest = User(username='guest', password_hash=generate_password_hash('guest123'), role='guest')
                db.session.add_all([admin, guest])

            # Создаем список администраторов
            admin_users = ['Sherdor', 'Abdulaziz', 'Abdulbosit', 'Usmoncha', 'Muhammadsodiq']
            default_pwd = generate_password_hash('Sam11sam1')

            for username in admin_users:
                if not User.query.filter_by(username=username).first():
                    new_admin = User(username=username, password_hash=default_pwd, role='admin')
                    db.session.add(new_admin)
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()

# Вызов инициализации при загрузке модуля
try:
    init_db()
except Exception:
    pass

# --- Маршруты ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    records = Record.query.all()
    total_income = sum(r.amount for r in records if r.type == 'income')
    total_expense = sum(r.amount for r in records if r.type == 'expense')
    total_debt = sum(r.amount for r in records if r.type == 'debt')
    
    return render_template('dashboard.html', 
                           records=records, 
                           income=total_income, 
                           expense=total_expense, 
                           debt=total_debt)

@app.route('/add_record', methods=['POST'])
@login_required
def add_record():
    if current_user.role != 'admin':
        flash('Только администраторы могут вносить изменения!')
        return redirect(url_for('dashboard'))

    rec_type = request.form['type']
    amount = float(request.form['amount'])
    desc = request.form['description']

    new_record = Record(type=rec_type, amount=amount, description=desc, updated_by=current_user.username)
    db.session.add(new_record)

    log = AuditLog(action=f"Добавлено {rec_type}: {amount} ({desc})", user_name=current_user.username)
    db.session.add(log)
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    if current_user.role != 'admin':
        flash('Только админ может менять аватарку!')
        return redirect(url_for('dashboard'))

    url = request.form.get('avatar_url')
    if url:
        current_user.avatar_url = url
        db.session.commit()
        flash('Ссылка на аватарку обновлена!')
    return redirect(url_for('dashboard'))

@app.route('/audit')
@login_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit.html', logs=logs)
