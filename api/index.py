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

# --- Настройка подключения к Neon PostgreSQL ---
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
    role_level = db.Column(db.Integer, default=1, nullable=False)
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

# --- АВТОМАТИЧЕСКАЯ ИНИЦИАЛИЗАЦИЯ СТРУКТУРЫ ---
db_initialized = False

def init_db():
    global db_initialized
    if db_initialized:
        return
    try:
        db.create_all()
        # Автоматическое добавление отсутствующих колонок в таблицу record и app_users
        db.session.execute(text("ALTER TABLE record ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS role_level INTEGER DEFAULT 1;"))
        db.session.execute(text("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);"))
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
        return "Структура таблиц обновлена! <a href='/login'>Перейти к входу</a>"
    except Exception as e:
        return f"Ошибка при настройке базы данных: {str(e)}"

# --- МАРШРУТЫ И ЛОГИКА ---

@app.route('/')
@login_required
def dashboard():
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true'

    if current_user.role_level >= 2 and show_hidden:
        records = Record.query.order_by(Record.updated_at.desc()).all()
    else:
        records = Record.query.filter_by(is_hidden=False).order_by(Record.updated_at.desc()).all()

    income = sum(r.amount for r in records if r.type == 'income' and not r.is_hidden)
    expense = sum(r.amount for r in records if r.type == 'expense' and not r.is_hidden)
    debt = sum(r.amount for r in records if r.type == 'debt' and not r.is_hidden)

    if current_user.role_level == 3:
        users = User.query.all()
    elif current_user.role_level == 2:
        users = User.query.filter(User.role_level < 3).all()
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
            flash(f'Ошибка БД: {str(e)}')
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
        flash('У гостей нет прав добавления записей!')
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

@app.route('/toggle_hide_record/<int:id>', methods=['POST'])
@login_required
def toggle_hide_record(id):
    if current_user.role_level < 2:
        return redirect(url_for('dashboard'))
    rec = Record.query.get_or_404(id)
    rec.is_hidden = not rec.is_hidden
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role_level < 2:
        return redirect(url_for('dashboard'))
    rec = Record.query.get_or_404(id)
    db.session.delete(rec)
    db.session.commit()
    flash('Запись удалена.')
    return redirect(url_for('dashboard'))

@app.route('/create_admin', methods=['POST'])
@login_required
def create_admin():
    if current_user.role_level < 2:
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')
    role_level = int(request.form.get('role_level', 1))

    if role_level >= 3 and current_user.role_level < 3:
        role_level = 2

    if User.query.filter_by(username=username).first():
        flash('Пользователь уже существует!')
        return redirect(url_for('dashboard'))

    hashed_pw = generate_password_hash(password, method='scrypt')
    new_user = User(username=username, password=hashed_pw, role_level=role_level)
    db.session.add(new_user)
    db.session.commit()
    flash('Пользователь успешно создан!')
    return redirect(url_for('dashboard'))

@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
def edit_user(id):
    if current_user.role_level < 2:
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(id)

    if user.role_level == 3 and current_user.role_level < 3:
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
        if lvl < 3 or current_user.role_level == 3:
            user.role_level = lvl

    db.session.commit()
    flash('Данные пользователя обновлены!')
    return redirect(url_for('dashboard'))

@app.route('/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if current_user.role_level < 2:
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(id)

    if user.role_level == 3:
        return redirect(url_for('dashboard'))

    if user.username != current_user.username:
        db.session.delete(user)
        db.session.commit()
        flash('Пользователь удален!')
        return redirect(url_for('dashboard'))
