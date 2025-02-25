import logging
import sqlite3
import os
import sys
import random
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
DEADLINE = 6  # Завершение выбора дедлайна
SELECT_TASK_TO_DELETE = 7  # Выбор задачи для удаления

# Инициализация базы данных
db_path = "tasks.db"

# Главная клавиатура
main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("Добавить задачу"), KeyboardButton("Посмотреть задачи")],
    [KeyboardButton("Удалить задачу"), KeyboardButton("Перезапустить бота")],
    [KeyboardButton("main")],
], resize_keyboard=True)

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


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            priority TEXT NOT NULL,
            deadline TEXT
        )
    """)
    conn.commit()
    conn.close()


# Функция для получения и форматирования списка задач
async def show_tasks(update: Update, context: CallbackContext) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, description, priority, deadline FROM tasks")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        message = "Список задач пуст.\n\nВыберите действие:"
    else:
        message = "Список задач:\n"
        for row in rows:
            task_id, description, priority, deadline = row
            message += f"ID: {task_id}\nОписание: {description}\nПриоритет: {priority}\nДедлайн: {deadline}\n\n"
        message += "Выберите действие:"

    if update.message:  # Если вызвано через сообщение
        await update.message.reply_text(message, reply_markup=main_keyboard)
    elif update.callback_query:  # Если вызвано через callback
        await update.callback_query.message.reply_text(message, reply_markup=main_keyboard)


# Обработчик команды /start
async def start(update: Update, context: CallbackContext) -> None:
    context.user_data['chat_id'] = update.message.chat_id  # Сохраняем chat_id
    await update.message.reply_text("Привет! Я бот для управления задачами.")
    await show_tasks(update, context)


# Функция для проверки дедлайнов и отправки уведомлений
async def check_deadlines(context: CallbackContext) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, description, priority, deadline FROM tasks")
    rows = cursor.fetchall()
    conn.close()

    now = datetime.now()
    notify_thresholds = [timedelta(hours=24), timedelta(hours=1)]

    for row in rows:
        task_id, description, priority, deadline_str = row
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
            time_left = deadline - now

            for threshold in notify_thresholds:
                if timedelta(0) < time_left <= threshold:
                    notified_key = f"notified_{task_id}_{threshold.total_seconds()}"
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
                        chat_id = context.user_data.get('chat_id')
                        if chat_id:
                            await context.bot.send_message(chat_id=chat_id, text=message)
                            context.user_data[notified_key] = True
                        else:
                            logging.warning("Chat ID не найден, уведомление не отправлено.")
        except ValueError as e:
            logging.error(f"Ошибка парсинга даты для задачи ID {task_id}: {e}")


# Начало добавления задачи (ввод названия)
async def add_task(update: Update, context: CallbackContext) -> int:
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

    # Отображаем клавиатуру для выбора приоритета
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
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_priority")])  # Добавляем кнопку "Назад"
    reply_markup = InlineKeyboardMarkup(keyboard)

    logging.info("Открывается выбор года. Клавиатура сформирована.")
    await query.edit_message_text("Выберите год:", reply_markup=reply_markup)
    return SELECT_YEAR

# Выбор года для дедлайна
async def select_year(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    year = int(query.data.split("_")[1])  # Получаем выбранный год
    context.user_data["deadline_year"] = year

    months = []  # Создаем клавиатуру для выбора месяцев
    for i in range(1, 13):
        months.append([InlineKeyboardButton(calendar.month_name[i], callback_data=f"month_{i}")])

    reply_markup = InlineKeyboardMarkup(months)  # Формируем клавиатуру
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

    logging.info(f"Выбран дедла1цн: {full_datetime}")
    await query.edit_message_text(f"Вы выбрали дедлайн: {full_datetime}.", reply_markup=None)
    return DEADLINE


# Возврат к началу выбора дедлайна
async def handle_back_to_start(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    return await start_deadline_selection(query, context)


# Сохранение задачи
async def process_deadline(update: Update, context: CallbackContext) -> int:
    deadline = context.user_data.get('deadline')

    if deadline is None:
        await update.message.reply_text("Произошла ошибка. Дедлайн не был выбран.")
        return ConversationHandler.END

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO tasks (description, priority, deadline) VALUES (?, ?, ?)""",
            (context.user_data['description'], context.user_data['priority'], deadline)
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        await update.message.reply_text(f"Задача успешно добавлена! ID задачи: {task_id}")
        await show_tasks(update, context)
        return ConversationHandler.END
    except Exception as e:
        logging.error(f"Ошибка сохранения задачи в базу данных: {e}")
        await update.message.reply_text("Произошла ошибка при добавлении задачи. Попробуйте снова.")
        await show_tasks(update, context)
        return ConversationHandler.END


# Просмотр задач
async def view_tasks(update: Update, context: CallbackContext) -> None:
    await show_tasks(update, context)


# Удаление задачи
async def delete_task(update: Update, context: CallbackContext) -> int:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, description FROM tasks")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Список задач пуст.", reply_markup=main_keyboard)
        return ConversationHandler.END

    logging.info(f"Tasks found: {rows}")

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

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT description FROM tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            await query.edit_message_text("Задача не найдена.")
            await show_tasks(update, context)
            conn.close()
            return ConversationHandler.END
        
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        
        logging.info(f"Task with ID {task_id} deleted successfully.")
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
    await update.message.reply_text("Действие отменено.")
    await show_tasks(update, context)
    return ConversationHandler.END


# Обработка текстовых сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    if text == "Добавить задачу":
        return await add_task(update, context)
    elif text == "Посмотреть задачи":
        return await view_tasks(update, context)
    elif text == "Удалить задачу":
        return await delete_task(update, context)
    elif text == "Перезапустить бота":
        return await restart_bot(update, context)
    elif text == "Отмена":
        return await cancel(update, context)
    elif text == "main":
        return await start(update, context)
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, используйте кнопки.", reply_markup=main_keyboard)


# Регистрация ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(Добавить задачу)$"), add_task),
        MessageHandler(filters.Regex("^(Удалить задачу)$"), delete_task),
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
    },
    fallbacks=[  # Обработчики для выхода из диалога
        MessageHandler(filters.Regex("^(Отмена)$"), cancel),
        CommandHandler("cancel", cancel),  # Дополнительная команда /cancel
    ]
)

# Настройка логгирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


# Главная функция
def main() -> None:
    init_db()

    BOT_TOKEN = "76"

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

