import logging
import sqlite3
import os
import sys
import random
import uuid
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext,
    JobQueue,
)

import calendar

# Состояния для диалогов
SELECT_TASK_NAME = 0
SELECT_PRIORITY = 1
SELECT_YEAR, SELECT_MONTH, SELECT_DAY, SELECT_TIME = range(2, 6)
DEADLINE = 6
SELECT_TASK_TO_DELETE = 7
TEAM_MENU = 8
JOIN_TEAM = 9
DISBAND_TEAM = 10
CREATE_NEW_TEAM = 11
DELETE_TEAM = 12

# Инициализация базы данных
db_path = "tasks.db"

# Главная клавиатура
main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("Добавить задачу"), KeyboardButton("О создателе")],
    [KeyboardButton("Удалить задачу"), KeyboardButton("team")],
    [KeyboardButton("main")],
], resize_keyboard=True)

# Подменю команды
team_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Вступить", callback_data="join")],
    [InlineKeyboardButton("Расформировать", callback_data="disband")],
    [InlineKeyboardButton("Создать новую", callback_data="create_new")],
    [InlineKeyboardButton("Удалить", callback_data="delete")],
    [InlineKeyboardButton("Отмена", callback_data="cancel")],
])

# Пул фраз для уведомлений
deadline_phrases = [
    "Упс! Осталось мало времени!",
    "Поторопись, дедлайн близко!",
    "Скользи быстрее, как пингвин!",
    "Хоп-хоп, давай скорей!",
    "Время тикает, дружок!",
    "Не упусти момент!",
    "Давай, ты справишься!",
    "Быстрее-быстрее, ура!",
    "Последний рывок — вперед!",
    "Мы в тебя верим! 🐧",
]

# Инициализация и миграция базы данных
def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Сначала создаем таблицу tasks, если она еще не существует
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            deadline TEXT,
            chat_id INTEGER NOT NULL
        )
    """)
    
    # Создаем таблицу users перед миграцией tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            team_key TEXT
        )
    """)
    
    # Теперь проверяем и добавляем столбец team_key в tasks
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'team_key' not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN team_key TEXT")
        cursor.execute("""
            UPDATE tasks 
            SET team_key = (SELECT team_key FROM users WHERE users.user_id = tasks.user_id LIMIT 1)
            WHERE team_key IS NULL
        """)
    
    conn.commit()
    conn.close()

# Функция для получения или создания team_key
def get_or_create_team_key(user_id):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT team_key FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        team_key = result[0]
    else:
        team_key = str(uuid.uuid4())[:8]
        cursor.execute("INSERT OR REPLACE INTO users (user_id, team_key) VALUES (?, ?)", (user_id, team_key))
        conn.commit()
    
    conn.close()
    return team_key

# Функция для получения и форматирования списка задач
async def show_tasks(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    team_key = get_or_create_team_key(user_id)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, description, priority, deadline FROM tasks WHERE team_key = ?", (team_key,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        message = f"Список задач пуст.\nВаш командный ключ:\n```\n{team_key}\n```\n\n"
    else:
        message = f"Список задач (командный ключ:\n```\n{team_key}\n```):\n"
        for row in rows:
            task_id, description, priority, deadline = row
            message += f"ID: {task_id}\nОписание: {description}\nПриоритет: {priority}\nДедлайн: {deadline}\n\n"
        message += "Выберите действие:"

    if update.message:
        await update.message.reply_text(message, reply_markup=main_keyboard, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.message.reply_text(message, reply_markup=main_keyboard, parse_mode='Markdown')

# Обработчик команды /start
async def start(update: Update, context: CallbackContext) -> None:
    context.user_data['chat_id'] = update.message.chat_id
    context.user_data['user_id'] = update.effective_user.id
    await update.message.reply_text("Привет! Я бот для управления задачами.")
    await show_tasks(update, context)

# Информация о создателе
# Информация о создателе с копируемым адресом TON-кошелька
async def about_creator(update: Update, context: CallbackContext) -> None:
    message = (
        "О создателе:\n"
        "Привет! ✌️\n"
        "Я разработчик этого бота. 😉\n"
        "Создал его, чтобы помочь людям организовывать свои задачи. 🪄\n\n"
        "Если хотите поддержать развитие проекта, можете отправить TON-коины 💎:\n"
        "Мой кошелек:\n"
        "```\n"
        "ton key\n"
        "```\n"
        "Скопируйте адрес выше и используйте его в вашем TON-кошельке.\n\n"
        "Спасибо за использование бота! 😻"
    )
    await update.message.reply_text(message, reply_markup=main_keyboard, parse_mode='Markdown')

# Функция для проверки дедлайнов и отправки уведомлений
async def check_deadlines(context: CallbackContext) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, description, priority, deadline, chat_id, team_key FROM tasks")
    rows = cursor.fetchall()
    conn.close()

    now = datetime.now()
    notify_thresholds = [timedelta(hours=24), timedelta(hours=1)]

    for row in rows:
        task_id, user_id, description, priority, deadline_str, chat_id, team_key = row
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
            time_left = deadline - now

            for threshold in notify_thresholds:
                if timedelta(0) < time_left <= threshold:
                    notified_key = f"notified_{task_id}_{threshold.total_seconds()}_{user_id}"
                    if not context.user_data.get(notified_key):
                        hours_left = int(time_left.total_seconds() // 3600)
                        minutes_left = int((time_left.total_seconds() % 3600) // 60)
                        time_str = f"{hours_left} ч {minutes_left} мин" if hours_left > 0 else f"{minutes_left} мин"
                        random_phrase = random.choice(deadline_phrases)
                        message = (
                            f"{random_phrase}\n"
                            f"Задача: {description}\n"
                            f"Приоритет: {priority}\n"
                            f"Дедлайн: {deadline_str}\n"
                            f"Осталось: {time_str}"
                        )
                        if chat_id:
                            await context.bot.send_message(chat_id=chat_id, text=message)
                            context.user_data[notified_key] = True
                        else:
                            logging.warning(f"Chat ID отсутствует для задачи ID {task_id}")
        except ValueError as e:
            logging.error(f"Ошибка парсинга даты для задачи ID {task_id}: {e}")

# Начало добавления задачи
async def add_task(update: Update, context: CallbackContext) -> int:
    context.user_data['user_id'] = update.effective_user.id
    context.user_data['chat_id'] = update.message.chat_id
    context.user_data['team_key'] = get_or_create_team_key(context.user_data['user_id'])
    await update.message.reply_text("Введите название задачи:")
    return SELECT_TASK_NAME

# Обработка ввода названия задачи
async def process_task_name(update: Update, context: CallbackContext) -> int:
    task_name = update.message.text.strip()
    if not task_name:
        await update.message.reply_text("Название задачи не может быть пустым. Пожалуйста, введите название снова.")
        return SELECT_TASK_NAME

    context.user_data["description"] = task_name
    logging.info(f"Задача получена: {task_name}. Переход к выбору приоритета.")

    keyboard = [
        [InlineKeyboardButton("Низкий 🟢", callback_data="priority_низкий")],
        [InlineKeyboardButton("Средний 🟨", callback_data="priority_средний")],
        [InlineKeyboardButton("Высокий ⚠️", callback_data="priority_высокий")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите приоритет:", reply_markup=reply_markup)
    return SELECT_PRIORITY

# Обработка выбора приоритета
async def process_priority(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    priority = query.data.split("_")[1]
    context.user_data["priority"] = priority

    logging.info(f"Выбран приоритет: {priority}. Переход к выбору дедлайна.")
    await query.edit_message_text(f"Приоритет выбран: {priority}. Теперь выберите дедлайн.")
    next_state = await start_deadline_selection(query, context)
    logging.info(f"Состояние после start_deadline_selection: {next_state}")
    return next_state

# Начало выбора дедлайна
async def start_deadline_selection(query: CallbackQuery, context: CallbackContext) -> int:
    current_year = datetime.now().year
    years = [current_year, current_year + 1, current_year + 2]

    keyboard = [[InlineKeyboardButton(str(year), callback_data=f"year_{year}") for year in years]]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_priority")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    logging.info("Открывается выбор года. Клавиатура сформирована.")
    await query.edit_message_text("Выберите год:", reply_markup=reply_markup)
    return SELECT_YEAR

# Выбор года для дедлайна
async def select_year(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    year = int(query.data.split("_")[1])
    context.user_data["deadline_year"] = year

    months = []
    for i in range(1, 13):
        months.append([InlineKeyboardButton(calendar.month_name[i], callback_data=f"month_{i}")])

    reply_markup = InlineKeyboardMarkup(months)
    logging.info(f"Выбран год: {year}")
    await query.edit_message_text(f"Вы выбрали год: {year}. Теперь выберите месяц:", reply_markup=reply_markup)
    return SELECT_MONTH

# Обработка выбора месяца
async def select_month(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "back":
        logging.info("Возврат к выбору года")
        return await start_deadline_selection(query, context)

    month = int(query.data.split("_")[1])
    context.user_data["deadline_month"] = month

    year = context.user_data["deadline_year"]
    days_in_month = calendar.monthrange(year, month)[1]

    days = []
    for day in range(1, days_in_month + 1):
        days.append([InlineKeyboardButton(str(day), callback_data=f"day_{day}")])

    days.append([InlineKeyboardButton("Назад", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(days)
    logging.info(f"Выбран месяц: {calendar.month_name[month]}")
    await query.edit_message_text(f"Вы выбрали месяц: {calendar.month_name[month]}. Теперь выберите день:", reply_markup=reply_markup)
    return SELECT_DAY

# Обработка выбора дня
async def select_day(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "back":
        logging.info("Возврат к выбору месяца")
        return await select_month(update, context)

    day = int(query.data.split("_")[1])
    context.user_data["deadline_day"] = day

    times = []
    for hour in range(8, 21):
        for minute in range(0, 60, 15):
            time_str = f"{hour:02d}:{minute:02d}"
            times.append(InlineKeyboardButton(time_str, callback_data=f"time_{time_str}"))

    keyboard = [times[i:i + 4] for i in range(0, len(times), 4)]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    logging.info(f"Выбран день: {day}")
    await query.edit_message_text(f"Вы выбрали день: {day}. Теперь выберите время:", reply_markup=reply_markup)
    return SELECT_TIME

# Обработка выбора времени
async def select_time(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "back":
        logging.info("Возврат к выбору дня")
        return await select_day(update, context)

    time_str = query.data.split("_")[1]
    context.user_data["deadline_time"] = time_str

    year = context.user_data["deadline_year"]
    month = context.user_data["deadline_month"]
    day = context.user_data["deadline_day"]

    full_datetime = f"{year}-{month:02d}-{day:02d} {time_str}"
    context.user_data["deadline"] = full_datetime

    logging.info(f"Выбран дедлайн: {full_datetime}")
    await query.edit_message_text(f"Вы выбрали дедлайн: {full_datetime}.", reply_markup=None)
    return DEADLINE

# Сохранение задачи
async def process_deadline(update: Update, context: CallbackContext) -> int:
    deadline = context.user_data.get('deadline')
    user_id = context.user_data.get('user_id')
    chat_id = context.user_data.get('chat_id')
    team_key = context.user_data.get('team_key')

    if deadline is None or user_id is None or chat_id is None or team_key is None:
        await update.message.reply_text("Произошла ошибка. Данные неполные.")
        return ConversationHandler.END

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tasks (user_id, description, priority, deadline, chat_id, team_key) VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, context.user_data['description'], context.user_data['priority'], deadline, chat_id, team_key)
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        await update.message.reply_text(f"Задача успешно добавлена! ID задачи: {task_id}")
        await show_tasks(update, context)
        return ConversationHandler.END
    except Exception as e:
        logging.error(f"Ошибка сохранения задачи: {e}")
        await update.message.reply_text("Произошла ошибка при добавлении задачи.")
        await show_tasks(update, context)
        return ConversationHandler.END

# Обработка меню команды
async def team_menu(update: Update, context: CallbackContext) -> int:
    context.user_data['user_id'] = update.effective_user.id
    team_key = get_or_create_team_key(context.user_data['user_id'])
    await update.message.reply_text(f"Текущий командный ключ: `{team_key}`\nВыберите действие:", reply_markup=team_keyboard, parse_mode='Markdown')
    return TEAM_MENU

# Вступление в команду
async def join_team(update: Update, context: CallbackContext) -> int:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("Введите командный ключ для вступления:")
    return JOIN_TEAM

async def process_join_team(update: Update, context: CallbackContext) -> int:
    team_key = update.message.text.strip()
    user_id = context.user_data['user_id']
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT team_key FROM users WHERE team_key = ?", (team_key,))
    result = cursor.fetchone()
    
    if result:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, team_key) VALUES (?, ?)", (user_id, team_key))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"Вы успешно вступили в команду с ключом `{team_key}`!", parse_mode='Markdown')
        await show_tasks(update, context)
        return ConversationHandler.END
    else:
        conn.close()
        await update.message.reply_text("Неверный командный ключ. Попробуйте еще раз.")
        return JOIN_TEAM

# Расформирование команды
async def disband_team(update: Update, context: CallbackContext) -> int:
    await update.callback_query.answer()
    user_id = context.user_data['user_id']
    team_key = get_or_create_team_key(user_id)
    await update.callback_query.message.reply_text(
        f"Вы уверены, что хотите расформировать команду `{team_key}`? Это уберет ваш доступ к текущим задачам. (да/нет)", 
        parse_mode='Markdown'
    )
    return DISBAND_TEAM

async def process_disband_team(update: Update, context: CallbackContext) -> int:
    response = update.message.text.lower()
    user_id = context.user_data['user_id']
    team_key = get_or_create_team_key(user_id)
    
    if response == "да":
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET team_key = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("Вы покинули команду. Теперь у вас индивидуальный доступ к задачам.")
        await show_tasks(update, context)
        return ConversationHandler.END
    elif response == "нет":
        await update.message.reply_text("Действие отменено.")
        await show_tasks(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, ответьте 'да' или 'нет'.")
        return DISBAND_TEAM

# Создание новой команды
async def create_new_team(update: Update, context: CallbackContext) -> int:
    await update.callback_query.answer()
    user_id = context.user_data['user_id']
    new_team_key = str(uuid.uuid4())[:8]
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, team_key) VALUES (?, ?)", (user_id, new_team_key))
    conn.commit()
    conn.close()
    
    await update.callback_query.message.reply_text(f"Создана новая команда с ключом: `{new_team_key}`", parse_mode='Markdown')
    await show_tasks(update, context)
    return ConversationHandler.END

# Удаление команды
async def delete_team(update: Update, context: CallbackContext) -> int:
    await update.callback_query.answer()
    user_id = context.user_data['user_id']
    team_key = get_or_create_team_key(user_id)
    await update.callback_query.message.reply_text(
        f"Вы уверены, что хотите удалить команду `{team_key}`? Это удалит все связанные задачи. (да/нет)", 
        parse_mode='Markdown'
    )
    return DELETE_TEAM

async def process_delete_team(update: Update, context: CallbackContext) -> int:
    response = update.message.text.lower()
    user_id = context.user_data['user_id']
    team_key = get_or_create_team_key(user_id)
    
    if response == "да":
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE team_key = ?", (team_key,))
        cursor.execute("UPDATE users SET team_key = NULL WHERE team_key = ?", (team_key,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"Команда `{team_key}` и все её задачи удалены.", parse_mode='Markdown')
        await show_tasks(update, context)
        return ConversationHandler.END
    elif response == "нет":
        await update.message.reply_text("Действие отменено.")
        await show_tasks(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Пожалуйста, ответьте 'да' или 'нет'.")
        return DELETE_TEAM

# Удаление задачи
async def delete_task(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    team_key = get_or_create_team_key(user_id)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, description FROM tasks WHERE team_key = ?", (team_key,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Список задач пуст.", reply_markup=main_keyboard)
        return ConversationHandler.END

    keyboard = []
    for row in rows:
        task_id, description = row
        description = description[:20] + "..." if len(description) > 20 else description
        button = InlineKeyboardButton(f"{description} (ID: {task_id})", callback_data=f"delete_{task_id}")
        keyboard.append([button])

    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите задачу для удаления:", reply_markup=reply_markup)
    return SELECT_TASK_TO_DELETE

# Подтверждение удаления задачи
async def confirm_delete_task(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("Действие отменено.")
        await show_tasks(update, context)
        return ConversationHandler.END

    task_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id
    team_key = get_or_create_team_key(user_id)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT description FROM tasks WHERE id = ? AND team_key = ?", (task_id, team_key))
        task = cursor.fetchone()
        if not task:
            await query.edit_message_text("Задача не найдена или не принадлежит вашей команде.")
            await show_tasks(update, context)
            conn.close()
            return ConversationHandler.END
        
        cursor.execute("DELETE FROM tasks WHERE id = ? AND team_key = ?", (task_id, team_key))
        conn.commit()
        conn.close()
        
        logging.info(f"Task with ID {task_id} deleted successfully for team {team_key}.")
        await query.message.reply_text(f"Задача с ID {task_id} успешно удалена.")
        await show_tasks(update, context)
    except sqlite3.Error as e:
        logging.error(f"Database error while deleting task: {e}")
        await query.edit_message_text("Ошибка при удалении.")
        await show_tasks(update, context)
        return ConversationHandler.END

    return ConversationHandler.END

# Перезапуск бота
async def restart_bot(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Бот перезапущен.", reply_markup=main_keyboard)
    python = sys.executable
    os.execl(python, python, *sys.argv)

# Отмена действия
async def cancel(update: Update, context: CallbackContext) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Действие отменено.")
    else:
        await update.message.reply_text("Действие отменено.")
    await show_tasks(update, context)
    return ConversationHandler.END

# Обработка текстовых сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    if text == "Добавить задачу":
        return await add_task(update, context)
    elif text == "О создателе":
        return await about_creator(update, context)
    elif text == "Удалить задачу":
        return await delete_task(update, context)
    elif text == "team":
        return await team_menu(update, context)
    elif text == "Перезапустить бота":
        return await restart_bot(update, context)
    elif text == "Отмена":
        return await cancel(update, context)
    elif text == "main":
        return await start(update, context)
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, используйте кнопки.", reply_markup=main_keyboard)

# Обработка callback-запросов для меню команды
async def handle_team_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    action = query.data

    if action == "join":
        return await join_team(update, context)
    elif action == "disband":
        return await disband_team(update, context)
    elif action == "create_new":
        return await create_new_team(update, context)
    elif action == "delete":
        return await delete_team(update, context)
    elif action == "cancel":
        return await cancel(update, context)
    return TEAM_MENU

# Регистрация ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Добавить задачу)$"), add_task),
        MessageHandler(filters.Regex("^(Удалить задачу)$"), delete_task),
        MessageHandler(filters.Regex("^(team)$"), team_menu),
    ],
    states={
        SELECT_TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_task_name)],
        SELECT_PRIORITY: [CallbackQueryHandler(process_priority)],
        SELECT_YEAR: [CallbackQueryHandler(select_year)],
        SELECT_MONTH: [CallbackQueryHandler(select_month)],
        SELECT_DAY: [CallbackQueryHandler(select_day)],
        SELECT_TIME: [CallbackQueryHandler(select_time)],
        DEADLINE: [MessageHandler(filters.TEXT, process_deadline)],
        SELECT_TASK_TO_DELETE: [CallbackQueryHandler(confirm_delete_task)],
        TEAM_MENU: [CallbackQueryHandler(handle_team_callback)],
        JOIN_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_join_team)],
        DISBAND_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_disband_team)],
        CREATE_NEW_TEAM: [CallbackQueryHandler(create_new_team)],
        DELETE_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_delete_team)],
    },
    fallbacks=[
        MessageHandler(filters.Regex("^(Отмена)$"), cancel),
        CommandHandler("cancel", cancel),
    ]
)

# Настройка логгирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Главная функция
def main() -> None:
    init_db()

    BOT_TOKEN = "telegram token"

    application = Application.builder().token(BOT_TOKEN).build()

    job_queue = application.job_queue
    if job_queue is not None:
        job_queue.run_repeating(check_deadlines, interval=300, first=10)
    else:
        logging.error("JobQueue не инициализирован. Убедитесь, что установлена версия python-telegram-bot с [job-queue].")

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()