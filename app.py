from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, IntegerField, BooleanField, validators
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import re
from secrets import token_urlsafe
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image
from sqlalchemy import or_, func

from profanity import contains_profanity

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
def normalize_database_url(url):
    """Нормализует URL БД для SQLAlchemy (postgres:// -> postgresql+psycopg2://)."""
    if not url:
        return url
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql+psycopg2://', 1)
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    return url


_default_uri = 'postgresql+psycopg2://postgres:postgres@localhost:5432/tinder'
app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(
    os.environ.get('DATABASE_URL', _default_uri)
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True
}

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
    # scrypt/pbkdf2/bcrypt хэши длиннее 120 символов (Werkzeug 3 по умолчанию — scrypt)
    password_hash = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Активность (для «онлайн» в поиске)
    last_seen_at = db.Column(db.DateTime, nullable=True)

    # Блокировки за мат в личных/групповых чатах (3 попытки → бан 1ч, затем 3, 8, 12, 24ч)
    profanity_strike_count = db.Column(db.Integer, default=0, nullable=False)
    profanity_ban_tier = db.Column(db.Integer, default=0, nullable=False)
    profanity_blocked_until = db.Column(db.DateTime, nullable=True)
    
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
    city = db.Column(db.String(100), nullable=True)

    # Предметы и интересы
    subjects = db.Column(db.Text)  # JSON строка с предметами
    interests = db.Column(db.Text)  # JSON строка с интересами
    
    # Описание и цели
    description = db.Column(db.Text)
    goals = db.Column(db.Text)
    
    # Предпочтения по партнеру
    preferred_subjects = db.Column(db.Text)  # JSON строка
    preferred_course = db.Column(db.String(50))  # например "1-3" или "4-6"
    preferred_city = db.Column(db.String(100))  # город партнёра
    prefer_photo_only = db.Column(db.Boolean, default=False)  # только с фото

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


class StudyGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    meeting_format = db.Column(db.String(20), nullable=False, default='online')
    city = db.Column(db.String(100))
    max_members = db.Column(db.Integer)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref='created_study_groups', foreign_keys=[creator_id])
    memberships = db.relationship('StudyGroupMembership', backref='group', cascade='all, delete-orphan', lazy='dynamic')
    messages = db.relationship('StudyGroupMessage', backref='group', cascade='all, delete-orphan', lazy='dynamic')


class StudyGroupMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('study_group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='study_group_memberships')
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id', name='unique_group_member'),)


class StudyGroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('study_group.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', backref='study_group_messages')


PROFANITY_MSG = 'Недопустимая лексика. Уберите ненормативные выражения.'

# Чаты: после 3-х попыток с матом — бан; длительности по очереди (часы)
PROFANITY_CHAT_STRIKES_LIMIT = 3
PROFANITY_CHAT_BAN_HOURS = [1, 3, 8, 12, 24]

# Окно «онлайн» для фильтра поиска (последняя активность)
ONLINE_WINDOW_MINUTES = 5


def is_user_profanity_chat_blocked(user):
    """Пользователь не может писать в личку/группы из-за активной блокировки за мат."""
    until = getattr(user, 'profanity_blocked_until', None)
    if not until:
        return False
    return datetime.utcnow() < until


def format_profanity_chat_blocked_message(user):
    """Текст, если блокировка уже действует."""
    until = user.profanity_blocked_until
    if not until:
        return 'Вы временно не можете отправлять сообщения.'
    return (
        'Вы временно не можете отправлять сообщения из-за нарушений правил. '
        f'Ограничение действует до {until.strftime("%d.%m.%Y %H:%M")} UTC.'
    )


def register_chat_profanity_violation(user):
    """
    Учесть попытку отправить мат в чате. Каждые 3 попытки — бан на следующий срок из PROFANITY_CHAT_BAN_HOURS.
    Возвращает dict: banned (bool), hours (int|None), strikes (int после инкремента).
    """
    user.profanity_strike_count = (user.profanity_strike_count or 0) + 1
    strikes = user.profanity_strike_count
    result = {'banned': False, 'hours': None, 'strikes': strikes}

    if strikes >= PROFANITY_CHAT_STRIKES_LIMIT:
        tier_idx = min(user.profanity_ban_tier or 0, len(PROFANITY_CHAT_BAN_HOURS) - 1)
        hours = PROFANITY_CHAT_BAN_HOURS[tier_idx]
        user.profanity_blocked_until = datetime.utcnow() + timedelta(hours=hours)
        user.profanity_ban_tier = (user.profanity_ban_tier or 0) + 1
        user.profanity_strike_count = 0
        result['banned'] = True
        result['hours'] = hours
        result['strikes'] = 0
    db.session.commit()
    return result


def format_new_chat_ban_message(hours):
    return (
        f'Вы заблокированы на {hours} ч. за повторные нарушения (ненормативная лексика в чатах). '
        'Дальнейшие нарушения увеличивают срок блокировки.'
    )


class NoProfanity:
    """WTForms: запрет ненормативной лексики в поле."""

    def __init__(self, message=None):
        self.message = message or PROFANITY_MSG

    def __call__(self, form, field):
        if field.data is None:
            return
        if contains_profanity(str(field.data)):
            raise validators.ValidationError(self.message)


# Формы
class RegistrationForm(FlaskForm):
    username = StringField(
        'Имя',
        validators=[
            validators.DataRequired(),
            validators.Length(min=2, max=50),
            NoProfanity(),
        ],
    )
    email = StringField('Email', validators=[validators.DataRequired(), validators.Email()])
    password = PasswordField('Пароль', validators=[validators.DataRequired(), validators.Length(min=6)])
    password2 = PasswordField('Повторите пароль', validators=[validators.DataRequired(), validators.EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

class LoginForm(FlaskForm):
    username = StringField('Email или имя пользователя', validators=[validators.DataRequired()])
    password = PasswordField('Пароль', validators=[validators.DataRequired()])
    submit = SubmitField('Войти')

class StudentProfileForm(FlaskForm):
    full_name = StringField(
        'Полное имя',
        validators=[validators.DataRequired(), validators.Length(min=2, max=100), NoProfanity()],
    )
    university = StringField(
        'Университет',
        validators=[validators.DataRequired(), validators.Length(min=2, max=100), NoProfanity()],
    )
    faculty = StringField(
        'Факультет',
        validators=[validators.DataRequired(), validators.Length(min=2, max=100), NoProfanity()],
    )
    city = StringField(
        'Город',
        validators=[validators.Optional(), validators.Length(max=100), NoProfanity()],
        render_kw={"placeholder": "Москва, Санкт-Петербург..."},
    )
    course = SelectField('Курс', choices=[(1, '1 курс'), (2, '2 курс'), (3, '3 курс'), (4, '4 курс'), (5, '5 курс'), (6, '6 курс')], coerce=int, validators=[validators.DataRequired()])
    
    subjects = TextAreaField(
        'Предметы (через запятую)',
        validators=[validators.DataRequired(), NoProfanity()],
        render_kw={"placeholder": "Математика, Физика, Программирование"},
    )
    interests = TextAreaField(
        'Интересы (через запятую)',
        validators=[validators.DataRequired(), NoProfanity()],
        render_kw={"placeholder": "ИИ, Веб-разработка, Анализ данных"},
    )

    description = TextAreaField(
        'О себе',
        validators=[validators.DataRequired(), NoProfanity()],
        render_kw={"placeholder": "Расскажите о себе, своих целях и интересах"},
    )
    goals = TextAreaField(
        'Цели обучения',
        validators=[validators.DataRequired(), NoProfanity()],
        render_kw={"placeholder": "Что хотите изучать вместе с партнером?"},
    )

    preferred_subjects = TextAreaField(
        'Интересующие предметы у партнера (через запятую)',
        validators=[validators.Optional(), NoProfanity()],
        render_kw={"placeholder": "Математика, Физика"},
    )
    preferred_course = SelectField('Предпочтительный курс партнера', choices=[('any', 'Любой'), ('1-2', '1-2 курс'), ('3-4', '3-4 курс'), ('5-6', '5-6 курс')])

    preferred_city = StringField(
        'Предпочтительный город партнера',
        validators=[validators.Optional(), validators.Length(max=100), NoProfanity()],
        render_kw={"placeholder": "Москва, Санкт-Петербург..."},
    )
    prefer_photo_only = BooleanField('Только партнёры с фото')

    telegram = StringField(
        'Telegram (опционально)',
        validators=[validators.Optional(), NoProfanity()],
        render_kw={"placeholder": "@username"},
    )
    discord = StringField(
        'Discord (опционально)',
        validators=[validators.Optional(), NoProfanity()],
        render_kw={"placeholder": "username#1234"},
    )
    
    photo = FileField('Фото профиля (опционально)', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Только изображения!')])
    
    submit = SubmitField('Сохранить профиль')

class MessageForm(FlaskForm):
    # Мат в чате обрабатываем вручную (счётчик попыток и баны), без NoProfanity здесь
    content = TextAreaField(
        'Сообщение',
        validators=[validators.DataRequired(), validators.Length(min=1, max=1000)],
        render_kw={"placeholder": "Напишите сообщение...", "rows": 3},
    )
    submit = SubmitField('Отправить')

class StudyGroupForm(FlaskForm):
    title = StringField(
        'Название группы',
        validators=[validators.DataRequired(), validators.Length(min=3, max=120), NoProfanity()],
    )
    subject = StringField(
        'Предмет',
        validators=[validators.DataRequired(), validators.Length(min=2, max=100), NoProfanity()],
    )
    description = TextAreaField(
        'Описание',
        validators=[validators.DataRequired(), validators.Length(min=12, max=1500), NoProfanity()],
        render_kw={"placeholder": "Опишите цель группы, темы и формат занятий", "rows": 4},
    )
    meeting_format = SelectField(
        'Формат встреч',
        choices=[('online', 'Онлайн'), ('offline', 'Очно'), ('hybrid', 'Смешанный')],
        validators=[validators.DataRequired()]
    )
    city = StringField(
        'Город (для очных встреч)',
        validators=[validators.Optional(), validators.Length(max=100), NoProfanity()],
    )
    max_members = IntegerField('Лимит участников (необязательно)', validators=[validators.Optional(), validators.NumberRange(min=2, max=200)])
    submit = SubmitField('Создать группу')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def touch_last_seen():
    """Обновляет last_seen_at не чаще чем раз в ~90 с (меньше нагрузки на БД)."""
    if not current_user.is_authenticated:
        return
    now = datetime.utcnow()
    key = '_last_seen_touch_ts'
    prev = session.get(key)
    if prev:
        try:
            if (now - datetime.fromisoformat(prev)).total_seconds() < 90:
                return
        except Exception:
            pass
    session[key] = now.isoformat()
    session.modified = True
    try:
        User.query.filter_by(id=current_user.id).update({'last_seen_at': now})
        db.session.commit()
    except Exception:
        db.session.rollback()


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


@app.template_global()
def user_is_online_now(user):
    """Онлайн, если last_seen в пределах ONLINE_WINDOW_MINUTES."""
    if not user or not getattr(user, 'last_seen_at', None):
        return False
    return datetime.utcnow() - user.last_seen_at < timedelta(minutes=ONLINE_WINDOW_MINUTES)


def parse_discovery_filters():
    """Параметры поиска из query string: город, курс, предмет, фото, онлайн/офлайн."""
    city = (request.args.get('city') or '').strip() or None
    subject = (request.args.get('subject') or '').strip() or None
    presence = (request.args.get('presence') or '').strip().lower()
    if presence not in ('online', 'offline'):
        presence = None
    course = None
    course_raw = (request.args.get('course') or '').strip()
    if course_raw:
        try:
            ci = int(course_raw)
            if 1 <= ci <= 6:
                course = ci
        except (TypeError, ValueError):
            pass
    photo_only = request.args.get('photo_only') in ('1', 'on', 'true', 'yes')
    return {
        'city': city,
        'subject': subject,
        'course': course,
        'photo_only': photo_only,
        'presence': presence,
    }


def get_profile_preferences(profile):
    """Строит dict фильтров из сохранённых предпочтений профиля пользователя."""
    if not profile:
        return {}
    filters = {
        'city': (getattr(profile, 'preferred_city', None) or '').strip() or None,
        'photo_only': bool(getattr(profile, 'prefer_photo_only', False)),
        'presence': None,
        'course': None,
        'subject': None,
    }

    # preferred_course: 'any', '1-2', '3-4', '5-6' → диапазон
    pc = (profile.preferred_course or '').strip().lower()
    filters['course_range'] = pc if pc and pc != 'any' else None

    # preferred_subjects: через запятую → список
    ps = (profile.preferred_subjects or '').strip()
    filters['subjects_list'] = [s.strip() for s in ps.split(',') if s.strip()] if ps else None

    return filters


def apply_discovery_filters(query, filters):
    """Ограничивает запрос StudentProfile фильтрами поиска."""
    f = filters or {}
    if f.get('city'):
        query = query.filter(StudentProfile.city.ilike('%' + f['city'] + '%'))
    if f.get('course') is not None:
        query = query.filter(StudentProfile.course == f['course'])
    if f.get('subject'):
        query = query.filter(StudentProfile.subjects.ilike('%' + f['subject'] + '%'))
    if f.get('photo_only'):
        query = query.filter(
            StudentProfile.photo_filename.isnot(None),
            StudentProfile.photo_filename != '',
        )
    # Диапазон курса из профильных предпочтений: '1-2' → BETWEEN 1 AND 2
    course_range = f.get('course_range')
    if course_range:
        try:
            parts = course_range.split('-')
            low, high = int(parts[0]), int(parts[1])
            query = query.filter(StudentProfile.course.between(low, high))
        except (ValueError, IndexError):
            pass
    # Несколько предметов из профильных предпочтений: совпадение по любому
    subjects_list = f.get('subjects_list')
    if subjects_list:
        conditions = [StudentProfile.subjects.ilike('%' + s + '%') for s in subjects_list]
        query = query.filter(or_(*conditions))
    presence = f.get('presence')
    if presence in ('online', 'offline'):
        threshold = datetime.utcnow() - timedelta(minutes=ONLINE_WINDOW_MINUTES)
        online_ids = db.session.query(User.id).filter(
            User.last_seen_at.isnot(None),
            User.last_seen_at >= threshold,
        )
        if presence == 'online':
            query = query.filter(StudentProfile.user_id.in_(online_ids))
        else:
            query = query.filter(~StudentProfile.user_id.in_(online_ids))
    return query


MEETING_FORMAT_LABELS = {
    'online': 'Онлайн',
    'offline': 'Очно',
    'hybrid': 'Смешанный',
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

def get_next_profile_for_user(user_id, filters=None):
    """Получает следующий профиль для просмотра пользователем (с учётом фильтров поиска)."""
    liked_user_ids = db.session.query(Like.liked_id).filter_by(liker_id=user_id).subquery()

    q = StudentProfile.query.filter(
        StudentProfile.is_active == True,
        StudentProfile.user_id != user_id,
        ~StudentProfile.user_id.in_(liked_user_ids),
    )
    q = apply_discovery_filters(q, filters or {})
    return q.first()

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
        
        city_val = (form.city.data or '').strip() or None
        profile = StudentProfile(
            user_id=current_user.id,
            full_name=form.full_name.data,
            university=form.university.data,
            faculty=form.faculty.data,
            city=city_val,
            course=form.course.data,
            subjects=form.subjects.data,
            interests=form.interests.data,
            description=form.description.data,
            goals=form.goals.data,
            preferred_subjects=form.preferred_subjects.data,
            preferred_course=form.preferred_course.data,
            preferred_city=(form.preferred_city.data or '').strip() or None,
            prefer_photo_only=bool(form.prefer_photo_only.data),
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
        profile.city = (form.city.data or '').strip() or None
        profile.course = form.course.data
        profile.subjects = form.subjects.data
        profile.interests = form.interests.data
        profile.description = form.description.data
        profile.goals = form.goals.data
        profile.preferred_subjects = form.preferred_subjects.data
        profile.preferred_course = form.preferred_course.data
        profile.preferred_city = (form.preferred_city.data or '').strip() or None
        profile.prefer_photo_only = bool(form.prefer_photo_only.data)
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
    
    filters = parse_discovery_filters()
    q = StudentProfile.query.filter(
        StudentProfile.is_active == True,
        StudentProfile.user_id != current_user.id,
    )
    q = apply_discovery_filters(q, filters)
    profiles = q.all()

    return render_template('search_partners.html', profiles=profiles, filter_values=filters)

@app.route('/tinder')
@login_required
def tinder():
    if not current_user.profile:
        flash('Сначала создайте профиль.', 'info')
        return redirect(url_for('create_profile'))
    
    filters = get_profile_preferences(current_user.profile)
    next_profile = get_next_profile_for_user(current_user.id, filters)

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


@app.route('/groups')
@login_required
def groups():
    subject = (request.args.get('subject') or '').strip()
    format_filter = (request.args.get('format') or '').strip().lower()

    query = StudyGroup.query.filter_by(is_active=True)
    if subject:
        query = query.filter(StudyGroup.subject.ilike(f"%{subject}%"))
    if format_filter in MEETING_FORMAT_LABELS:
        query = query.filter(StudyGroup.meeting_format == format_filter)

    groups_list = query.order_by(StudyGroup.created_at.desc()).all()

    joined_group_ids = {
        membership.group_id
        for membership in StudyGroupMembership.query.filter_by(user_id=current_user.id).all()
    }

    member_counts = {
        group_id: count
        for group_id, count in db.session.query(
            StudyGroupMembership.group_id, func.count(StudyGroupMembership.id)
        ).group_by(StudyGroupMembership.group_id).all()
    }

    return render_template(
        'groups.html',
        groups=groups_list,
        joined_group_ids=joined_group_ids,
        member_counts=member_counts,
        meeting_format_labels=MEETING_FORMAT_LABELS,
        subject=subject,
        format_filter=format_filter,
    )


@app.route('/groups/new', methods=['GET', 'POST'])
@login_required
def create_group():
    form = StudyGroupForm()

    if form.validate_on_submit():
        city = (form.city.data or '').strip() or None
        max_members = form.max_members.data if form.max_members.data else None

        group = StudyGroup(
            title=form.title.data.strip(),
            subject=form.subject.data.strip(),
            description=form.description.data.strip(),
            meeting_format=form.meeting_format.data,
            city=city,
            max_members=max_members,
            creator_id=current_user.id,
            is_active=True,
        )
        db.session.add(group)
        db.session.flush()

        db.session.add(
            StudyGroupMembership(group_id=group.id, user_id=current_user.id, role='owner')
        )
        db.session.commit()

        flash('Учебная группа успешно создана.', 'success')
        return redirect(url_for('group_detail', group_id=group.id))

    return render_template('group_create.html', form=form)


@app.route('/groups/<int:group_id>')
@login_required
def group_detail(group_id):
    group = StudyGroup.query.get_or_404(group_id)

    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()

    member_count = StudyGroupMembership.query.filter_by(group_id=group.id).count()
    can_join = (
        group.is_active
        and membership is None
        and (group.max_members is None or member_count < group.max_members)
    )

    members = (
        db.session.query(StudyGroupMembership, User, StudentProfile)
        .join(User, User.id == StudyGroupMembership.user_id)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .filter(StudyGroupMembership.group_id == group.id)
        .order_by(StudyGroupMembership.joined_at.asc())
        .all()
    )

    group_messages = []
    if membership:
        group_messages = (
            db.session.query(StudyGroupMessage, User, StudentProfile)
            .join(User, User.id == StudyGroupMessage.sender_id)
            .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
            .filter(StudyGroupMessage.group_id == group.id)
            .order_by(StudyGroupMessage.created_at.asc())
            .all()
        )

    chat_err = session.pop('group_chat_error', None)
    group_chat_field_error = None
    if (
        chat_err
        and isinstance(chat_err, dict)
        and chat_err.get('group_id') == group.id
    ):
        group_chat_field_error = chat_err.get('message')

    me = User.query.get(current_user.id)
    chat_blocked = is_user_profanity_chat_blocked(me)
    chat_blocked_until = me.profanity_blocked_until if chat_blocked else None

    return render_template(
        'group_detail.html',
        group=group,
        membership=membership,
        member_count=member_count,
        can_join=can_join,
        members=members,
        group_messages=group_messages,
        meeting_format_labels=MEETING_FORMAT_LABELS,
        group_chat_field_error=group_chat_field_error,
        chat_blocked=chat_blocked,
        chat_blocked_until=chat_blocked_until,
    )


@app.route('/groups/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(group_id):
    group = StudyGroup.query.get_or_404(group_id)

    if not group.is_active:
        flash('Эта группа уже закрыта.', 'error')
        return redirect(url_for('groups'))

    existing_membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()
    if existing_membership:
        flash('Вы уже состоите в этой группе.', 'info')
        return redirect(url_for('group_detail', group_id=group.id))

    member_count = StudyGroupMembership.query.filter_by(group_id=group.id).count()
    if group.max_members and member_count >= group.max_members:
        flash('В группе уже достигнут лимит участников.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    db.session.add(StudyGroupMembership(group_id=group.id, user_id=current_user.id, role='member'))
    db.session.commit()
    flash('Вы вступили в учебную группу.', 'success')
    return redirect(url_for('group_detail', group_id=group.id))


@app.route('/groups/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    group = StudyGroup.query.get_or_404(group_id)
    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()

    if not membership:
        flash('Вы не состоите в этой группе.', 'info')
        return redirect(url_for('groups'))

    if membership.role == 'owner':
        flash('Создатель группы не может покинуть её. Закройте группу, если она больше не нужна.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    db.session.delete(membership)
    db.session.commit()
    flash('Вы покинули группу.', 'info')
    return redirect(url_for('groups'))


@app.route('/groups/<int:group_id>/messages', methods=['POST'])
@login_required
def send_group_message(group_id):
    group = StudyGroup.query.get_or_404(group_id)
    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()

    if not membership:
        flash('Вступите в группу, чтобы писать в чат.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    if not group.is_active:
        flash('Группа закрыта. В чат больше нельзя отправлять сообщения.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    user = User.query.get(current_user.id)
    if is_user_profanity_chat_blocked(user):
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': format_profanity_chat_blocked_message(user),
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    content = (request.form.get('content') or '').strip()
    if not content:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': 'Введите сообщение.',
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if len(content) > 2000:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': 'Сообщение слишком длинное (максимум 2000 символов).',
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if contains_profanity(content):
        viol = register_chat_profanity_violation(user)
        if viol['banned']:
            user = User.query.get(current_user.id)
            session['group_chat_error'] = {
                'group_id': group.id,
                'message': format_new_chat_ban_message(viol['hours'])
                + ' '
                + format_profanity_chat_blocked_message(user),
            }
        else:
            session['group_chat_error'] = {
                'group_id': group.id,
                'message': (
                    f'{PROFANITY_MSG} (попытка {viol["strikes"]} из {PROFANITY_CHAT_STRIKES_LIMIT} до блокировки чата).'
                ),
            }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    db.session.add(
        StudyGroupMessage(
            group_id=group.id,
            sender_id=current_user.id,
            content=content,
        )
    )
    db.session.commit()
    return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")


@app.route('/groups/<int:group_id>/close', methods=['POST'])
@login_required
def close_group(group_id):
    group = StudyGroup.query.get_or_404(group_id)
    if group.creator_id != current_user.id:
        flash('Закрыть группу может только создатель.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    group.is_active = False
    db.session.commit()
    flash('Группа закрыта.', 'info')
    return redirect(url_for('groups'))

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
        me = User.query.get(current_user.id)
        chat_blocked = is_user_profanity_chat_blocked(me)
        chat_blocked_until = me.profanity_blocked_until if chat_blocked else None

        print("Рендеринг шаблона чата...")
        return render_template(
            'chat.html',
            other_user=other_user,
            messages=messages,
            form=form,
            chat_blocked=chat_blocked,
            chat_blocked_until=chat_blocked_until,
        )
    
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

    user = User.query.get(current_user.id)
    if is_user_profanity_chat_blocked(user):
        return {
            'success': False,
            'blocked': True,
            'error': format_profanity_chat_blocked_message(user),
        }, 403
    
    # Проверяем, что пользователи являются мэтчами
    match = Match.query.filter(
        ((Match.user1_id == current_user.id) & (Match.user2_id == receiver_id)) |
        ((Match.user1_id == receiver_id) & (Match.user2_id == current_user.id))
    ).first()
    
    if not match:
        return {'error': 'Вы можете общаться только с вашими мэтчами'}, 403
    
    form = MessageForm()
    if not form.validate_on_submit():
        return {'success': False, 'error': 'Ошибка валидации формы', 'errors': form.errors}, 400

    content = (form.content.data or '').strip()
    if contains_profanity(content):
        viol = register_chat_profanity_violation(user)
        if viol['banned']:
            user = User.query.get(current_user.id)
            return {
                'success': False,
                'blocked': True,
                'error': format_new_chat_ban_message(viol['hours'])
                + ' '
                + format_profanity_chat_blocked_message(user),
            }, 403
        return {
            'success': False,
            'errors': {
                'content': [
                    f'{PROFANITY_MSG} (попытка {viol["strikes"]} из {PROFANITY_CHAT_STRIKES_LIMIT} до блокировки чата).'
                ]
            },
        }, 400

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
    )

    db.session.add(message)
    db.session.commit()

    return {
        'success': True,
        'message_id': message.id,
        'created_at': message.created_at.strftime('%H:%M'),
    }

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

    created_group_ids = [
        row[0]
        for row in db.session.query(StudyGroup.id).filter(StudyGroup.creator_id == user_id).all()
    ]
    if created_group_ids:
        StudyGroupMessage.query.filter(
            StudyGroupMessage.group_id.in_(created_group_ids)
        ).delete(synchronize_session=False)
        StudyGroupMembership.query.filter(
            StudyGroupMembership.group_id.in_(created_group_ids)
        ).delete(synchronize_session=False)
    StudyGroupMessage.query.filter(StudyGroupMessage.sender_id == user_id).delete(synchronize_session=False)
    StudyGroupMembership.query.filter(StudyGroupMembership.user_id == user_id).delete(synchronize_session=False)
    StudyGroup.query.filter(StudyGroup.creator_id == user_id).delete(synchronize_session=False)

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
