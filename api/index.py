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

# --- Настройка подключения к Neon PostgreSQL / SQLite ---
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

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---
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

# --- ИНИЦИАЛИЗАЦИЯ СТРУКТУРЫ И СОЗДАНИЕ CREATOR ---
db_initialized = False

def init_db():
    global db_initialized
    if db_initialized:
        return
    try:
        db.create_all()
        db.session.execute(text("ALTER TABLE record ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS role_level INTEGER DEFAULT 0;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);"))
        db.session.commit()

        # Автоматическое создание/обновление пользователя Creator (sodiqjon)
        creator_user = User.query.filter_by(username='sodiqjon').first()
        if not creator_user:
            hashed_pw = generate_password_hash('0551410404a', method='scrypt')
            creator_user = User(username='sodiqjon', password=hashed_pw, role_level=3)
            db.session.add(creator_user)
            db.session.commit()
        else:
            if creator_user.role_level != 3:
                creator_user.role_level = 3
                db.session.commit()

        db_initialized = True
    except Exception as e:
        db.session.rollback()

@app.before_request
def ensure_db_init():
    init_db()

@app.route('/setup_db')
def setup_db():
    try:
        init_db()
        return "База данных успешно инициализирована! <a href='/login'>Перейти к входу</a>"
    except Exception as e:
        return f"Ошибка при настройке базы данных: {str(e)}"

# --- МАРШРУТЫ И ЛОГИКА ---

@app.route('/')
@login_required
def dashboard():
    # Показывать скрытые записи может только Creator (role_level == 3)
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true' and current_user.role_level == 3

    if current_user.role_level == 3 and show_hidden:
        records = Record.query.order_by(Record.updated_at.desc()).all()
    else:
        records = Record.query.filter_by(is_hidden=False).order_by(Record.updated_at.desc()).all()

    income = sum(r.amount for r in records if r.type == 'income' and not r.is_hidden)
    expense = sum(r.amount for r in records if r.type == 'expense' and not r.is_hidden)
    debt = sum(r.amount for r in records if r.type == 'debt' and not r.is_hidden)

    # Просмотр списка пользователей:
    # Creator (3) видит всех пользователей (кроме себя)
    # SuperAdmin (2) видит только Admin (1) и Guest (0)
    # Admin (1) и Guest (0) не видят список пользователей
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

# Добавление записей: доступно Admin (1), SuperAdmin (2), Creator (3)
@app.route('/add_record', methods=['POST'])
@login_required
def add_record():
    if current_user.role_level < 1:
        flash('У вас нет прав для добавления записей (роль Guest).')
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

    log = AuditLog(action=f"Добавлено {rec_type}: {amount} ({description})", user_name=current_user.username)
    db.session.add(log)

    db.session.commit()
    flash('Запись успешно добавлена!')
    return redirect(url_for('dashboard'))

# Редактирование записи: SuperAdmin (2) и Creator (3)
@app.route('/edit_record/<int:id>', methods=['POST'])
@login_required
def edit_record(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав для редактирования записей.')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    rec.type = request.form.get('type', rec.type)
    rec.amount = float(request.form.get('amount', rec.amount))
    rec.description = request.form.get('description', rec.description)
    rec.updated_by = current_user.username

    log = AuditLog(action=f"Изменена запись ID {rec.id}", user_name=current_user.username)
    db.session.add(log)

    db.session.commit()
    flash('Запись изменена.')
    return redirect(url_for('dashboard'))

# Удаление записи: SuperAdmin (2) и Creator (3)
@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав для удаления записей.')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    db.session.delete(rec)

    log = AuditLog(action=f"Удалена запись ID {id}", user_name=current_user.username)
    db.session.add(log)

    db.session.commit()
    flash('Запись удалена.')
    return redirect(url_for('dashboard'))

# Скрытие / Раскрытие записи: Только Creator (3)
@app.route('/toggle_hide_record/<int:id>', methods=['POST'])
@login_required
def toggle_hide_record(id):
    if current_user.role_level < 3:
        flash('Только Creator может скрывать или показывать записи.')
        return redirect(url_for('dashboard'))

    rec = Record.query.get_or_404(id)
    rec.is_hidden = not rec.is_hidden

    action_str = "Скрыта" if rec.is_hidden else "Восстановлена"
    log = AuditLog(action=f"{action_str} запись ID {id}", user_name=current_user.username)
    db.session.add(log)

    db.session.commit()
    flash(f'Статус скрытия записи изменен.')
    return redirect(url_for('dashboard'))

# Создание пользователей: Creator (3) может создавать любые роли; SuperAdmin (2) — только Admin (1) и Guest (0)
@app.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    if current_user.role_level < 2:
        flash('Недостаточно прав для создания пользователей.')
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')
    role_level = int(request.form.get('role_level', 1))

    # Ограничения по назначению ролей:
    if current_user.role_level < 3 and role_level >= 2:
        role_level = 1  # SuperAdmin не может создавать других SuperAdmin или Creator

    if User.query.filter_by(username=username).first():
        flash('Пользователь с таким именем уже существует!')
        return redirect(url_for('dashboard'))

    hashed_pw = generate_password_hash(password, method='scrypt')
    new_user = User(username=username, password=hashed_pw, role_level=role_level)
    db.session.add(new_user)
    db.session.commit()

    flash(f'Пользователь {username} (роль {role_level}) успешно создан!')
    return redirect(url_for('dashboard'))

# Изменение данных пользователя (логин, пароль, роль): Creator (3) может менять всех, SuperAdmin (2) — только Admin и Guest
@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав для управления пользователями.')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(id)

    # SuperAdmin не может менять аккаунты уровня 2 и 3
    if current_user.role_level < 3 and user.role_level >= 2:
        flash('У вас нет прав на редактирование этого пользователя.')
        return redirect(url_for('dashboard'))

    new_username = request.form.get('username')
    new_password = request.form.get('password')
    new_role_level = request.form.get('role_level')

    if new_username:
        user.username = new_username
    if new_password:
        user.password = generate_password_hash(new_password, method='scrypt')
    if new_role_level is not None:
        lvl = int(new_role_level)
        if current_user.role_level == 3 or lvl < 2:
            user.role_level = lvl

    db.session.commit()
    flash(f'Данные пользователя {user.username} обновлены!')
    return redirect(url_for('dashboard'))

# Удаление пользователя
@app.route('/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if current_user.role_level < 2:
        flash('Недостаточно прав.')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(id)

    # Нельзя удалить сам себя или Creator
    if user.username == current_user.username or user.role_level == 3:
        flash('Нельзя удалить этот аккаунт!')
        return redirect(url_for('dashboard'))

    # SuperAdmin не может удалять других SuperAdmin
    if current_user.role_level < 3 and user.role_level >= 2:
        flash('У вас нет прав на удаление этого пользователя.')
        return redirect(url_for('dashboard'))

    db.session.delete(user)
    db.session.commit()
    flash('Пользователь удален!')
    return redirect(url_for('dashboard'))

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    file = request.files.get('avatar_file')
    avatar_url = request.form.get('avatar_url')

    if file and file.filename:
        current_user.avatar_url = f"https://api.dicebear.com/7.x/bottts/svg?seed={file.filename}"
    elif avatar_url:
        current_user.avatar_url = avatar_url

    db.session.commit()
    flash('Аватар обновлен!')
    return redirect(url_for('dashboard'))

@app.route('/export_csv')
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Тип', 'Сумма', 'Описание', 'Кто изменил', 'Дата'])

    records = Record.query.filter_by(is_hidden=False).all()
    for r in records:
        writer.writerow([r.id, r.type, r.amount, r.description or '', r.updated_by, r.updated_at.strftime('%Y-%m-%d %H:%M')])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': 'attachment; filename=financial_report.csv'}
    )

@app.route('/audit')
@login_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit.html', logs=logs)
