from pyrogram import Client, filters
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import enum
import threading
import time
from pyrogram.errors import BotBlocked, UserDeactivated

# Настройки бота
api_id = 'YOUR_API_ID'  # ваш API ID
api_hash = 'YOUR_API_HASH'  #  ваш API Hash
bot_token = 'YOUR_BOT_TOKEN'  #  ваш токен бота

# Настройка SQLAlchemy
Base = declarative_base()
engine = create_engine('sqlite:///users.db', echo=True)
Session = sessionmaker(bind=engine)
session = Session()


# Определение статусов пользователя
class UserStatus(enum.Enum):
    alive = "alive"
    dead = "dead"
    finished = "finished"


# Определение модели пользователя
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(Enum(UserStatus), default=UserStatus.alive)
    status_updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    first_message_sent_at = Column(DateTime, nullable=True)
    second_message_sent_at = Column(DateTime, nullable=True)
    trigger1_received_at = Column(DateTime, nullable=True)
    third_message_due = Column(DateTime, nullable=True)


# Создание таблицы
Base.metadata.create_all(engine)

# Инициализация бота
app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)


# Функция проверки наличия ключевых слов в сообщении
def contains_stopwords(text):
    stopwords = ["прекрасно", "ожидать"]
    return any(word in text.lower() for word in stopwords)


# Функция отправки первого и второго сообщений
def send_delayed_messages(client, user):
    try:
        time.sleep(360)  # Задержка 6 минут (360 секунд)

        # Проверка наличия ключевых слов в последних сообщениях
        messages = client.get_chat_history(user.user_id, limit=1)
        if messages and contains_stopwords(messages[0].text):
            return  # Прекращаем работу, если найдено ключевое слово

        # Отправка первого сообщения
        client.send_message(user.user_id, "Текст1")
        user.first_message_sent_at = datetime.datetime.utcnow()
        user.status = UserStatus.finished
        user.status_updated_at = datetime.datetime.utcnow()
        session.commit()

        # Проверка на отправку второго сообщения через 39 минут
        for _ in range(2340):  # Проверяем каждую секунду в течение 39 минут (2340 секунд)
            messages = client.get_chat_history(user.user_id, limit=1)
            if messages and "триггер1" in messages[0].text.lower():
                user.trigger1_received_at = datetime.datetime.utcnow()
                user.third_message_due = user.trigger1_received_at + datetime.timedelta(days=1, hours=2)
                session.commit()
                return  # Прекращаем работу, если найдено слово "Триггер1"
            time.sleep(1)

        # Отправка второго сообщения
        client.send_message(user.user_id, "Текст2")
        user.second_message_sent_at = datetime.datetime.utcnow()
        user.third_message_due = user.second_message_sent_at + datetime.timedelta(days=1, hours=2)
        session.commit()
    except (BotBlocked, UserDeactivated):
        user.status = UserStatus.dead
        user.status_updated_at = datetime.datetime.utcnow()
        session.commit()


# Функция для проверки и отправки сообщений пользователям
def check_and_send_messages():
    while True:
        users = session.query(User).filter_by(status=UserStatus.alive).all()
        for user in users:
            # Проверка необходимости отправки первого сообщения
            if datetime.datetime.utcnow() - user.created_at >= datetime.timedelta(minutes=6):
                threading.Thread(target=send_delayed_messages, args=(app, user)).start()
                user.status = UserStatus.finished
                user.status_updated_at = datetime.datetime.utcnow()
                session.commit()

            # Проверка необходимости отправки третьего сообщения
            if user.third_message_due and datetime.datetime.utcnow() >= user.third_message_due:
                try:
                    app.send_message(user.user_id, "Текст3")
                    user.third_message_due = None
                    session.commit()
                except (BotBlocked, UserDeactivated):
                    user.status = UserStatus.dead
                    user.status_updated_at = datetime.datetime.utcnow()
                    session.commit()

        time.sleep(2)  # Пауза перед следующей проверкой


# Запуск потока для проверки и отправки сообщений
threading.Thread(target=check_and_send_messages, daemon=True).start()


# Команда старт
@app.on_message(filters.command("start"))
def start(client, message):
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверка наличия пользователя в базе данных
    user = session.query(User).filter_by(user_id=user_id).first()
    if not user:
        # Добавление нового пользователя
        new_user = User(user_id=user_id, username=username)
        session.add(new_user)
        session.commit()
        message.reply_text(f"Привет, {username}! Ты был добавлен в базу данных.")
    else:
        message.reply_text(f"С возвращением, {username}!")


# Пример команды для обновления статуса пользователя
@app.on_message(filters.command("update_status"))
def update_status(client, message):
    if len(message.command) != 2:
        message.reply_text("Использование: /update_status [alive|dead|finished]")
        return

    new_status_str = message.command[1]
    try:
        new_status = UserStatus[new_status_str]
    except KeyError:
        message.reply_text("Неверный статус. Используйте: alive, dead, finished")
        return

    user_id = message.from_user.id
    user = session.query(User).filter_by(user_id=user_id).first()
    if user:
        user.status = new_status
        user.status_updated_at = datetime.datetime.utcnow()
        session.commit()
        message.reply_text(f"Ваш статус обновлен на {new_status_str}.")
    else:
        message.reply_text("Пользователь не найден в базе данных.")


# Запуск бота
app.run()
