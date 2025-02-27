# ToDoPenguinBot 🐧

![Python](https://img.shields.io/badge/Python-3.13-blue.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot_API-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

**ToDoPenguinBot** — это Telegram-бот для управления задачами, разработанный как дипломная работа студента [Ваше имя]. Бот помогает пользователям организовывать свои личные и командные задачи с использованием удобного интерфейса прямо в мессенджере Telegram.

---

## Проблема ведения задач

В современном мире люди сталкиваются с огромным количеством задач: от личных дел, таких как покупка продуктов, до рабочих проектов, требующих координации с командой. Без правильной организации задачи легко теряются, дедлайны пропускаются, а хаос в расписании приводит к стрессу и снижению продуктивности. Существующие инструменты управления задачами часто сложны, требуют отдельного приложения или не подходят для быстрого доступа и совместной работы. Например:

- **Разрозненность**: Заметки в блокноте, напоминания в телефоне и рабочие чаты остаются несвязанными.
- **Отсутствие уведомлений**: Без своевременных напоминаний о дедлайнах задачи забываются.
- **Сложность совместной работы**: Традиционные менеджеры задач не всегда интуитивны для командного взаимодействия без долгого обучения.

Эти проблемы особенно актуальны для студентов, фрилансеров и небольших команд, которым нужен простой, доступный и интегрированный инструмент.

---

## Цель проекта

Цель создания **ToDoPenguinBot** — разработать минималистичный, но мощный инструмент для управления задачами, который решает перечисленные проблемы:
1. **Доступность**: Бот работает в Telegram, платформе, которая уже установлена у миллионов пользователей, устраняя необходимость в дополнительных приложениях.
2. **Простота**: Интуитивный интерфейс с кнопками делает управление задачами быстрым и понятным даже для новичков.
3. **Уведомления**: Автоматические напоминания о приближающихся дедлайнах помогают не пропустить важное.
4. **Командная работа**: Поддержка совместного ведения задач через уникальный ключ команды позволяет легко координировать действия между участниками.
5. **Образовательная ценность**: Как дипломная работа, проект демонстрирует навыки программирования на Python, работы с базами данных SQLite и интеграции с Telegram API.

Бот был создан, чтобы доказать, что управление задачами может быть одновременно простым, мобильным и эффективным, а также чтобы показать практическое применение современных технологий в решении повседневных проблем.

---

## Функционал

**ToDoPenguinBot** предлагает следующие возможности:

- **Создание задач**:
  - Добавление задачи с названием, приоритетом (низкий, средний, высокий) и дедлайном.
  - Удобный выбор даты и времени через инлайн-клавиатуры.

- **Просмотр задач**:
  - Отображение списка задач с ID, описанием, приоритетом и дедлайном через кнопку "main".

- **Удаление задач**:
  - Удаление конкретной задачи по её ID с подтверждением действия.

- **Уведомления**:
  - Автоматические напоминания за 24 часа и 1 час до дедлайна с случайными мотивационными фразами.

- **Командная работа**:
  - Генерация уникального ключа команды (`team_key`) для каждого пользователя.
  - Подменю "team" с опциями:
    - **Вступить**: Присоединение к существующей команде по ключу.
    - **Расформировать**: Выход из текущей команды без удаления задач.
    - **Создать новую**: Генерация нового ключа команды.
    - **Удалить**: Удаление команды и всех её задач с подтверждением.

- **Поддержка проекта**:
  - Информация о создателе с копируемым TON-адресом для донатов через кнопку "О создателе".

---

## Установка

### Требования
- Python 3.13+
- Зависимости из `requirements.txt`

### Установка зависимостей
1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/[ваш-username]/ToDoPenguinBot.git
   cd ToDoPenguinBot

# Спасибо за внимание к проекту! 🐧

## О дипломной работе

Этот проект является дипломной работой Тимофея, выполненной в рамках обучения в 2025 году. Целью работы было не только создание практичного инструмента, но и демонстрация навыков разработки, включая:

- Проектирование архитектуры бота.
- Интеграцию с внешними API (Telegram).
- Управление базой данных.
- Реализацию асинхронного программирования.

Проект успешно решает задачу упрощения ведения задач и доказывает эффективность использования мессенджеров как платформы для повседневных инструментов.
