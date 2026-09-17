import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='../templates')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it')

# Получаем URL базы данных
db_url = os.environ.get('POSTGRES_URL', 'sqlite:///:memory:')

# Исправляем префикс postgres:// -> postgresql:// для Flask-SQLAlchemy
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
# --- Модели БД ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'admin' или 'guest'
    avatar_url = db.Column(db.String(500), default='https://via.placeholder.com/150')

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # 'income', 'expense', 'debt'
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

# --- Авто-создание БД и всех администраторов при старте ---
@app.before_request
def init_db_once():
    db.create_all()
    
    # Базовые аккаунты по умолчанию
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin123'), role='admin')
        guest = User(username='guest', password_hash=generate_password_hash('guest123'), role='guest')
        db.session.add_all([admin, guest])
        db.session.commit()

    # Список новых администраторов
    admin_users = ['Sherdor', 'Abdulaziz', 'Abdulbosit', 'Usmoncha', 'Muhammadsodiq']
    default_password_hash = generate_password_hash('Sam11sam1')

    for username in admin_users:
        if not User.query.filter_by(username=username).first():
            new_admin = User(
                username=username, 
                password_hash=default_password_hash, 
                role='admin' # Назначение роли АДМИНИСТРАТОРА
            )
            db.session.add(new_admin)
    
    db.session.commit()

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

app = app

if __name__ == '__main__':
    app.run(debug=True)
