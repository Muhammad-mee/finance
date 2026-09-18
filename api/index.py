<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Финансовый Учет</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#111827">
    <style>
        body { background-color: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
        .card-stat { cursor: pointer; transition: transform 0.2s; border: none; color: white; border-radius: 12px; }
        .card-stat:hover { transform: translateY(-3px); }
        
        .bg-income { background-color: #198754 !important; }
        .bg-expense { background-color: #dc3545 !important; }
        .bg-debt { background-color: #ffc107 !important; color: #000 !important; }
        
        .badge-income { background-color: #198754; color: white; padding: 5px 10px; border-radius: 6px; }
        .badge-expense { background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 6px; }
        .badge-debt { background-color: #ffc107; color: black; padding: 5px 10px; border-radius: 6px; }

        .tr-income { border-left: 5px solid #198754; }
        .tr-expense { border-left: 5px solid #dc3545; }
        .tr-debt { border-left: 5px solid #ffc107; }
        .tr-hidden { opacity: 0.5; background-color: #e9ecef; }
        
        .avatar-img { width: 45px; height: 45px; object-fit: cover; border-radius: 50%; border: 2px solid #fff; }
        .btn-dots { background: transparent; border: none; font-size: 1.4rem; line-height: 1; padding: 0 8px; color: #6c757d; }
        .btn-dots:hover { color: #000; }
        
        .table-responsive { width: 100%; overflow-x: auto; }
    </style>
</head>
<body>

<nav class="navbar navbar-dark bg-dark mb-4 shadow-sm">
    <div class="container d-flex justify-content-between align-items-center">
        <span class="navbar-brand mb-0 h1">📊 Панель Учета</span>
        <div class="d-flex align-items-center gap-3 text-white">
            <img src="{{ current_user.avatar_url or 'https://via.placeholder.com/150' }}" class="avatar-img" alt="Avatar">
            <span>{{ current_user.username }} (<strong>{{ current_user.role }}</strong>)</span>
            <a href="{{ url_for('logout') }}" class="btn btn-outline-light btn-sm">Выход</a>
        </div>
    </div>
</nav>

<div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for message in messages %}
          <div class="alert alert-info alert-dismissible fade show shadow-sm" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <!-- Карточки -->
    <div class="row g-3 mb-4">
        <div class="col-md-4">
            <div class="card card-stat bg-income p-3 text-center shadow-sm" onclick="filterType('income')">
                <h5>Доход</h5>
                <h3>{{ income }}</h3>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card card-stat bg-expense p-3 text-center shadow-sm" onclick="filterType('expense')">
                <h5>Затраты</h5>
                <h3>{{ expense }}</h3>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card card-stat bg-debt p-3 text-center shadow-sm" onclick="filterType('debt')">
                <h5>Долги</h5>
                <h3>{{ debt }}</h3>
            </div>
        </div>
    </div>

    <!-- Добавление записи и Смена аватарки -->
    <div class="row g-3 mb-4">
        <div class="col-lg-8">
            <div class="card p-3 shadow-sm border-0">
                <h5 class="mb-3">➕ Добавить запись</h5>
                <form action="{{ url_for('add_record') }}" method="POST" class="row g-2">
                    <div class="col-md-3">
                        <select name="type" class="form-select" required>
                            <option value="income">Доход</option>
                            <option value="expense">Затраты</option>
                            <option value="debt">Долг</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <input type="number" step="any" name="amount" class="form-control" placeholder="Сумма" required>
                    </div>
                    <div class="col-md-4">
                        <input type="text" name="description" class="form-control" placeholder="Описание">
                    </div>
                    <div class="col-md-2">
                        <button type="submit" class="btn btn-success w-100">Сохранить</button>
                    </div>
                </form>
            </div>
        </div>

        <div class="col-lg-4">
            <div class="card p-3 shadow-sm border-0">
                <h5 class="mb-3">🖼️ Загрузить аватарку</h5>
                <form action="{{ url_for('update_avatar') }}" method="POST" enctype="multipart/form-data">
                    <input type="file" name="avatar_file" accept="image/*" class="form-control mb-2" required>
                    <button type="submit" class="btn btn-primary btn-sm w-100">Изменить фото</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Управление пользователями для Суперадмина -->
    {% if current_user.role == 'superadmin' %}
    <div class="card p-3 mb-4 shadow-sm border-danger">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h5 class="text-danger m-0">👑 Управление пользователями</h5>
            <button class="btn btn-danger btn-sm" data-bs-toggle="modal" data-bs-target="#createAdminModal">+ Новый пользователь</button>
        </div>

        <div class="table-responsive">
            <table class="table align-middle">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Пользователь</th>
                        <th>Роль</th>
                        <th class="text-end">Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for u in users %}
                    <tr>
                        <td>{{ u.id }}</td>
                        <td><strong>{{ u.username }}</strong></td>
                        <td><span class="badge bg-secondary">{{ u.role }}</span></td>
                        <td class="text-end">
                            <!-- Меню 3 точки для Пользователя -->
                            <div class="dropdown">
                                <button class="btn-dots" type="button" data-bs-toggle="dropdown">⋮</button>
                                <ul class="dropdown-menu dropdown-menu-end shadow">
                                    <li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#editUserModal{{ u.id }}">✏️ Редактировать</a></li>
                                    {% if u.username != current_user.username %}
                                    <li><hr class="dropdown-divider"></li>
                                    <li>
                                        <form action="{{ url_for('delete_user', id=u.id) }}" method="POST" onsubmit="return confirm('Удалить аккаунт {{ u.username }}?');">
                                            <button type="submit" class="dropdown-item text-danger">🗑️ Удалить</button>
                                        </form>
                                    </li>
                                    {% endif %}
                                </ul>
                            </div>

                            <!-- Модальное окно редактирования пользователя -->
                            <div class="modal fade text-start" id="editUserModal{{ u.id }}" tabindex="-1">
                                <div class="modal-dialog">
                                    <div class="modal-content">
                                        <form action="{{ url_for('edit_user', id=u.id) }}" method="POST">
                                            <div class="modal-header">
                                                <h5 class="modal-title">Редактировать: {{ u.username }}</h5>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                            </div>
                                            <div class="modal-body">
                                                <div class="mb-3">
                                                    <label class="form-label">Новое имя пользователя</label>
                                                    <input type="text" name="username" class="form-control" value="{{ u.username }}">
                                                </div>
                                                <div class="mb-3">
                                                    <label class="form-label">Новый пароль</label>
                                                    <input type="password" name="password" class="form-control" placeholder="Оставьте пустым, если не меняете">
                                                </div>
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                                                <button type="submit" class="btn btn-primary">Сохранить</button>
                                            </div>
                                        </form>
                                    </div>
                                </div>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% endif %}

    <!-- Таблица записей -->
    <div class="card p-3 shadow-sm border-0 mb-5">
        <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
            <h5 class="m-0">📋 Список записей</h5>
            
            <div class="d-flex align-items-center gap-2 flex-wrap">
                <a href="{{ url_for('export_csv') }}" class="btn btn-outline-success btn-sm">📥 Скачать отчет (CSV)</a>
                {% if current_user.role == 'superadmin' %}
                <div class="form-check form-switch me-2">
                    <input class="form-check-input" type="checkbox" id="showHiddenToggle" {% if show_hidden %}checked{% endif %} onchange="toggleHiddenView(this.checked)">
                    <label class="form-check-label small" for="showHiddenToggle">Показывать скрытые</label>
                </div>
                {% endif %}
                <button class="btn btn-outline-secondary btn-sm" onclick="filterType('all')">Все записи</button>
            </div>
        </div>
        
        <div class="table-responsive">
            <table class="table align-middle">
                <thead>
                    <tr>
                        <th>Тип</th>
                        <th>Сумма</th>
                        <th>Описание</th>
                        <th>Кто изменил</th>
                        <th>Дата</th>
                        {% if current_user.role == 'superadmin' %}<th class="text-end">Действия</th>{% endif %}
                    </tr>
                </thead>
                <tbody id="records-table">
                    {% for r in records %}
                    <tr class="record-row tr-{{ r.type }} {% if r.is_hidden %}tr-hidden{% endif %}" data-type="{{ r.type }}">
                        <td>
                            {% if r.type == 'income' %}<span class="badge-income">Доход</span>{% endif %}
                            {% if r.type == 'expense' %}<span class="badge-expense">Затраты</span>{% endif %}
                            {% if r.type == 'debt' %}<span class="badge-debt">Долг</span>{% endif %}
                            {% if r.is_hidden %}<span class="badge bg-secondary ms-1">Скрыто</span>{% endif %}
                        </td>
                        <td><strong>{{ r.amount }}</strong></td>
                        <td>{{ r.description or '-' }}</td>
                        <td><strong>{{ r.updated_by }}</strong></td>
                        <td>{{ r.updated_at.strftime('%Y-%m-%d %H:%M') }}</td>
                        
                        {% if current_user.role == 'superadmin' %}
                        <td class="text-end">
                            <!-- Меню 3 точки для Записи -->
                            <div class="dropdown">
                                <button class="btn-dots" type="button" data-bs-toggle="dropdown">⋮</button>
                                <ul class="dropdown-menu dropdown-menu-end shadow">
                                    <li>
                                        <form action="{{ url_for('toggle_hide_record', id=r.id) }}" method="POST">
                                            <button type="submit" class="dropdown-item">
                                                {% if r.is_hidden %}👁️ Показать{% else %}🙈 Скрыть{% endif %}
                                            </button>
                                        </form>
                                    </li>
                                    <li><hr class="dropdown-divider"></li>
                                    <li>
                                        <form action="{{ url_for('delete_record', id=r.id) }}" method="POST" onsubmit="return confirm('Удалить эту запись?');">
                                            <button type="submit" class="dropdown-item text-danger">🗑️ Удалить</button>
                                        </form>
                                    </li>
                                </ul>
                            </div>
                        </td>
                        {% endif %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>

<!-- Модальное окно создания админа -->
{% if current_user.role == 'superadmin' %}
<div class="modal fade" id="createAdminModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <form action="{{ url_for('create_admin') }}" method="POST">
                <div class="modal-header">
                    <h5 class="modal-title">Создать нового пользователя</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">Имя пользователя</label>
                        <input type="text" name="username" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Пароль</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Роль</label>
                        <select name="role" class="form-select">
                            <option value="admin">Администратор</option>
                            <option value="superadmin">Суперадмин</option>
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn btn-danger">Создать</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endif %}

<script>
function filterType(type) {
    let rows = document.querySelectorAll('.record-row');
    rows.forEach(row => {
        if (type === 'all' || row.getAttribute('data-type') === type) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

function toggleHiddenView(show) {
    let url = new URL(window.location.href);
    url.searchParams.set('show_hidden', show);
    window.location.href = url.href;
}
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
