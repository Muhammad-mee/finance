import os
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__, template_folder='../templates', instance_path='/tmp')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-123')

# --- Подключение к базе данных ---
db_url = (
    os.environ.get('DATABASE_URL') or 
    os.environ.get('POSTGRES_URL') or 
    os.environ.get('NEON_DATABASE_URL') or 
    os.environ.get('NEON_URL') or 
    'sqlite:////tmp/finance.db'
)

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if ("neon.tech" in db_url or "supabase.co" in db_url) and "sslmode" not in db_url:
    delimiter = "&" if "?" in db_url else "?"
    db_url += f"{delimiter}sslmode=require"

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
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
    __tablename__ = 'app_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role_level = db.Column(db.Integer, default=0, nullable=False)  # 0: Guest, 1: Admin, 2: SuperAdmin, 3: Creator
    avatar_url = db.Column(db.String(500), nullable=True)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(db.String(150), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_hidden = db.Column(db.Boolean, default=False)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    user_name = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

def init_db():
    try:
        db.create_all()
        db.session.execute(text("ALTER TABLE record ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS role_level INTEGER DEFAULT 0;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);"))
        db.session.commit()

        creator_user = User.query.filter_by(username='sodiqjon').first()
        if creator_user:
            if creator_user.role_level != 3:
                creator_user.role_level = 3
                db.session.commit()
        else:
            hashed_pw = generate_password_hash('0551410404a')
            new_creator = User(username='sodiqjon', password=hashed_pw, role_level=3)
            db.session.add(new_creator)
            db.session.commit()
    except Exception as e:
        db.session.rollback()

@app.before_request
def ensure_db_init():
    init_db()

@app.route('/')
@login_required
def dashboard():
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true' and current_user.role_level == 3

    if current_user.role_level == 3 and show_hidden:
        records = Record.query.order_by(Record.updated_at.desc()).all()
    else:
        records = Record.query.filter_by(is_hidden=False).order_by(Record.updated_at.desc()).all()

    # Суммы считаются только повидимым записям (если не включен показ скрытых)
    income = sum(r.amount for r in records if r.type == 'income')
    expense = sum(r.amount for r in records if r.type == 'expense')
    debt = sum(r.amount for r in records if r.type == 'debt')

    if current_user.role_level == 3:
        users = User.query.filter(User.username != current_user.username).all()
    elif current_user.role_level == 2:
        users = User.query.filter(User.role_level <= 1).all()
    else:
        users = []

    return render_template('dashboard.html', 
                           records=records, 
                           income=income, 
                           expense=expense, 
                           debt=debt, 
                           users=users, 
                           show_hidden=show_hidden)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        try:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Ошибка входа: {str(e)}')
            return render_template('login.html')
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_record', methods=['POST'])
@login_required
def add_record():
    if current_user.role_level < 1:
        flash('У вас нет прав для добавления записей.')
        return redirect(url_for('dashboard'))

    rec_type = request.form.get('type')
    amount = float(request.form.get('amount', 0))
    description = request.form.get('description')

    new_rec = Record(
        type=rec_type,
        amount=amount,
        description=description,
        updated_by=current_user.username
    )
    db.session.add(new_rec)
    db.session.commit()
    flash('Запись успешно добавлена!')
    return redirect(url_for('dashboard'))

# Редактирование: разрешено SuperAdmin (2) и Creator (3)
@app.route('/edit_record/<int:id>', methods=['POST'])
@login_required
def edit_record(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав.')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    rec.type = request.form.get('type', rec.type)
    rec.amount = float(request.form.get('amount', rec.amount))
    rec.description = request.form.get('description', rec.description)
    rec.updated_by = current_user.username

    db.session.commit()
    flash('Запись успешно обновлена.')
    return redirect(url_for('dashboard'))

# Удаление: разрешено ТОЛЬКО Creator (3 / sodiqjon)
@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role_level < 3:
        flash('Только Creator (sodiqjon) имеет право удалять записи!')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    db.session.delete(rec)
    db.session.commit()
    flash('Запись безвозвратно удалена.')
    return redirect(url_for('dashboard'))

# Скрытие / Восстановление: разрешено SuperAdmin (2) и Creator (3)
@app.route('/toggle_hide_record/<int:id>', methods=['POST'])
@login_required
def toggle_hide_record(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав для этой операции.')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    rec.is_hidden = not rec.is_hidden
    db.session.commit()

    status = "скрыта" if rec.is_hidden else "восстановлена"
    flash(f'Запись #{rec.id} {status}.')
    return redirect(url_for('dashboard'))

@app.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    if current_user.role_level < 2:
        flash('Недостаточно прав.')
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')
    role_level = int(request.form.get('role_level', 1))

    if current_user.role_level < 3 and role_level >= 2:
        role_level = 1

    if User.query.filter_by(username=username).first():
        flash('Пользователь уже существует!')
        return redirect(url_for('dashboard'))

    hashed_pw = generate_password_hash(password)
    new_user = User(username=username, password=hashed_pw, role_level=role_level)
    db.session.add(new_user)
    db.session.commit()

    flash(f'Пользователь {username} создан!')
    return redirect(url_for('dashboard'))

@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав.')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(id)
    if current_user.role_level < 3 and user.role_level >= 2:
        flash('Нет прав для изменения этого пользователя.')
        return redirect(url_for('dashboard'))

    new_username = request.form.get('username')
    new_password = request.form.get('password')

    if new_username:
        user.username = new_username
    if new_password:
        user.password = generate_password_hash(new_password)

    db.session.commit()
    flash('Данные пользователя обновлены!')
    return redirect(url_for('dashboard'))

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    avatar_url = request.form.get('avatar_url')
    avatar_file = request.files.get('avatar_file')

    # 1. Если передана прямая ссылка на изображение
    if avatar_url and avatar_url.strip():
        current_user.avatar_url = avatar_url.strip()
        db.session.commit()
        flash('Аватар обновлен по ссылке!')
        return redirect(url_for('dashboard'))

    # 2. Если загружен файл напрямую через форму
    if avatar_file and avatar_file.filename:
        # Здесь вы можете при необходимости подключить загрузку на внешнее облако (например, Cloudinary/Imgur)
        flash('Для загрузки файлов используйте прямую URL-ссылку на фото.')
        return redirect(url_for('dashboard'))

    flash('Укажите корректную ссылку на аватар.')
    return redirect(url_for('dashboard'))
