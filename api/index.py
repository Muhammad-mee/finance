import os
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='../templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///finance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='admin')  # admin или superadmin
    avatar_url = db.Column(db.String(500), nullable=True)

class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # income, expense, debt
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(db.String(150), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_hidden = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Инициализация БД
with app.app_context():
    db.create_all()

# --- МАРШРУТЫ И ЛОГИКА ---

@app.route('/')
@login_required
def dashboard():
    show_hidden = request.args.get('show_hidden', 'false').lower() == 'true'
    
    if current_user.role == 'superadmin' and show_hidden:
        records = Record.query.order_by(Record.updated_at.desc()).all()
    else:
        records = Record.query.filter_by(is_hidden=False).order_by(Record.updated_at.desc()).all()

    # Расчет сумм (только активные записи)
    income = sum(r.amount for r in records if r.type == 'income' and not r.is_hidden)
    expense = sum(r.amount for r in records if r.type == 'expense' and not r.is_hidden)
    debt = sum(r.amount for r in records if r.type == 'debt' and not r.is_hidden)

    users = User.query.all() if current_user.role == 'superadmin' else []

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
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
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

@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    # Простая форма сохранения ссылки или имени файла
    file = request.files.get('avatar_file')
    if file:
        filename = secure_filename(file.filename)
        # Для Vercel без S3 лучше хранить URL или использовать базовую заглушку
        current_user.avatar_url = f"https://api.dicebear.com/7.x/bottts/svg?seed={filename}"
        db.session.commit()
        flash('Аватар обновлен!')
    return redirect(url_for('dashboard'))

@app.route('/export_csv')
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Тип', 'Сумма', 'Описание', 'Кто изминил', 'Дата'])

    records = Record.query.filter_by(is_hidden=False).all()
    for r in records:
        writer.writerow([r.id, r.type, r.amount, r.description or '', r.updated_by, r.updated_at.strftime('%Y-%m-%d %H:%M')])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': 'attachment; filename=financial_report.csv'}
    )

@app.route('/toggle_hide_record/<int:id>', methods=['POST'])
@login_required
def toggle_hide_record(id):
    if current_user.role != 'superadmin':
        return redirect(url_for('dashboard'))
    rec = Record.query.get_or_404(id)
    rec.is_hidden = not rec.is_hidden
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    if current_user.role != 'superadmin':
        return redirect(url_for('dashboard'))
    rec = Record.query.get_or_404(id)
    db.session.delete(rec)
    db.session.commit()
    flash('Запись удалена.')
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
        return redirect(url_for('dashboard'))

    hashed_pw = generate_password_hash(password, method='scrypt')
    new_user = User(username=username, password=hashed_pw, role=role)
    db.session.add(new_user)
    db.session.commit()
    flash('Пользователь успешно создан!')
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
        user.password = generate_password_hash(new_password, method='scrypt')
    db.session.commit()
    flash('Данные пользователя обновлены!')
    return redirect(url_for('dashboard'))

@app.route('/delete_user/<int:id>', methods=['POST'])
@login_required
def delete_user(id):
    if current_user.role != 'superadmin':
        return redirect(url_for('dashboard'))
    user = User.query.get_or_404(id)
    if user.username != current_user.username:
        db.session.delete(user)
        db.session.commit()
        flash('Пользователь удален!')
    return redirect(url_for('dashboard'))

# Экспорт приложения для Vercel / WSGI
app = app
