import os
import base64
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-change-it')

# Настройка сохранения входа (не нужно вводить логин и пароль каждый раз)
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_REFRESH_EACH_REQUEST'] = True

# Настройка подключения к БД
db_url = (
    os.environ.get('NEON_URL') or 
    os.environ.get('POSTGRES_URL') or 
    os.environ.get('STORAGE_URL') or 
    os.environ.get('DATABASE_URL') or 
    ''
)

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url and "sslmode" not in db_url and "sqlite" not in db_url:
    delimiter = "&" if "?" in db_url else "?"
    db_url += f"{delimiter}sslmode=require"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url if db_url else 'sqlite:///:memory:'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # superadmin, admin
    avatar_url = db.Column(db.Text, default='https://via.placeholder.com/150')

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False) # income, expense, debt
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

# Инициализация БД
def init_db():
    with app.app_context():
        try:
            db.create_all()
            pwd = generate_password_hash('Sam11sam1')
            
            if not User.query.filter_by(username='superadmin').first():
                db.session.add(User(username='superadmin', password_hash=pwd, role='superadmin'))

            admins = ['Sherdor', 'Abdulaziz', 'Abdulbosit', 'Usmoncha', 'Muhammadsodiq']
            for name in admins:
                if not User.query.filter_by(username=name).first():
                    db.session.add(User(username=name, password_hash=pwd, role='admin'))
            
            db.session.commit()
        except Exception:
            db.session.rollback()

try:
    init_db()
except Exception:
    pass

# Раздача файлов для PWA
@app.route('/manifest.json')
def manifest():
    return send_from_directory('../static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('../static', 'sw.js')

# Маршруты
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            # remember=True сохраняет сессию даже при закрытии браузера/приложения
            login_user(user, remember=True)
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
    records = Record.query.order_by(Record.updated_at.desc()).all()
    users = User.query.all() if current_user.role == 'superadmin' else []
    
    total_income = sum(r.amount for r in records if r.type == 'income')
    total_expense = sum(r.amount for r in records if r.type == 'expense')
    total_debt = sum(r.amount for r in records if r.type == 'debt')
    
    return render_template('dashboard.html', 
                           records=records, 
                           users=users,
                           income=total_income, 
                           expense=total_expense, 
                           debt=total_debt)

@app.route('/add_record', methods=['POST'])
@login_required
def add_record():
    if current_user.role not in ['admin', 'superadmin']:
        flash('Отказано в доступе!')
        return redirect(url_for('dashboard'))

    try:
        rec_type = request.form.get('type')
        amount = float(request.form.get('amount', 0))
        desc = request.form.get('description', '')

        new_rec = Record(type=rec_type, amount=amount, description=desc, updated_by=current_user.username)
        db.session.add(new_rec)
        db.session.add(AuditLog(action=f"Добавлено {rec_type}: {amount}", user_name=current_user.username))
        db.session.commit()
        flash('Запись добавлена!')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {e}')
    return redirect(url_for('dashboard'))

@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role != 'superadmin':
        flash('Удалять записи может только Суперадмин!')
        return redirect(url_for('dashboard'))
    
    rec = Record.query.get_or_404(id)
    db.session.delete(rec)
    db.session.add(AuditLog(action=f"Удалена запись ID {id}", user_name=current_user.username))
    db.session.commit()
    flash('Запись успешно удалена!')
    return redirect(url_for('dashboard'))

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    file = request.files.get('avatar_file')
    if file and file.filename != '':
        encoded = base64.b64encode(file.read()).decode('utf-8')
        mime = file.mimetype or 'image/png'
        current_user.avatar_url = f"data:{mime};base64,{encoded}"
        db.session.commit()
        flash('Аватарка успешно изменена!')
    else:
        flash('Выберите файл изображения!')
    return redirect(url_for('dashboard'))

@app.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    if current_user.role != 'superadmin':
        return redirect(url_for('dashboard'))
    
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'admin')
    
    if User.query.filter_by(username=username).first():
        flash('Пользователь уже существует!')
    else:
        new_user = User(username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(new_user)
        db.session.commit()
        flash(f'Пользователь {username} создан!')
    return redirect(url_for('dashboard'))

@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    if current_user.role != 'superadmin':
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(id)
    new_username = request.form.get('username')
    new_password = request.form.get('password')
    
    if new_username:
        user.username = new_username
    if new_password:
        user.password_hash = generate_password_hash(new_password)
        
    db.session.commit()
    flash(f'Данные пользователя {user.username} обновлены!')
    return redirect(url_for('dashboard'))
