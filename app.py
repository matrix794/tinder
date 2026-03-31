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
import mimetypes
from secrets import token_urlsafe
from datetime import datetime, timedelta
from functools import wraps
from PIL import Image
from sqlalchemy import or_, func, inspect, text

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
PROFILE_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
CHAT_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
CHAT_FILE_EXTENSIONS = {
    'pdf', 'txt', 'csv', 'zip', 'rar', '7z',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'
}
CHAT_ATTACHMENT_EXTENSIONS = CHAT_IMAGE_EXTENSIONS | CHAT_FILE_EXTENSIONS
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['ALLOWED_EXTENSIONS'] = PROFILE_PHOTO_EXTENSIONS
app.config['CHAT_ATTACHMENT_EXTENSIONS'] = CHAT_ATTACHMENT_EXTENSIONS

# Создаем папку для загрузок
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Администраторы (список логинов через запятую в ENV ADMIN_USERS)
ADMIN_USERNAMES = {name.strip().lower() for name in os.environ.get('ADMIN_USERS', 'admin').split(',') if name.strip()}
USER_ROLE_CHOICES = ('user', 'moderator', 'admin')

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
    role = db.Column(db.String(20), nullable=False, default='user')
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    blocked_until = db.Column(db.DateTime, nullable=True)
    chat_muted_until = db.Column(db.DateTime, nullable=True)
    
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
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    attachment_filename = db.Column(db.String(255))
    attachment_original_name = db.Column(db.String(255))
    attachment_mime_type = db.Column(db.String(120))
    attachment_size = db.Column(db.Integer)
    attachment_type = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)
    delivered_at = db.Column(db.DateTime)
    edited_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    reply_to = db.relationship('Message', remote_side=[id], foreign_keys=[reply_to_id], uselist=False)


class ChatPinnedMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    message = db.relationship('Message', foreign_keys=[message_id], backref='chat_pins')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    __table_args__ = (
        db.UniqueConstraint('user1_id', 'user2_id', 'message_id', name='unique_chat_pinned_message'),
        db.Index('idx_chat_pinned_pair_created', 'user1_id', 'user2_id', 'created_at'),
    )


class UserReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    group_message_id = db.Column(db.Integer, db.ForeignKey('study_group_message.id'))
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default='open')
    action_taken = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    resolution_note = db.Column(db.Text)

    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reports_created')
    reported_user = db.relationship('User', foreign_keys=[reported_user_id], backref='reports_received')
    message = db.relationship('Message', foreign_keys=[message_id], backref='reports')
    group_message = db.relationship('StudyGroupMessage', foreign_keys=[group_message_id], backref='reports')
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id], backref='resolved_reports')


class AdminActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(40), nullable=False)
    target_user_id = db.Column(db.Integer)
    report_id = db.Column(db.Integer)
    message_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
    reply_to_id = db.Column(db.Integer, db.ForeignKey('study_group_message.id'))
    attachment_filename = db.Column(db.String(255))
    attachment_original_name = db.Column(db.String(255))
    attachment_mime_type = db.Column(db.String(120))
    attachment_size = db.Column(db.Integer)
    attachment_type = db.Column(db.String(20))
    edited_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', backref='study_group_messages')
    reply_to = db.relationship(
        'StudyGroupMessage',
        remote_side=[id],
        foreign_keys=[reply_to_id],
        uselist=False,
    )


PROFANITY_MSG = 'Недопустимая лексика. Уберите ненормативные выражения.'
DELETED_MESSAGE_TEXT = 'Сообщение удалено'

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
        validators=[validators.Optional(), validators.Length(max=1000)],
        render_kw={"placeholder": "Напишите сообщение...", "rows": 3},
    )
    attachment = FileField(
        'Вложение',
        validators=[FileAllowed(sorted(CHAT_ATTACHMENT_EXTENSIONS), 'Неподдерживаемый тип файла.')],
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


def normalize_user_role(role):
    value = (role or '').strip().lower()
    if value in USER_ROLE_CHOICES:
        return value
    return 'user'


def get_user_role(user):
    if not user:
        return 'user'
    if user.username and user.username.lower() in ADMIN_USERNAMES:
        return 'admin'
    return normalize_user_role(getattr(user, 'role', None))


def is_admin(user):
    return get_user_role(user) == 'admin'


def is_moderator(user):
    return get_user_role(user) in ('moderator', 'admin')


def clear_expired_user_restrictions(user):
    if not user:
        return
    now_utc = datetime.utcnow()
    changed = False
    if getattr(user, 'is_blocked', False) and getattr(user, 'blocked_until', None):
        if user.blocked_until <= now_utc:
            user.is_blocked = False
            user.blocked_until = None
            changed = True
    if getattr(user, 'chat_muted_until', None) and user.chat_muted_until <= now_utc:
        user.chat_muted_until = None
        changed = True
    if changed:
        db.session.commit()


def is_user_blocked(user):
    if not user:
        return False
    if not getattr(user, 'is_blocked', False):
        return False
    until = getattr(user, 'blocked_until', None)
    if not until:
        return True
    return datetime.utcnow() < until


def is_user_chat_muted(user):
    if not user:
        return False
    muted_until = getattr(user, 'chat_muted_until', None)
    if not muted_until:
        return False
    return datetime.utcnow() < muted_until


def format_user_chat_muted_message(user):
    muted_until = getattr(user, 'chat_muted_until', None)
    if not muted_until:
        return 'Вам временно запрещено писать в чат.'
    return f'Чат временно недоступен. Ограничение до {muted_until.strftime("%d.%m.%Y %H:%M")} UTC.'


def format_user_blocked_message(user):
    blocked_until = getattr(user, 'blocked_until', None)
    if blocked_until:
        return f'Ваш аккаунт заблокирован администратором до {blocked_until.strftime("%d.%m.%Y %H:%M")} UTC.'
    return 'Ваш аккаунт заблокирован администратором.'


def get_active_chat_restriction_message(user):
    if not user:
        return None
    if is_user_blocked(user):
        return format_user_blocked_message(user)
    if is_user_chat_muted(user):
        return format_user_chat_muted_message(user)
    if is_user_profanity_chat_blocked(user):
        return format_profanity_chat_blocked_message(user)
    return None


def add_admin_action_log(action, target_user_id=None, report_id=None, message_id=None, details=None):
    if not current_user.is_authenticated:
        return
    db.session.add(
        AdminActionLog(
            admin_id=current_user.id,
            action=action,
            target_user_id=target_user_id,
            report_id=report_id,
            message_id=message_id,
            details=details,
        )
    )


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated or not is_admin(current_user):
            flash('Доступ только для администраторов.', 'error')
            return redirect(url_for('index'))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.before_request
def enforce_account_restrictions():
    if not current_user.is_authenticated:
        return
    endpoint = request.endpoint or ''
    if endpoint in {'logout', 'static'}:
        return
    user = User.query.get(current_user.id)
    if not user:
        return
    clear_expired_user_restrictions(user)
    if is_user_blocked(user):
        logout_user()
        flash(format_user_blocked_message(user), 'error')
        return redirect(url_for('login'))


@app.context_processor
def inject_role_flags():
    return {
        'current_user_is_admin': current_user.is_authenticated and is_admin(current_user),
        'current_user_role': get_user_role(current_user) if current_user.is_authenticated else 'user',
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
def get_file_extension(filename):
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def allowed_profile_photo(filename):
    return get_file_extension(filename) in PROFILE_PHOTO_EXTENSIONS


def allowed_chat_attachment(filename):
    return get_file_extension(filename) in CHAT_ATTACHMENT_EXTENSIONS


def save_chat_attachment(file, sender_id):
    if not file or not file.filename:
        return None, None

    original_name = (file.filename or '').strip().replace('\\', '/').split('/')[-1]
    if not original_name:
        return None, 'Некорректное имя файла.'

    ext = get_file_extension(original_name)
    if ext not in CHAT_ATTACHMENT_EXTENSIONS:
        return None, 'Неподдерживаемый тип файла.'

    # Защита от больших файлов (дополнительно к MAX_CONTENT_LENGTH).
    try:
        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
    except Exception:
        file_size = file.content_length or 0

    if file_size > MAX_FILE_SIZE:
        return None, 'Файл слишком большой (максимум 5 МБ).'

    attachment_filename = f"chat_{sender_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}.{ext}"
    upload_folder = app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, attachment_filename)
    file.save(filepath)

    return {
        'attachment_filename': attachment_filename,
        'attachment_original_name': original_name,
        'attachment_mime_type': file.mimetype or mimetypes.guess_type(original_name)[0] or 'application/octet-stream',
        'attachment_size': int(file_size or 0),
        'attachment_type': 'image' if ext in CHAT_IMAGE_EXTENSIONS else 'file',
    }, None


def delete_uploaded_file(filename):
    if not filename:
        return
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)


def get_attachment_kind(filename, attachment_type=None):
    if attachment_type in ('image', 'file'):
        return attachment_type
    return 'image' if get_file_extension(filename) in CHAT_IMAGE_EXTENSIONS else 'file'


def get_attachment_preview_label(obj):
    if not getattr(obj, 'attachment_filename', None):
        return None
    kind = get_attachment_kind(obj.attachment_filename, getattr(obj, 'attachment_type', None))
    return '[Фотография]' if kind == 'image' else '[Файл]'


def _trim_text(text, max_len=80):
    normalized = (text or '').replace('\n', ' ').strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1] + '…'


def build_reply_payload(message_obj):
    replied = getattr(message_obj, 'reply_to', None)
    if not replied:
        return None

    replied_sender = getattr(replied, 'sender', None)
    if replied_sender and replied_sender.profile:
        replied_sender_name = replied_sender.profile.full_name
    elif replied_sender:
        replied_sender_name = replied_sender.username
    else:
        replied_sender_name = 'Пользователь'

    if getattr(replied, 'deleted_at', None):
        preview = DELETED_MESSAGE_TEXT
    elif (getattr(replied, 'content', '') or '').strip():
        preview = _trim_text(replied.content)
    else:
        preview = get_attachment_preview_label(replied) or ''

    return {
        'id': replied.id,
        'sender_name': replied_sender_name,
        'preview': preview,
        'is_deleted': bool(getattr(replied, 'deleted_at', None)),
    }


def get_message_attachment_payload(message):
    if not message.attachment_filename or message.deleted_at:
        return None

    return {
        'url': url_for('uploaded_file', filename=message.attachment_filename),
        'filename': message.attachment_filename,
        'original_name': message.attachment_original_name or message.attachment_filename,
        'mime_type': message.attachment_mime_type,
        'size': message.attachment_size or 0,
        'type': get_attachment_kind(message.attachment_filename, message.attachment_type),
    }


def serialize_chat_message(message):
    is_deleted = bool(message.deleted_at)
    is_read = bool(message.is_read)
    is_delivered = bool(message.delivered_at) or is_read
    return {
        'id': message.id,
        'sender_id': message.sender_id,
        'content': DELETED_MESSAGE_TEXT if is_deleted else (message.content or ''),
        'created_at': message.created_at.strftime('%H:%M'),
        'is_deleted': is_deleted,
        'is_edited': bool(message.edited_at) and not is_deleted,
        'is_read': is_read,
        'is_delivered': is_delivered,
        'sender_name': message.sender.profile.full_name if message.sender.profile else message.sender.username,
        'attachment': get_message_attachment_payload(message),
        'reply_to': build_reply_payload(message),
    }


def get_chat_pair_ids(user_a_id, user_b_id):
    return (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)


def serialize_chat_pinned_message(message):
    if message.deleted_at:
        preview = DELETED_MESSAGE_TEXT
    elif (message.content or '').strip():
        preview = _trim_text(message.content, 90)
    else:
        preview = get_attachment_preview_label(message) or ''

    sender_name = message.sender.profile.full_name if message.sender and message.sender.profile else (message.sender.username if message.sender else 'Пользователь')
    return {
        'id': message.id,
        'sender_id': message.sender_id,
        'sender_name': sender_name,
        'preview': preview,
        'is_deleted': bool(message.deleted_at),
        'created_at': message.created_at.strftime('%H:%M'),
    }


def serialize_chat_pinned_messages(user_a_id, user_b_id):
    user1_id, user2_id = get_chat_pair_ids(user_a_id, user_b_id)
    pinned_rows = (
        db.session.query(ChatPinnedMessage, Message)
        .join(Message, Message.id == ChatPinnedMessage.message_id)
        .filter(
            ChatPinnedMessage.user1_id == user1_id,
            ChatPinnedMessage.user2_id == user2_id,
        )
        .order_by(ChatPinnedMessage.created_at.desc())
        .all()
    )
    return [serialize_chat_pinned_message(message) for _, message in pinned_rows]


def build_chat_list_for_user(user_id):
    user_matches = db.session.query(Match).filter(
        (Match.user1_id == user_id) | (Match.user2_id == user_id)
    ).all()

    chat_items = []
    for match in user_matches:
        other_user_id = match.user2_id if match.user1_id == user_id else match.user1_id
        other_user = User.query.get(other_user_id)
        other_profile = StudentProfile.query.filter_by(user_id=other_user_id).first()
        if not other_user or not other_profile:
            continue

        last_message = Message.query.filter(
            ((Message.sender_id == user_id) & (Message.receiver_id == other_user_id))
            | ((Message.sender_id == other_user_id) & (Message.receiver_id == user_id))
        ).order_by(Message.created_at.desc()).first()

        if last_message:
            if last_message.deleted_at:
                last_message_preview = '[Удалено]'
            elif (last_message.content or '').strip():
                last_message_preview = _trim_text(last_message.content, 80)
            elif last_message.attachment_filename:
                attachment_kind = get_attachment_kind(last_message.attachment_filename, last_message.attachment_type)
                last_message_preview = '[Фотография]' if attachment_kind == 'image' else '[Файл]'
            else:
                last_message_preview = None
        else:
            last_message_preview = None

        unread_count = Message.query.filter(
            Message.sender_id == other_user_id,
            Message.receiver_id == user_id,
            Message.is_read == False
        ).count()

        chat_items.append({
            'user': other_user,
            'user_id': other_user_id,
            'profile': other_profile,
            'match_date': match.created_at,
            'last_message': last_message_preview,
            'last_message_time': last_message.created_at.strftime('%H:%M') if last_message else None,
            'last_message_at': last_message.created_at if last_message else match.created_at,
            'has_unread': unread_count > 0,
            'unread_count': unread_count,
        })

    chat_items.sort(key=lambda item: item.get('last_message_at') or item['match_date'], reverse=True)
    return chat_items


def save_profile_photo(file, user_id):
    if file and file.filename and allowed_profile_photo(file.filename):
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
    delete_uploaded_file(filename)

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
            clear_expired_user_restrictions(user)
            if is_user_blocked(user):
                flash(format_user_blocked_message(user), 'error')
                return render_template('login.html', form=form)
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
    clear_expired_user_restrictions(user)
    if is_user_blocked(user):
        flash(format_user_blocked_message(user), 'error')
        return redirect(url_for('login'))
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
    clear_expired_user_restrictions(user)
    if is_user_blocked(user):
        flash(format_user_blocked_message(user), 'error')
        return redirect(url_for('login'))
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

    match_profiles = build_chat_list_for_user(current_user.id)
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
    clear_expired_user_restrictions(me)
    chat_blocked_message = get_active_chat_restriction_message(me)
    chat_blocked = bool(chat_blocked_message)
    chat_blocked_until = None
    if chat_blocked:
        if is_user_chat_muted(me):
            chat_blocked_until = me.chat_muted_until
        elif is_user_profanity_chat_blocked(me):
            chat_blocked_until = me.profanity_blocked_until

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
        chat_blocked_message=chat_blocked_message,
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
    clear_expired_user_restrictions(user)
    restriction_message = get_active_chat_restriction_message(user)
    if restriction_message:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': restriction_message,
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    content = (request.form.get('content') or '').strip()
    attachment_file = request.files.get('attachment')
    has_attachment = bool(attachment_file and attachment_file.filename)
    reply_to_id_raw = (request.form.get('reply_to_id') or '').strip()
    reply_to_message = None

    if reply_to_id_raw:
        if not reply_to_id_raw.isdigit():
            session['group_chat_error'] = {
                'group_id': group.id,
                'message': 'Некорректная ссылка на сообщение для ответа.',
            }
            return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")
        reply_to_message = StudyGroupMessage.query.filter_by(
            id=int(reply_to_id_raw),
            group_id=group.id,
        ).first()
        if not reply_to_message:
            session['group_chat_error'] = {
                'group_id': group.id,
                'message': 'Сообщение для ответа не найдено.',
            }
            return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if not content and not has_attachment:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': 'Введите сообщение или добавьте вложение.',
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if len(content) > 2000:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': 'Сообщение слишком длинное (максимум 2000 символов).',
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if content and contains_profanity(content):
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

    attachment_payload = None
    if has_attachment:
        attachment_payload, attachment_error = save_chat_attachment(attachment_file, current_user.id)
        if attachment_error:
            session['group_chat_error'] = {
                'group_id': group.id,
                'message': attachment_error,
            }
            return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    db.session.add(
        StudyGroupMessage(
            group_id=group.id,
            sender_id=current_user.id,
            content=content,
            reply_to_id=reply_to_message.id if reply_to_message else None,
            attachment_filename=attachment_payload['attachment_filename'] if attachment_payload else None,
            attachment_original_name=attachment_payload['attachment_original_name'] if attachment_payload else None,
            attachment_mime_type=attachment_payload['attachment_mime_type'] if attachment_payload else None,
            attachment_size=attachment_payload['attachment_size'] if attachment_payload else None,
            attachment_type=attachment_payload['attachment_type'] if attachment_payload else None,
        )
    )
    db.session.commit()
    return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")


@app.route('/groups/<int:group_id>/messages/<int:message_id>/edit', methods=['POST'])
@login_required
def edit_group_message(group_id, message_id):
    group = StudyGroup.query.get_or_404(group_id)
    if not group.is_active:
        flash('Группа закрыта. Редактирование сообщений отключено.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))
    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()
    if not membership:
        flash('Вступите в группу, чтобы управлять сообщениями.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    message = StudyGroupMessage.query.filter_by(id=message_id, group_id=group.id).first_or_404()
    if message.sender_id != current_user.id:
        flash('Можно редактировать только свои сообщения.', 'error')
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if message.deleted_at:
        flash('Удалённое сообщение нельзя редактировать.', 'error')
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    user = User.query.get(current_user.id)
    clear_expired_user_restrictions(user)
    restriction_message = get_active_chat_restriction_message(user)
    if restriction_message:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': restriction_message,
        }
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    content = (request.form.get('content') or '').strip()
    if not content:
        session['group_chat_error'] = {
            'group_id': group.id,
            'message': 'Введите текст сообщения для редактирования.',
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

    message.content = content
    message.edited_at = datetime.utcnow()
    db.session.commit()
    return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")


@app.route('/groups/<int:group_id>/messages/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_group_message(group_id, message_id):
    group = StudyGroup.query.get_or_404(group_id)
    if not group.is_active:
        flash('Группа закрыта. Удаление сообщений отключено.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))
    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id, user_id=current_user.id
    ).first()
    if not membership:
        flash('Вступите в группу, чтобы управлять сообщениями.', 'error')
        return redirect(url_for('group_detail', group_id=group.id))

    message = StudyGroupMessage.query.filter_by(id=message_id, group_id=group.id).first_or_404()
    if message.sender_id != current_user.id:
        flash('Можно удалять только свои сообщения.', 'error')
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    if message.deleted_at:
        return redirect(f"{url_for('group_detail', group_id=group.id)}#group-chat")

    delete_uploaded_file(message.attachment_filename)
    message.content = ''
    message.attachment_filename = None
    message.attachment_original_name = None
    message.attachment_mime_type = None
    message.attachment_size = None
    message.attachment_type = None
    message.deleted_at = datetime.utcnow()
    message.edited_at = None
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
        
        # При открытии чата отмечаем входящие как доставленные.
        # В прочитанные переводим при синхронизации /get-messages (когда чат уже активен).
        now_utc = datetime.utcnow()
        has_updates = False
        for message in messages:
            if message.receiver_id != current_user.id:
                continue
            if not message.delivered_at:
                message.delivered_at = now_utc
                has_updates = True
        if has_updates:
            db.session.commit()
        
        form = MessageForm()
        me = User.query.get(current_user.id)
        clear_expired_user_restrictions(me)
        chat_blocked_message = get_active_chat_restriction_message(me)
        chat_blocked = bool(chat_blocked_message)
        chat_blocked_until = None
        if chat_blocked:
            if is_user_chat_muted(me):
                chat_blocked_until = me.chat_muted_until
            elif is_user_profanity_chat_blocked(me):
                chat_blocked_until = me.profanity_blocked_until
        pinned_messages = serialize_chat_pinned_messages(current_user.id, user_id)
        chat_list = build_chat_list_for_user(current_user.id)

        print("Рендеринг шаблона чата...")
        return render_template(
            'chat.html',
            other_user=other_user,
            messages=messages,
            pinned_messages=pinned_messages,
            chat_list=chat_list,
            selected_chat_user_id=user_id,
            form=form,
            chat_blocked=chat_blocked,
            chat_blocked_until=chat_blocked_until,
            chat_blocked_message=chat_blocked_message,
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
    clear_expired_user_restrictions(user)
    restriction_message = get_active_chat_restriction_message(user)
    if restriction_message:
        return {
            'success': False,
            'blocked': True,
            'error': restriction_message,
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
    attachment_file = form.attachment.data
    has_attachment = bool(getattr(attachment_file, 'filename', None))
    reply_to_id_raw = (request.form.get('reply_to_id') or '').strip()
    reply_to_message = None

    if reply_to_id_raw:
        if not reply_to_id_raw.isdigit():
            return {
                'success': False,
                'errors': {'content': ['Некорректная ссылка на сообщение для ответа.']},
            }, 400
        reply_to_id = int(reply_to_id_raw)
        reply_to_message = Message.query.filter(
            Message.id == reply_to_id,
            (
                ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id))
                | ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id))
            ),
        ).first()
        if not reply_to_message:
            return {
                'success': False,
                'errors': {'content': ['Сообщение для ответа не найдено.']},
            }, 400

    if not content and not has_attachment:
        return {
            'success': False,
            'errors': {
                'content': ['Введите сообщение или добавьте вложение.'],
            },
        }, 400

    if content and contains_profanity(content):
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

    attachment_payload = None
    if has_attachment:
        attachment_payload, attachment_error = save_chat_attachment(attachment_file, current_user.id)
        if attachment_error:
            return {
                'success': False,
                'errors': {'attachment': [attachment_error]},
            }, 400

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content,
        reply_to_id=reply_to_message.id if reply_to_message else None,
        attachment_filename=attachment_payload['attachment_filename'] if attachment_payload else None,
        attachment_original_name=attachment_payload['attachment_original_name'] if attachment_payload else None,
        attachment_mime_type=attachment_payload['attachment_mime_type'] if attachment_payload else None,
        attachment_size=attachment_payload['attachment_size'] if attachment_payload else None,
        attachment_type=attachment_payload['attachment_type'] if attachment_payload else None,
    )

    db.session.add(message)
    db.session.commit()

    return {
        'success': True,
        'message': serialize_chat_message(message),
    }


@app.route('/edit-message/<int:message_id>', methods=['POST'])
@login_required
def edit_message(message_id):
    message = Message.query.get_or_404(message_id)
    if message.sender_id != current_user.id:
        return {'success': False, 'error': 'Можно редактировать только свои сообщения.'}, 403
    if message.deleted_at:
        return {'success': False, 'error': 'Удалённое сообщение нельзя редактировать.'}, 400

    user = User.query.get(current_user.id)
    clear_expired_user_restrictions(user)
    restriction_message = get_active_chat_restriction_message(user)
    if restriction_message:
        return {
            'success': False,
            'blocked': True,
            'error': restriction_message,
        }, 403

    content = (request.form.get('content') or '').strip()
    if not content:
        return {'success': False, 'errors': {'content': ['Введите текст сообщения.']}}, 400
    if len(content) > 1000:
        return {'success': False, 'errors': {'content': ['Сообщение слишком длинное (максимум 1000 символов).']}}, 400

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

    message.content = content
    message.edited_at = datetime.utcnow()
    db.session.commit()
    return {'success': True, 'message': serialize_chat_message(message)}


@app.route('/delete-message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)
    if message.sender_id != current_user.id:
        return {'success': False, 'error': 'Можно удалять только свои сообщения.'}, 403

    if message.deleted_at:
        return {'success': True, 'message': serialize_chat_message(message)}

    delete_uploaded_file(message.attachment_filename)
    message.content = ''
    message.attachment_filename = None
    message.attachment_original_name = None
    message.attachment_mime_type = None
    message.attachment_size = None
    message.attachment_type = None
    message.deleted_at = datetime.utcnow()
    message.edited_at = None
    db.session.commit()
    return {'success': True, 'message': serialize_chat_message(message)}


@app.route('/pin-message/<int:message_id>', methods=['POST'])
@login_required
def pin_message(message_id):
    message = Message.query.get_or_404(message_id)
    if current_user.id not in (message.sender_id, message.receiver_id):
        return {'success': False, 'error': 'Недостаточно прав для закрепления этого сообщения.'}, 403

    user1_id, user2_id = get_chat_pair_ids(message.sender_id, message.receiver_id)
    existing = ChatPinnedMessage.query.filter_by(
        user1_id=user1_id,
        user2_id=user2_id,
        message_id=message.id,
    ).first()
    if not existing:
        db.session.add(
            ChatPinnedMessage(
                user1_id=user1_id,
                user2_id=user2_id,
                message_id=message.id,
                created_by_id=current_user.id,
            )
        )
        db.session.commit()

    return {
        'success': True,
        'pinned_messages': serialize_chat_pinned_messages(message.sender_id, message.receiver_id),
    }


@app.route('/unpin-message/<int:message_id>', methods=['POST'])
@login_required
def unpin_message(message_id):
    message = Message.query.get_or_404(message_id)
    if current_user.id not in (message.sender_id, message.receiver_id):
        return {'success': False, 'error': 'Недостаточно прав для открепления этого сообщения.'}, 403

    user1_id, user2_id = get_chat_pair_ids(message.sender_id, message.receiver_id)
    ChatPinnedMessage.query.filter_by(
        user1_id=user1_id,
        user2_id=user2_id,
        message_id=message.id,
    ).delete(synchronize_session=False)
    db.session.commit()

    return {
        'success': True,
        'pinned_messages': serialize_chat_pinned_messages(message.sender_id, message.receiver_id),
    }


@app.route('/get-messages/<int:user_id>')
@login_required
def get_messages(user_id):
    """Получение сообщений чата (для синхронизации новых/изменённых/удалённых)."""
    if not current_user.profile:
        return {'error': 'Профиль не создан'}, 400
    
    # Отдаём всю переписку, чтобы синхронизировать редактирование/удаление.
    messages = Message.query.filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
        | ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id))
    ).order_by(Message.created_at.asc()).all()
    
    # Отмечаем входящие как доставленные/прочитанные.
    now_utc = datetime.utcnow()
    has_updates = False
    for message in messages:
        if message.receiver_id != current_user.id:
            continue
        if not message.delivered_at:
            message.delivered_at = now_utc
            has_updates = True
        if not message.is_read:
            message.is_read = True
            has_updates = True
    if has_updates:
        db.session.commit()
    
    # Форматируем сообщения для JSON
    messages_data = []
    for message in messages:
        messages_data.append(serialize_chat_message(message))
    
    return {
        'messages': messages_data,
        'pinned_messages': serialize_chat_pinned_messages(current_user.id, user_id),
    }


@app.route('/report-message/<int:message_id>', methods=['POST'])
@login_required
def report_message(message_id):
    message = Message.query.get_or_404(message_id)
    if current_user.id not in (message.sender_id, message.receiver_id):
        return {'success': False, 'error': 'Недостаточно прав для жалобы на это сообщение.'}, 403
    if message.sender_id == current_user.id:
        return {'success': False, 'error': 'Нельзя пожаловаться на собственное сообщение.'}, 400

    existing_open = UserReport.query.filter_by(
        reporter_id=current_user.id,
        message_id=message.id,
        status='open',
    ).first()
    if existing_open:
        return {'success': True, 'report_id': existing_open.id}

    reason = (request.form.get('reason') or '').strip()
    if len(reason) > 1000:
        return {'success': False, 'error': 'Слишком длинное описание жалобы (максимум 1000 символов).'}, 400

    report = UserReport(
        reporter_id=current_user.id,
        reported_user_id=message.sender_id,
        message_id=message.id,
        reason=reason or None,
        status='open',
    )
    db.session.add(report)
    db.session.commit()
    return {'success': True, 'report_id': report.id}


@app.route('/groups/<int:group_id>/messages/<int:message_id>/report', methods=['POST'])
@login_required
def report_group_message(group_id, message_id):
    group = StudyGroup.query.get_or_404(group_id)
    membership = StudyGroupMembership.query.filter_by(
        group_id=group.id,
        user_id=current_user.id,
    ).first()
    if not membership:
        return {'success': False, 'error': 'Вступите в группу, чтобы отправлять жалобы на сообщения.'}, 403

    message = StudyGroupMessage.query.filter_by(
        id=message_id,
        group_id=group.id,
    ).first_or_404()
    if message.sender_id == current_user.id:
        return {'success': False, 'error': 'Нельзя пожаловаться на собственное сообщение.'}, 400

    existing_open = UserReport.query.filter_by(
        reporter_id=current_user.id,
        group_message_id=message.id,
        status='open',
    ).first()
    if existing_open:
        return {'success': True, 'report_id': existing_open.id}

    reason = (request.form.get('reason') or '').strip()
    if len(reason) > 1000:
        return {'success': False, 'error': 'Слишком длинное описание жалобы (максимум 1000 символов).'}, 400

    report = UserReport(
        reporter_id=current_user.id,
        reported_user_id=message.sender_id,
        group_message_id=message.id,
        reason=reason or None,
        status='open',
    )
    db.session.add(report)
    db.session.commit()
    return {'success': True, 'report_id': report.id}


@app.route('/report-profile/<int:profile_id>', methods=['POST'])
@login_required
def report_profile(profile_id):
    profile = StudentProfile.query.get_or_404(profile_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not profile.is_active:
        if is_ajax:
            return {'success': False, 'error': '??????? ?????????.'}, 400
        flash('??????? ?????????.', 'error')
        return redirect(request.referrer or url_for('tinder'))

    if profile.user_id == current_user.id:
        if is_ajax:
            return {'success': False, 'error': '?????? ???????????? ?? ???? ???????.'}, 400
        flash('?????? ???????????? ?? ???? ???????.', 'error')
        return redirect(request.referrer or url_for('view_profile', profile_id=profile.id))

    existing_open = UserReport.query.filter_by(
        reporter_id=current_user.id,
        reported_user_id=profile.user_id,
        message_id=None,
        group_message_id=None,
        status='open',
    ).first()
    if existing_open:
        if is_ajax:
            return {'success': True, 'report_id': existing_open.id}
        flash('?????? ?? ??????? ??? ?????????? ? ??????? ????????????.', 'info')
        return redirect(request.referrer or url_for('view_profile', profile_id=profile.id))

    reason = (request.form.get('reason') or '').strip()
    if len(reason) > 1000:
        if is_ajax:
            return {'success': False, 'error': '??????? ??????? ???????? ?????? (???????? 1000 ????????).'}, 400
        flash('??????? ??????? ???????? ?????? (???????? 1000 ????????).', 'error')
        return redirect(request.referrer or url_for('view_profile', profile_id=profile.id))

    report = UserReport(
        reporter_id=current_user.id,
        reported_user_id=profile.user_id,
        reason=reason or '?????? ?? ???????',
        status='open',
    )
    db.session.add(report)
    db.session.commit()

    if is_ajax:
        return {'success': True, 'report_id': report.id}

    flash('?????? ?? ??????? ?????????? ??????????????.', 'success')
    return redirect(request.referrer or url_for('view_profile', profile_id=profile.id))


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    now_utc = datetime.utcnow()
    total_users = User.query.count()
    total_profiles = StudentProfile.query.count()
    total_active_profiles = StudentProfile.query.filter_by(is_active=True).count()
    total_matches = Match.query.count()
    total_messages = Message.query.count()
    total_open_reports = UserReport.query.filter_by(status='open').count()
    total_blocked_users = User.query.filter(
        User.is_blocked.is_(True),
        or_(User.blocked_until.is_(None), User.blocked_until > now_utc),
    ).count()
    total_muted_users = User.query.filter(
        User.chat_muted_until.isnot(None),
        User.chat_muted_until > now_utc,
    ).count()
    actions_last_24h = AdminActionLog.query.filter(
        AdminActionLog.created_at >= (now_utc - timedelta(hours=24))
    ).count()

    latest_users = User.query.order_by(User.created_at.desc()).limit(8).all()
    latest_profiles = StudentProfile.query.order_by(StudentProfile.created_at.desc()).limit(8).all()
    latest_reports = (
        UserReport.query
        .order_by(UserReport.created_at.desc())
        .limit(6)
        .all()
    )

    return render_template(
        'admin/dashboard.html',
        stats={
            'total_users': total_users,
            'total_profiles': total_profiles,
            'total_active_profiles': total_active_profiles,
            'total_matches': total_matches,
            'total_messages': total_messages,
            'total_open_reports': total_open_reports,
            'total_blocked_users': total_blocked_users,
            'total_muted_users': total_muted_users,
            'actions_last_24h': actions_last_24h,
        },
        latest_users=latest_users,
        latest_profiles=latest_profiles,
        latest_reports=latest_reports,
    )


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    now_utc = datetime.utcnow()
    users = User.query.order_by(User.created_at.desc()).all()
    effective_roles = {user.id: get_user_role(user) for user in users}
    total_report_counts = dict(
        db.session.query(UserReport.reported_user_id, func.count(UserReport.id))
        .group_by(UserReport.reported_user_id)
        .all()
    )
    open_report_counts = dict(
        db.session.query(UserReport.reported_user_id, func.count(UserReport.id))
        .filter(UserReport.status == 'open')
        .group_by(UserReport.reported_user_id)
        .all()
    )
    return render_template(
        'admin/users.html',
        users=users,
        role_choices=USER_ROLE_CHOICES,
        effective_roles=effective_roles,
        now_utc=now_utc,
        total_report_counts=total_report_counts,
        open_report_counts=open_report_counts,
    )


@app.route('/admin/users/<int:user_id>/manage', methods=['POST'])
@login_required
@admin_required
def admin_manage_user(user_id):
    user = User.query.get_or_404(user_id)
    action = (request.form.get('action') or '').strip().lower()
    if not action:
        flash('Не выбрано действие.', 'error')
        return redirect(url_for('admin_users'))

    protected_admin = bool(user.username and user.username.lower() in ADMIN_USERNAMES)
    if user.id == current_user.id and action in {'block_user', 'set_role'}:
        flash('Нельзя применить это действие к своему аккаунту.', 'error')
        return redirect(url_for('admin_users'))

    if action == 'set_role':
        new_role = normalize_user_role(request.form.get('role'))
        if new_role not in USER_ROLE_CHOICES:
            flash('Некорректная роль.', 'error')
            return redirect(url_for('admin_users'))
        if protected_admin and new_role != 'admin':
            flash('Для системного администратора роль admin обязательна.', 'error')
            return redirect(url_for('admin_users'))
        user.role = new_role
        add_admin_action_log('set_role', target_user_id=user.id, details=f'role={new_role}')
        db.session.commit()
        flash('Роль пользователя обновлена.', 'success')
        return redirect(url_for('admin_users'))

    if action == 'mute_chat':
        minutes_raw = (request.form.get('minutes') or '60').strip()
        try:
            minutes = int(minutes_raw)
        except (TypeError, ValueError):
            flash('Некорректная длительность мута.', 'error')
            return redirect(url_for('admin_users'))
        if minutes < 1 or minutes > 43200:
            flash('Длительность мута должна быть от 1 до 43200 минут.', 'error')
            return redirect(url_for('admin_users'))
        until = datetime.utcnow() + timedelta(minutes=minutes)
        user.chat_muted_until = until
        add_admin_action_log('mute_chat', target_user_id=user.id, details=f'until={until.isoformat()}')
        db.session.commit()
        flash('Пользователь получил мут чата.', 'success')
        return redirect(url_for('admin_users'))

    if action == 'clear_mute':
        user.chat_muted_until = None
        add_admin_action_log('clear_mute', target_user_id=user.id)
        db.session.commit()
        flash('Мут чата снят.', 'success')
        return redirect(url_for('admin_users'))

    if action == 'block_user':
        if protected_admin:
            flash('Нельзя заблокировать системного администратора.', 'error')
            return redirect(url_for('admin_users'))
        hours_raw = (request.form.get('hours') or '').strip()
        until = None
        if hours_raw:
            try:
                hours = int(hours_raw)
            except (TypeError, ValueError):
                flash('Некорректная длительность блокировки.', 'error')
                return redirect(url_for('admin_users'))
            if hours < 1 or hours > 8760:
                flash('Длительность блокировки должна быть от 1 до 8760 часов.', 'error')
                return redirect(url_for('admin_users'))
            until = datetime.utcnow() + timedelta(hours=hours)
        user.is_blocked = True
        user.blocked_until = until
        add_admin_action_log(
            'block_user',
            target_user_id=user.id,
            details=f'until={until.isoformat() if until else "permanent"}',
        )
        db.session.commit()
        flash('Пользователь заблокирован.', 'success')
        return redirect(url_for('admin_users'))

    if action == 'unblock_user':
        user.is_blocked = False
        user.blocked_until = None
        add_admin_action_log('unblock_user', target_user_id=user.id)
        db.session.commit()
        flash('Пользователь разблокирован.', 'success')
        return redirect(url_for('admin_users'))

    flash('Неизвестное действие.', 'error')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if current_user.id == user_id:
        flash('Нельзя удалить собственный аккаунт администратора.', 'error')
        return redirect(url_for('admin_users'))

    user = User.query.get_or_404(user_id)
    protected_admin = bool(user.username and user.username.lower() in ADMIN_USERNAMES)
    if protected_admin:
        flash('Нельзя удалить системного администратора.', 'error')
        return redirect(url_for('admin_users'))

    if user.profile and user.profile.photo_filename:
        delete_profile_photo(user.profile.photo_filename)

    message_ids_to_delete = [
        row[0]
        for row in db.session.query(Message.id).filter(
            or_(Message.sender_id == user_id, Message.receiver_id == user_id)
        ).all()
    ]

    if message_ids_to_delete:
        UserReport.query.filter(UserReport.message_id.in_(message_ids_to_delete)).delete(synchronize_session=False)
    UserReport.query.filter(
        or_(
            UserReport.reporter_id == user_id,
            UserReport.reported_user_id == user_id,
            UserReport.resolved_by_id == user_id,
        )
    ).delete(synchronize_session=False)

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

    add_admin_action_log('delete_user', target_user_id=user.id, details=f'username={user.username}')
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


@app.route('/admin/reports')
@login_required
@admin_required
def admin_reports():
    open_reports = (
        UserReport.query
        .filter(UserReport.status == 'open')
        .order_by(UserReport.created_at.desc())
        .all()
    )
    resolved_reports = (
        UserReport.query
        .filter(UserReport.status != 'open')
        .order_by(UserReport.resolved_at.desc(), UserReport.created_at.desc())
        .limit(200)
        .all()
    )
    reports = open_reports + resolved_reports
    return render_template('admin/reports.html', reports=reports, now_utc=datetime.utcnow())


@app.route('/admin/reports/<int:report_id>/action', methods=['POST'])
@login_required
@admin_required
def admin_report_action(report_id):
    report = UserReport.query.get_or_404(report_id)
    action = (request.form.get('action') or '').strip().lower()
    if action not in {'delete_message', 'warn_user', 'ban_user', 'dismiss'}:
        flash('Неизвестное действие по жалобе.', 'error')
        return redirect(url_for('admin_reports'))

    if report.status != 'open':
        flash('Жалоба уже обработана.', 'info')
        return redirect(url_for('admin_reports'))

    resolution_note = (request.form.get('note') or '').strip()
    message_for_flash = 'Жалоба обработана.'
    details = []

    if action == 'delete_message':
        deleted_any_message = False
        if report.message and not report.message.deleted_at:
            delete_uploaded_file(report.message.attachment_filename)
            report.message.content = ''
            report.message.attachment_filename = None
            report.message.attachment_original_name = None
            report.message.attachment_mime_type = None
            report.message.attachment_size = None
            report.message.attachment_type = None
            report.message.deleted_at = datetime.utcnow()
            report.message.edited_at = None
            details.append('message_deleted')
            deleted_any_message = True
        if report.group_message and not report.group_message.deleted_at:
            delete_uploaded_file(report.group_message.attachment_filename)
            report.group_message.content = ''
            report.group_message.attachment_filename = None
            report.group_message.attachment_original_name = None
            report.group_message.attachment_mime_type = None
            report.group_message.attachment_size = None
            report.group_message.attachment_type = None
            report.group_message.deleted_at = datetime.utcnow()
            report.group_message.edited_at = None
            details.append('group_message_deleted')
            deleted_any_message = True
        if not deleted_any_message:
            details.append('message_missing_or_already_deleted')
        report.action_taken = 'delete_message'
        if deleted_any_message:
            message_for_flash = '��������� �������, ������ �������.'
        else:
            message_for_flash = '��������� ��� ������� ��� ����������, ������ �������.'

    elif action == 'warn_user':
        report.action_taken = 'warn_user'
        if not resolution_note:
            resolution_note = 'Предупреждение зафиксировано администратором.'
        message_for_flash = 'Пользователю вынесено предупреждение.'

    elif action == 'ban_user':
        target = report.reported_user
        if not target:
            flash('Не удалось определить пользователя для блокировки.', 'error')
            return redirect(url_for('admin_reports'))
        if target.username and target.username.lower() in ADMIN_USERNAMES:
            flash('Нельзя заблокировать системного администратора.', 'error')
            return redirect(url_for('admin_reports'))
        hours_raw = (request.form.get('hours') or '24').strip()
        try:
            hours = int(hours_raw)
        except (TypeError, ValueError):
            flash('Некорректная длительность блокировки.', 'error')
            return redirect(url_for('admin_reports'))
        if hours < 1 or hours > 8760:
            flash('Длительность блокировки должна быть от 1 до 8760 часов.', 'error')
            return redirect(url_for('admin_reports'))
        target.is_blocked = True
        target.blocked_until = datetime.utcnow() + timedelta(hours=hours)
        report.action_taken = 'ban_user'
        if not resolution_note:
            resolution_note = f'Блокировка пользователя на {hours} ч.'
        message_for_flash = 'Пользователь заблокирован, жалоба закрыта.'
        details.append(f'ban_hours={hours}')

    elif action == 'dismiss':
        report.action_taken = 'dismissed'
        if not resolution_note:
            resolution_note = 'Жалоба отклонена администратором.'
        message_for_flash = 'Жалоба отклонена.'

    report.status = 'resolved'
    report.resolved_at = datetime.utcnow()
    report.resolved_by_id = current_user.id
    if details:
        resolution_note = (resolution_note + ' ' if resolution_note else '') + '; '.join(details)
    report.resolution_note = resolution_note or None

    add_admin_action_log(
        action,
        target_user_id=report.reported_user_id,
        report_id=report.id,
        message_id=report.message_id or report.group_message_id,
        details=report.resolution_note,
    )
    db.session.commit()
    flash(message_for_flash, 'success')
    return redirect(url_for('admin_reports'))


@app.route('/admin/logs')
@login_required
@admin_required
def admin_logs():
    logs = (
        AdminActionLog.query
        .order_by(AdminActionLog.created_at.desc())
        .limit(500)
        .all()
    )
    user_ids = set()
    for log in logs:
        if log.admin_id:
            user_ids.add(log.admin_id)
        if log.target_user_id:
            user_ids.add(log.target_user_id)
    users = User.query.filter(User.id.in_(list(user_ids))).all() if user_ids else []
    user_map = {user.id: user for user in users}
    return render_template('admin/logs.html', logs=logs, user_map=user_map)

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


def run_schema_migrations():
    """Простейшие миграции схемы без Alembic."""
    db.metadata.create_all(db.engine, tables=[UserReport.__table__, AdminActionLog.__table__])
    inspector = inspect(db.engine)
    statements = []
    table_names = set(inspector.get_table_names())

    if 'user' in table_names:
        user_columns = {col['name'] for col in inspector.get_columns('user')}
        if 'role' not in user_columns:
            statements.append('ALTER TABLE "user" ADD COLUMN role VARCHAR(20) DEFAULT \'user\'')
        if 'is_blocked' not in user_columns:
            statements.append('ALTER TABLE "user" ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE')
        if 'blocked_until' not in user_columns:
            statements.append('ALTER TABLE "user" ADD COLUMN blocked_until TIMESTAMP')
        if 'chat_muted_until' not in user_columns:
            statements.append('ALTER TABLE "user" ADD COLUMN chat_muted_until TIMESTAMP')
        if 'role' in user_columns:
            statements.append('UPDATE "user" SET role = \'user\' WHERE role IS NULL')
        if 'is_blocked' in user_columns:
            statements.append('UPDATE "user" SET is_blocked = FALSE WHERE is_blocked IS NULL')

    if 'user_report' in table_names:
        user_report_columns = {col['name'] for col in inspector.get_columns('user_report')}
        if 'group_message_id' not in user_report_columns:
            statements.append('ALTER TABLE user_report ADD COLUMN group_message_id INTEGER')

    if 'message' in table_names:
        message_columns = {col['name'] for col in inspector.get_columns('message')}
        if 'reply_to_id' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN reply_to_id INTEGER')
        if 'attachment_filename' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN attachment_filename VARCHAR(255)')
        if 'attachment_original_name' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN attachment_original_name VARCHAR(255)')
        if 'attachment_mime_type' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN attachment_mime_type VARCHAR(120)')
        if 'attachment_size' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN attachment_size INTEGER')
        if 'attachment_type' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN attachment_type VARCHAR(20)')
        if 'delivered_at' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN delivered_at TIMESTAMP')
        if 'edited_at' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN edited_at TIMESTAMP')
        if 'deleted_at' not in message_columns:
            statements.append('ALTER TABLE message ADD COLUMN deleted_at TIMESTAMP')

    if 'study_group_message' in table_names:
        group_message_columns = {col['name'] for col in inspector.get_columns('study_group_message')}
        if 'reply_to_id' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN reply_to_id INTEGER')
        if 'attachment_filename' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN attachment_filename VARCHAR(255)')
        if 'attachment_original_name' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN attachment_original_name VARCHAR(255)')
        if 'attachment_mime_type' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN attachment_mime_type VARCHAR(120)')
        if 'attachment_size' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN attachment_size INTEGER')
        if 'attachment_type' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN attachment_type VARCHAR(20)')
        if 'edited_at' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN edited_at TIMESTAMP')
        if 'deleted_at' not in group_message_columns:
            statements.append('ALTER TABLE study_group_message ADD COLUMN deleted_at TIMESTAMP')

    if not statements:
        return

    for statement in statements:
        db.session.execute(text(statement))
    db.session.commit()


# Создание таблиц при первом запуске
def create_tables():
    with app.app_context():
        db.create_all()
        run_schema_migrations()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        run_schema_migrations()
    app.run(host="127.0.0.1", port=5000, debug=True)
