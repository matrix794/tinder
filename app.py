from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, validators
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import re
from secrets import token_urlsafe
from datetime import datetime
from functools import wraps
from PIL import Image
from sqlalchemy import or_, func

try:
    from authlib.integrations.flask_client import OAuth
except Exception:
    OAuth = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
# Для локального запуска без PostgreSQL используем SQLite; для продакшена задайте DATABASE_URL
# По умолчанию — папка проекта; для проблем с записью (OneDrive и т.п.) задайте DATABASE_URL или используйте TEMP
import tempfile
_db_dir = os.path.dirname(os.path.abspath(__file__))
_db_path = os.path.join(_db_dir, 'tinder.db')
try:
    with open(_db_path, 'a'):
        pass
except OSError:
    _db_path = os.path.join(tempfile.gettempdir(), 'tinder.db')
_default_uri = 'sqlite:///' + _db_path.replace('\\', '/')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', _default_uri)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройки для загрузки файлов
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['ALLOWED_EXTENSIONS'] = ALLOWED_EXTENSIONS

# Создаем папку для загрузок
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Администраторы (список логинов через запятую в ENV ADMIN_USERS)
ADMIN_USERNAMES = {name.strip().lower() for name in os.environ.get('ADMIN_USERS', 'admin').split(',') if name.strip()}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'

# OAuth (Google / GitHub)
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['GITHUB_CLIENT_ID'] = os.environ.get('GITHUB_CLIENT_ID')
app.config['GITHUB_CLIENT_SECRET'] = os.environ.get('GITHUB_CLIENT_SECRET')
app.config['GOOGLE_CALLBACK_URL'] = os.environ.get('GOOGLE_CALLBACK_URL', 'http://localhost:5000/auth/google/callback')
app.config['GITHUB_CALLBACK_URL'] = os.environ.get('GITHUB_CALLBACK_URL', 'http://localhost:5000/auth/github/callback')

oauth = OAuth(app) if OAuth else None
google_oauth = None
github_oauth = None

if oauth:
    google_oauth = oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )
    github_oauth = oauth.register(
        name='github',
        client_id=app.config.get('GITHUB_CLIENT_ID'),
        client_secret=app.config.get('GITHUB_CLIENT_SECRET'),
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'read:user user:email'},
    )

# Модель пользователя
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с профилем студента
    profile = db.relationship('StudentProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Модель профиля студента
class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Основная информация
    full_name = db.Column(db.String(100), nullable=False)
    university = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(100), nullable=False)
    course = db.Column(db.Integer, nullable=False)
    
    # Предметы и интересы
    subjects = db.Column(db.Text)  # JSON строка с предметами
    interests = db.Column(db.Text)  # JSON строка с интересами
    
    # Описание и цели
    description = db.Column(db.Text)
    goals = db.Column(db.Text)
    
    # Предпочтения по партнеру
    preferred_subjects = db.Column(db.Text)  # JSON строка
    preferred_course = db.Column(db.String(50))  # например "1-3" или "4-6"
    
    # Контактная информация
    telegram = db.Column(db.String(50))
    discord = db.Column(db.String(50))
    
    # Фото профиля
    photo_filename = db.Column(db.String(255))
    
    # Статус
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Модель для лайков и дизлайков
class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    liker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    liked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_like = db.Column(db.Boolean, nullable=False)  # True для лайка, False для дизлайка
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Уникальный индекс для предотвращения повторных лайков
    __table_args__ = (db.UniqueConstraint('liker_id', 'liked_id', name='unique_like'),)
    
    # Связи
    liker = db.relationship('User', foreign_keys=[liker_id], backref='likes_given')
    liked = db.relationship('User', foreign_keys=[liked_id], backref='likes_received')

# Модель для мэтчей (взаимных лайков)
class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Уникальный индекс для предотвращения дублирования мэтчей
    __table_args__ = (db.UniqueConstraint('user1_id', 'user2_id', name='unique_match'),)
    
    # Связи
    user1 = db.relationship('User', foreign_keys=[user1_id], backref='matches_as_user1')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='matches_as_user2')

# Модель для сообщений
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

# Формы
class RegistrationForm(FlaskForm):
    username = StringField('Имя', validators=[validators.DataRequired(), validators.Length(min=2, max=50)])
    email = StringField('Email', validators=[validators.DataRequired(), validators.Email()])
    password = PasswordField('Пароль', validators=[validators.DataRequired(), validators.Length(min=6)])
    password2 = PasswordField('Повторите пароль', validators=[validators.DataRequired(), validators.EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

class LoginForm(FlaskForm):
    username = StringField('Email или имя пользователя', validators=[validators.DataRequired()])
    password = PasswordField('Пароль', validators=[validators.DataRequired()])
    submit = SubmitField('Войти')

class StudentProfileForm(FlaskForm):
    full_name = StringField('Полное имя', validators=[validators.DataRequired(), validators.Length(min=2, max=100)])
    university = StringField('Университет', validators=[validators.DataRequired(), validators.Length(min=2, max=100)])
    faculty = StringField('Факультет', validators=[validators.DataRequired(), validators.Length(min=2, max=100)])
    course = SelectField('Курс', choices=[(1, '1 курс'), (2, '2 курс'), (3, '3 курс'), (4, '4 курс'), (5, '5 курс'), (6, '6 курс')], coerce=int, validators=[validators.DataRequired()])
    
    subjects = TextAreaField('Предметы (через запятую)', validators=[validators.DataRequired()], render_kw={"placeholder": "Математика, Физика, Программирование"})
    interests = TextAreaField('Интересы (через запятую)', validators=[validators.DataRequired()], render_kw={"placeholder": "ИИ, Веб-разработка, Анализ данных"})
    
    description = TextAreaField('О себе', validators=[validators.DataRequired()], render_kw={"placeholder": "Расскажите о себе, своих целях и интересах"})
    goals = TextAreaField('Цели обучения', validators=[validators.DataRequired()], render_kw={"placeholder": "Что хотите изучать вместе с партнером?"})
    
    preferred_subjects = TextAreaField('Интересующие предметы у партнера (через запятую)', render_kw={"placeholder": "Математика, Физика"})
    preferred_course = SelectField('Предпочтительный курс партнера', choices=[('any', 'Любой'), ('1-2', '1-2 курс'), ('3-4', '3-4 курс'), ('5-6', '5-6 курс')])
    
    telegram = StringField('Telegram (опционально)', render_kw={"placeholder": "@username"})
    discord = StringField('Discord (опционально)', render_kw={"placeholder": "username#1234"})
    
    photo = FileField('Фото профиля (опционально)', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Только изображения!')])
    
    submit = SubmitField('Сохранить профиль')

class MessageForm(FlaskForm):
    content = TextAreaField('Сообщение', validators=[validators.DataRequired(), validators.Length(min=1, max=1000)], render_kw={"placeholder": "Напишите сообщение...", "rows": 3})
    submit = SubmitField('Отправить')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def is_admin(user):
    return bool(user and user.username and user.username.lower() in ADMIN_USERNAMES)


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated or not is_admin(current_user):
            flash('Доступ только для администраторов.', 'error')
            return redirect(url_for('index'))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.context_processor
def inject_role_flags():
    return {
        'current_user_is_admin': current_user.is_authenticated and is_admin(current_user)
    }


def is_oauth_provider_enabled(provider):
    if not oauth:
        return False
    if provider == 'google':
        return bool(google_oauth and app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET'))
    if provider == 'github':
        return bool(github_oauth and app.config.get('GITHUB_CLIENT_ID') and app.config.get('GITHUB_CLIENT_SECRET'))
    return False


def normalize_email(value):
    return (value or '').strip().lower()


def find_user_by_email(email):
    normalized = normalize_email(email)
    if not normalized:
        return None
    return User.query.filter(func.lower(User.email) == normalized).first()


def generate_unique_username(seed):
    base = re.sub(r'[^a-zA-Z0-9_]+', '_', (seed or '').strip().lower()).strip('_')
    if not base:
        base = 'student'
    base = base[:40]
    candidate = base
    counter = 1
    while User.query.filter_by(username=candidate).first():
        suffix = f"_{counter}"
        trimmed = base[: max(1, 50 - len(suffix))]
        candidate = f"{trimmed}{suffix}"
        counter += 1
    return candidate


def get_or_create_oauth_user(email, username_hint):
    normalized_email = normalize_email(email)
    user = find_user_by_email(normalized_email)
    if user:
        return user, False

    username = generate_unique_username(username_hint or normalized_email.split('@')[0])
    user = User(username=username, email=normalized_email)
    user.set_password(token_urlsafe(32))
    db.session.add(user)
    db.session.commit()
    return user, True

# Функции для работы с файлами
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_profile_photo(file, user_id):
    if file and file.filename and allowed_file(file.filename):
        try:
            # Создаем уникальное имя файла
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"profile_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}{ext}"
            
            # Убеждаемся, что папка существует
            upload_folder = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            
            # Сохраняем файл
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            # Проверяем, что файл действительно сохранился
            if not os.path.exists(filepath):
                print(f"Ошибка: файл не был сохранен в {filepath}")
                return None
            
            # Оптимизируем изображение
            try:
                with Image.open(filepath) as img:
                    # Изменяем размер до максимум 400x400
                    img.thumbnail((400, 400), Image.Resampling.LANCZOS)
                    img.save(filepath, optimize=True, quality=85)
                print(f"Фото успешно сохранено: {filename}")
            except Exception as e:
                print(f"Ошибка при оптимизации изображения: {e}")
                # Файл все равно сохраняем, даже если оптимизация не удалась
            
            return filename
        except Exception as e:
            print(f"Ошибка при сохранении фото: {e}")
            return None
    else:
        print(f"Файл не подходит: file={file}, filename={file.filename if file else 'None'}")
    return None

def delete_profile_photo(filename):
    if filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)

def get_next_profile_for_user(user_id):
    """Получает следующий профиль для просмотра пользователем"""
    # Получаем ID пользователей, которых уже лайкал/дизлайкал текущий пользователь
    liked_user_ids = db.session.query(Like.liked_id).filter_by(liker_id=user_id).subquery()
    
    # Получаем следующий профиль, который еще не был оценен
    next_profile = StudentProfile.query.filter(
        StudentProfile.is_active == True,
        StudentProfile.user_id != user_id,
        ~StudentProfile.user_id.in_(liked_user_ids)
    ).first()
    
    return next_profile

# Маршруты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Проверяем, не существует ли пользователь
        if User.query.filter_by(username=form.username.data).first():
            flash('Пользователь с таким именем уже существует', 'error')
            return render_template('register.html', form=form)
        
        if User.query.filter_by(email=form.email.data).first():
            flash('Пользователь с таким email уже существует', 'error')
            return render_template('register.html', form=form)
        
        # Создаем нового пользователя
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация прошла успешно! Теперь вы можете войти в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.username.data.strip()
        if '@' in identifier:
            user = User.query.filter_by(email=identifier).first()
        else:
            user = User.query.filter_by(username=identifier).first()
        
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Вы успешно вошли в систему!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('login.html', form=form)


@app.route('/auth/google')
def auth_google():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if not is_oauth_provider_enabled('google'):
        flash('Вход через Google пока не настроен. Обратитесь к администратору.', 'info')
        return redirect(url_for('login'))

    try:
        redirect_uri = app.config.get('GOOGLE_CALLBACK_URL') or url_for('auth_google_callback', _external=True)
        return google_oauth.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"Google OAuth start error: {e}")
        flash('Не удалось начать вход через Google. Попробуйте позже.', 'error')
        return redirect(url_for('login'))


@app.route('/auth/google/callback')
def auth_google_callback():
    if not is_oauth_provider_enabled('google'):
        flash('Вход через Google пока не настроен.', 'info')
        return redirect(url_for('login'))

    try:
        token = google_oauth.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = google_oauth.get('userinfo').json()
    except Exception as e:
        print(f"Google OAuth callback error: {e}")
        flash('Ошибка авторизации через Google.', 'error')
        return redirect(url_for('login'))

    email = normalize_email((user_info or {}).get('email'))
    email_verified = (user_info or {}).get('email_verified')
    if not email:
        flash('Google не вернул email. Проверьте настройки аккаунта.', 'error')
        return redirect(url_for('login'))
    if email_verified is False:
        flash('Подтвердите email в Google и попробуйте снова.', 'error')
        return redirect(url_for('login'))

    username_hint = (user_info or {}).get('name') or (user_info or {}).get('given_name') or email.split('@')[0]
    user, created = get_or_create_oauth_user(email, username_hint)
    login_user(user)
    flash('Аккаунт создан через Google.' if created else 'Вы успешно вошли через Google.', 'success')
    return redirect(url_for('index'))


@app.route('/auth/github')
def auth_github():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if not is_oauth_provider_enabled('github'):
        flash('Вход через GitHub пока не настроен. Обратитесь к администратору.', 'info')
        return redirect(url_for('login'))

    try:
        redirect_uri = app.config.get('GITHUB_CALLBACK_URL') or url_for('auth_github_callback', _external=True)
        return github_oauth.authorize_redirect(redirect_uri)
    except Exception as e:
        print(f"GitHub OAuth start error: {e}")
        flash('Не удалось начать вход через GitHub. Попробуйте позже.', 'error')
        return redirect(url_for('login'))


@app.route('/auth/github/callback')
def auth_github_callback():
    if not is_oauth_provider_enabled('github'):
        flash('Вход через GitHub пока не настроен.', 'info')
        return redirect(url_for('login'))

    try:
        github_oauth.authorize_access_token()
        profile = github_oauth.get('user').json()
    except Exception as e:
        print(f"GitHub OAuth callback error: {e}")
        flash('Ошибка авторизации через GitHub.', 'error')
        return redirect(url_for('login'))

    email = normalize_email((profile or {}).get('email'))
    if not email:
        try:
            emails = github_oauth.get('user/emails').json()
            if isinstance(emails, list):
                chosen = None
                for item in emails:
                    if item.get('email') and item.get('verified') and item.get('primary'):
                        chosen = item.get('email')
                        break
                if not chosen:
                    for item in emails:
                        if item.get('email') and item.get('verified'):
                            chosen = item.get('email')
                            break
                if not chosen and emails:
                    chosen = emails[0].get('email')
                email = normalize_email(chosen)
        except Exception as e:
            print(f"GitHub email fetch error: {e}")

    if not email:
        flash('GitHub не вернул email. Включите публичный email или подтверждённый primary email.', 'error')
        return redirect(url_for('login'))

    username_hint = (profile or {}).get('login') or (profile or {}).get('name') or email.split('@')[0]
    user, created = get_or_create_oauth_user(email, username_hint)
    login_user(user)
    flash('Аккаунт создан через GitHub.' if created else 'Вы успешно вошли через GitHub.', 'success')
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/create-profile', methods=['GET', 'POST'])
@login_required
def create_profile():
    # Проверяем, есть ли уже профиль
    if current_user.profile:
        flash('У вас уже есть профиль. Вы можете его редактировать.', 'info')
        return redirect(url_for('edit_profile'))
    
    form = StudentProfileForm()
    print(f"=== СОЗДАНИЕ ПРОФИЛЯ ===")
    print(f"validate_on_submit = {form.validate_on_submit()}")
    print(f"Файл в форме: {form.photo.data}")
    print(f"Имя файла: {form.photo.data.filename if form.photo.data else 'None'}")
    print(f"Content-Type: {request.content_type}")
    print(f"Files в запросе: {request.files}")
    print(f"Form в запросе: {request.form}")
    
    if not form.validate_on_submit():
        print(f"Ошибки валидации формы: {form.errors}")
    if form.validate_on_submit():
        # Обрабатываем загрузку фото
        photo_filename = None
        if form.photo.data:
            print(f"Загружается фото: {form.photo.data.filename}")
            photo_filename = save_profile_photo(form.photo.data, current_user.id)
            print(f"Результат загрузки фото: {photo_filename}")
        
        profile = StudentProfile(
            user_id=current_user.id,
            full_name=form.full_name.data,
            university=form.university.data,
            faculty=form.faculty.data,
            course=form.course.data,
            subjects=form.subjects.data,
            interests=form.interests.data,
            description=form.description.data,
            goals=form.goals.data,
            preferred_subjects=form.preferred_subjects.data,
            preferred_course=form.preferred_course.data,
            telegram=form.telegram.data,
            discord=form.discord.data,
            photo_filename=photo_filename
        )
        
        print(f"Создается профиль с фото: {photo_filename}")
        
        db.session.add(profile)
        db.session.commit()
        
        print(f"Профиль сохранен в БД. ID: {profile.id}, фото: {profile.photo_filename}")
        
        flash('Профиль успешно создан! Теперь вы можете искать партнеров для учебы.', 'success')
        return redirect(url_for('tinder'))
    
    return render_template('create_profile.html', form=form)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    form = StudentProfileForm(obj=current_user.profile)
    print(f"=== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ===")
    print(f"validate_on_submit = {form.validate_on_submit()}")
    print(f"Файл в форме: {form.photo.data}")
    print(f"Имя файла: {form.photo.data.filename if form.photo.data else 'None'}")
    print(f"Content-Type: {request.content_type}")
    print(f"Files в запросе: {request.files}")
    print(f"Form в запросе: {request.form}")
    
    if not form.validate_on_submit():
        print(f"Ошибки валидации формы: {form.errors}")
    if form.validate_on_submit():
        profile = current_user.profile
        
        # Обрабатываем загрузку нового фото
        if form.photo.data:
            print(f"Загружается новое фото: {form.photo.data.filename}")
            # Удаляем старое фото
            if profile.photo_filename:
                delete_profile_photo(profile.photo_filename)
            
            # Сохраняем новое фото
            photo_filename = save_profile_photo(form.photo.data, current_user.id)
            print(f"Результат загрузки нового фото: {photo_filename}")
            if photo_filename:
                profile.photo_filename = photo_filename
        
        profile.full_name = form.full_name.data
        profile.university = form.university.data
        profile.faculty = form.faculty.data
        profile.course = form.course.data
        profile.subjects = form.subjects.data
        profile.interests = form.interests.data
        profile.description = form.description.data
        profile.goals = form.goals.data
        profile.preferred_subjects = form.preferred_subjects.data
        profile.preferred_course = form.preferred_course.data
        profile.telegram = form.telegram.data
        profile.discord = form.discord.data
        profile.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"Профиль обновлен в БД. ID: {profile.id}, фото: {profile.photo_filename}")
        
        flash('Профиль успешно обновлен!', 'success')
        return redirect(url_for('my_profile'))
    
    return render_template('edit_profile.html', form=form, profile=current_user.profile)

@app.route('/my-profile')
@login_required
def my_profile():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    return render_template('my_profile.html', profile=current_user.profile)

@app.route('/search-partners')
@login_required
def search_partners():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    # Получаем всех активных студентов, кроме текущего пользователя
    profiles = StudentProfile.query.filter(
        StudentProfile.is_active == True,
        StudentProfile.user_id != current_user.id
    ).all()
    
    return render_template('search_partners.html', profiles=profiles)

@app.route('/tinder')
@login_required
def tinder():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    # Получаем следующий профиль для просмотра
    next_profile = get_next_profile_for_user(current_user.id)
    
    if not next_profile:
        return render_template('tinder.html', profile=None, no_more_profiles=True)
    
    return render_template('tinder.html', profile=next_profile, no_more_profiles=False)

@app.route('/like/<int:profile_id>', methods=['POST'])
@login_required
def like_profile(profile_id):
    if not current_user.profile:
        return {'error': 'Профиль не создан'}, 400
    
    # Проверяем, что профиль существует и активен
    target_profile = StudentProfile.query.filter_by(id=profile_id, is_active=True).first()
    if not target_profile:
        return {'error': 'Профиль не найден'}, 404
    
    # Проверяем, что пользователь не лайкает сам себя
    if target_profile.user_id == current_user.id:
        return {'error': 'Нельзя лайкать самого себя'}, 400
    
    # Проверяем, не лайкал ли уже этот профиль
    existing_like = Like.query.filter_by(
        liker_id=current_user.id,
        liked_id=target_profile.user_id
    ).first()
    
    if existing_like:
        return {'error': 'Уже лайкали этого пользователя'}, 400
    
    # Создаем лайк
    like = Like(
        liker_id=current_user.id,
        liked_id=target_profile.user_id,
        is_like=True
    )
    db.session.add(like)
    
    # Проверяем, есть ли взаимный лайк
    mutual_like = Like.query.filter_by(
        liker_id=target_profile.user_id,
        liked_id=current_user.id,
        is_like=True
    ).first()
    
    is_match = False
    if mutual_like:
        # Создаем мэтч
        match = Match(
            user1_id=min(current_user.id, target_profile.user_id),
            user2_id=max(current_user.id, target_profile.user_id)
        )
        db.session.add(match)
        is_match = True
    
    db.session.commit()
    
    return {
        'success': True,
        'is_match': is_match,
        'match_name': target_profile.full_name if is_match else None
    }

@app.route('/dislike/<int:profile_id>', methods=['POST'])
@login_required
def dislike_profile(profile_id):
    if not current_user.profile:
        return {'error': 'Профиль не создан'}, 400
    
    # Проверяем, что профиль существует и активен
    target_profile = StudentProfile.query.filter_by(id=profile_id, is_active=True).first()
    if not target_profile:
        return {'error': 'Профиль не найден'}, 404
    
    # Проверяем, что пользователь не дизлайкает сам себя
    if target_profile.user_id == current_user.id:
        return {'error': 'Нельзя дизлайкать самого себя'}, 400
    
    # Проверяем, не лайкал ли уже этот профиль
    existing_like = Like.query.filter_by(
        liker_id=current_user.id,
        liked_id=target_profile.user_id
    ).first()
    
    if existing_like:
        return {'error': 'Уже лайкали этого пользователя'}, 400
    
    # Создаем дизлайк
    dislike = Like(
        liker_id=current_user.id,
        liked_id=target_profile.user_id,
        is_like=False
    )
    db.session.add(dislike)
    db.session.commit()
    
    return {'success': True}

@app.route('/matches')
@login_required
def matches():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    # Получаем все мэтчи текущего пользователя
    user_matches = db.session.query(Match).filter(
        (Match.user1_id == current_user.id) | (Match.user2_id == current_user.id)
    ).all()
    
    # Получаем профили мэтчей + краткую информацию по переписке
    match_profiles = []
    for match in user_matches:
        other_user_id = match.user2_id if match.user1_id == current_user.id else match.user1_id
        other_profile = StudentProfile.query.filter_by(user_id=other_user_id).first()
        if other_profile:
            # Последнее сообщение в чате с этим пользователем
            last_message = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user_id)) |
                ((Message.sender_id == other_user_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.created_at.desc()).first()

            # Есть ли непрочитанные сообщения от собеседника
            has_unread = Message.query.filter(
                Message.sender_id == other_user_id,
                Message.receiver_id == current_user.id,
                Message.is_read == False
            ).count() > 0

            match_profiles.append({
                'profile': other_profile,
                'match_date': match.created_at,
                'last_message': last_message.content if last_message else None,
                'last_message_time': last_message.created_at.strftime('%H:%M') if last_message else None,
                'has_unread': has_unread
            })
    
    # Количество мэтчей с непрочитанными сообщениями
    new_matches_count = sum(1 for m in match_profiles if m['has_unread'])
    
    return render_template('matches.html', matches=match_profiles, new_matches_count=new_matches_count)


@app.route('/likes')
@login_required
def likes():
    """Список пользователей, которые поставили лайк текущему пользователю"""
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))

    # Входящие лайки
    likes_query = (
        db.session.query(Like, User, StudentProfile)
        .join(User, User.id == Like.liker_id)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .filter(Like.liked_id == current_user.id, Like.is_like == True)
        .order_by(Like.created_at.desc())
        .all()
    )

    likes_data = []
    for like, user, profile in likes_query:
        # Проверяем, стал ли лайк взаимным (есть ли уже мэтч)
        is_match = db.session.query(Match).filter(
            ((Match.user1_id == current_user.id) & (Match.user2_id == user.id)) |
            ((Match.user1_id == user.id) & (Match.user2_id == current_user.id))
        ).first() is not None

        # Показываем здесь только невзаимные лайки
        if is_match:
            continue

        likes_data.append(
            {
                'user': user,
                'profile': profile,
                'created_at': like.created_at,
                'is_match': is_match,
            }
        )

    return render_template('likes.html', likes=likes_data)

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    """Страница чата с конкретным пользователем"""
    try:
        print(f"=== ОТКРЫТИЕ ЧАТА ===")
        print(f"Текущий пользователь: {current_user.id}")
        print(f"ID собеседника: {user_id}")
        
        if not current_user.profile:
            print("Ошибка: у пользователя нет профиля")
            flash('Сначала создайте профиль.', 'info')
            return redirect(url_for('create_profile'))
        
        # Проверяем, что пользователи являются мэтчами
        print("Поиск мэтча...")
        match = Match.query.filter(
            ((Match.user1_id == current_user.id) & (Match.user2_id == user_id)) |
            ((Match.user1_id == user_id) & (Match.user2_id == current_user.id))
        ).first()
        
        print(f"Найден мэтч: {match}")
        if not match:
            print("Ошибка: мэтч не найден")
            flash('Вы можете общаться только с вашими мэтчами.', 'error')
            return redirect(url_for('matches'))
        
        # Получаем профиль собеседника
        print("Поиск пользователя...")
        other_user = User.query.get_or_404(user_id)
        print(f"Найден пользователь: {other_user.username}")
        
        if not other_user.profile:
            print("Ошибка: у собеседника нет профиля")
            flash('Профиль собеседника не найден.', 'error')
            return redirect(url_for('matches'))
    
        # Получаем сообщения между пользователями
        print("Получение сообщений...")
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
            ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at.asc()).all()
        
        print(f"Найдено сообщений: {len(messages)}")
        
        # Отмечаем сообщения как прочитанные
        for message in messages:
            if message.receiver_id == current_user.id and not message.is_read:
                message.is_read = True
        db.session.commit()
        
        form = MessageForm()
        
        print("Рендеринг шаблона чата...")
        return render_template('chat.html', 
                             other_user=other_user, 
                             messages=messages, 
                             form=form)
    
    except Exception as e:
        print(f"Ошибка в функции chat: {e}")
        import traceback
        traceback.print_exc()
        flash('Произошла ошибка при открытии чата.', 'error')
        return redirect(url_for('matches'))

@app.route('/send-message/<int:receiver_id>', methods=['POST'])
@login_required
def send_message(receiver_id):
    """Отправка сообщения"""
    if not current_user.profile:
        return {'error': 'Профиль не создан'}, 400
    
    # Проверяем, что пользователи являются мэтчами
    match = Match.query.filter(
        ((Match.user1_id == current_user.id) & (Match.user2_id == receiver_id)) |
        ((Match.user1_id == receiver_id) & (Match.user2_id == current_user.id))
    ).first()
    
    if not match:
        return {'error': 'Вы можете общаться только с вашими мэтчами'}, 403
    
    form = MessageForm()
    if form.validate_on_submit():
        message = Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=form.content.data
        )
        
        db.session.add(message)
        db.session.commit()
        
        return {
            'success': True,
            'message_id': message.id,
            'created_at': message.created_at.strftime('%H:%M')
        }
    else:
        return {'error': 'Ошибка валидации формы', 'errors': form.errors}, 400

@app.route('/get-messages/<int:user_id>')
@login_required
def get_messages(user_id):
    """Получение новых сообщений"""
    if not current_user.profile:
        return {'error': 'Профиль не создан'}, 400
    
    # Получаем непрочитанные сообщения
    messages = Message.query.filter(
        Message.sender_id == user_id,
        Message.receiver_id == current_user.id,
        Message.is_read == False
    ).order_by(Message.created_at.asc()).all()
    
    # Отмечаем как прочитанные
    for message in messages:
        message.is_read = True
    db.session.commit()
    
    # Форматируем сообщения для JSON
    messages_data = []
    for message in messages:
        messages_data.append({
            'id': message.id,
            'content': message.content,
            'created_at': message.created_at.strftime('%H:%M'),
            'sender_name': message.sender.profile.full_name if message.sender.profile else message.sender.username
        })
    
    return {'messages': messages_data}


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_profiles = StudentProfile.query.count()
    total_active_profiles = StudentProfile.query.filter_by(is_active=True).count()
    total_matches = Match.query.count()
    total_messages = Message.query.count()

    latest_users = User.query.order_by(User.created_at.desc()).limit(8).all()
    latest_profiles = StudentProfile.query.order_by(StudentProfile.created_at.desc()).limit(8).all()

    return render_template(
        'admin/dashboard.html',
        stats={
            'total_users': total_users,
            'total_profiles': total_profiles,
            'total_active_profiles': total_active_profiles,
            'total_matches': total_matches,
            'total_messages': total_messages,
        },
        latest_users=latest_users,
        latest_profiles=latest_profiles,
    )


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if current_user.id == user_id:
        flash('Нельзя удалить собственный аккаунт администратора.', 'error')
        return redirect(url_for('admin_users'))

    user = User.query.get_or_404(user_id)

    if user.profile and user.profile.photo_filename:
        delete_profile_photo(user.profile.photo_filename)

    Like.query.filter(or_(Like.liker_id == user_id, Like.liked_id == user_id)).delete(synchronize_session=False)
    Match.query.filter(or_(Match.user1_id == user_id, Match.user2_id == user_id)).delete(synchronize_session=False)
    Message.query.filter(or_(Message.sender_id == user_id, Message.receiver_id == user_id)).delete(synchronize_session=False)

    db.session.delete(user)
    db.session.commit()

    flash('Пользователь удален.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/messages')
@login_required
@admin_required
def admin_messages():
    messages = (
        Message.query
        .order_by(Message.created_at.desc())
        .limit(200)
        .all()
    )
    return render_template('admin/messages.html', messages=messages)

@app.route('/profile/<int:profile_id>')
@login_required
def view_profile(profile_id):
    profile = StudentProfile.query.get_or_404(profile_id)
    if not profile.is_active:
        flash('Профиль неактивен.', 'error')
        return redirect(url_for('tinder'))
    
    return render_template('view_profile.html', profile=profile)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        filepath = os.path.join(upload_folder, filename)
        
        # Проверяем, что файл существует
        if not os.path.exists(filepath):
            print(f"Файл не найден: {filepath}")
            return "Файл не найден", 404
        
        return send_from_directory(upload_folder, filename)
    except Exception as e:
        print(f"Ошибка при загрузке файла {filename}: {e}")
        return "Ошибка загрузки файла", 500

@app.route('/test-upload', methods=['GET', 'POST'])
def test_upload():
    """Тестовый маршрут для проверки загрузки файлов"""
    if request.method == 'POST':
        try:
            print("=== ТЕСТ ЗАГРУЗКИ ФАЙЛА ===")
            print(f"Content-Type: {request.content_type}")
            print(f"Files: {request.files}")
            print(f"Form: {request.form}")
            print(f"UPLOAD_FOLDER: {app.config['UPLOAD_FOLDER']}")
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            # Проверим права на запись
            test_path = os.path.join(app.config['UPLOAD_FOLDER'], '.write_test')
            with open(test_path, 'w') as f:
                f.write('ok')
            os.remove(test_path)
            
            if 'file' in request.files:
                file = request.files['file']
                print(f"Файл получен: {file.filename}")
                
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"test_{filename}")
                    file.save(filepath)
                    print(f"Файл сохранен: {filepath}")
                    return f"Файл сохранен: {filepath}"
                else:
                    return "Файл не получен"
            else:
                return "Поле 'file' не найдено в запросе"
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"ОШИБКА В /test-upload: {e}\n{tb}")
            return f"Ошибка: {e}\n{tb}", 500
    
    return '''
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file">
        <input type="submit" value="Загрузить">
    </form>
    '''

@app.route('/test-upload-perms')
def test_upload_perms():
    """Быстрый тест прав записи в папку загрузок"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        test_file = os.path.join(upload_folder, '.perm_test')
        with open(test_file, 'w') as f:
            f.write('ok')
        os.remove(test_file)
        return f"OK: запись в {upload_folder} работает"
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"ОШИБКА ПРАВ: {e}\n{tb}")
        return f"Ошибка прав/каталога в {app.config['UPLOAD_FOLDER']}: {e}\n{tb}", 500

@app.route('/test-profile-form', methods=['GET', 'POST'])
@login_required
def test_profile_form():
    """Тестовый маршрут для проверки формы профиля"""
    if request.method == 'POST':
        print("=== ТЕСТ ФОРМЫ ПРОФИЛЯ ===")
        print(f"Content-Type: {request.content_type}")
        print(f"Files: {request.files}")
        print(f"Form: {request.form}")
        
        form = StudentProfileForm()
        print(f"validate_on_submit = {form.validate_on_submit()}")
        print(f"Файл в форме: {form.photo.data}")
        print(f"Ошибки: {form.errors}")
        
        if form.validate_on_submit():
            if form.photo.data:
                print(f"Файл получен: {form.photo.data.filename}")
                filename = save_profile_photo(form.photo.data, current_user.id)
                return f"Файл сохранен: {filename}"
            else:
                return "Файл не получен"
        else:
            return f"Ошибки валидации: {form.errors}"
    
    return '''
    <form method="post" enctype="multipart/form-data">
        {{ csrf_token() }}
        <input type="file" name="photo">
        <input type="submit" value="Загрузить фото">
    </form>
    '''

# Создание таблиц при первом запуске
def create_tables():
    with app.app_context():
        db.create_all()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="127.0.0.1", port=5000, debug=True)
