# AI Study Assistant Bot 🎓

**Умный Telegram-бот для решения учебных задач по фото с использованием Google Gemini API.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)
![Aiogram](https://img.shields.io/badge/Aiogram-3.x-blue?style=flat-square&logo=telegram&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-8E75B2?style=flat-square&logo=google&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## 📖 О проекте
Бот выступает в роли персонального репетитора. Пользователь отправляет фотографию задачи, теста, конспекта или кода, а бот с помощью мультимодальной нейросети (Gemini) распознает содержимое, выдает готовый ответ и подробный пошаговый разбор, как от учителя.

### ✨ Ключевые возможности:
*   **Интеграция с LLM:** Использование Google Gemini API для анализа изображений и генерации текста.
*   **Разделение задач:** Если на фото несколько заданий, бот распознает их и присылает решения по очереди.
*   **Форматирование:** Аккуратный вывод формул без сложного LaTeX (удобно читать с телефона).
*   **Личный архив:** Возможность сохранять нерешенные фото (или мемы) в личную галерею (команда `/saved`) с возможностью листать, удалять и очищать архив.
*   **Безопасность:** Whitelist-система (белый список). Ботом могут пользоваться только те, кого одобрил администратор. Реализовано через Middleware.
*   **Админ-панель:** Удобное управление доступом пользователей прямо из интерфейса бота (добавление/удаление по ID).

## 📸 Демонстрация
<!-- Сюда перетащи скриншоты из Телеграма (как бот решает задачу, как выглядит меню и архив) -->
<img width="1235" height="992" alt="image" src="https://github.com/user-attachments/assets/fb20bf09-6d71-4089-b7d0-8819cfa6bac4" />
<img width="1232" height="937" alt="image" src="https://github.com/user-attachments/assets/6edaa4f2-701b-4517-8694-81966cce8b01" />
<img width="1226" height="937" alt="image" src="https://github.com/user-attachments/assets/1c457b6e-98ac-4bac-a1ef-bb5963b258fa" />

## 🛠 Стек технологий
*   **Язык:** Python 3
*   **Фреймворк:** Aiogram 3 (асинхронный)
*   **AI/ML:** Google Generative AI (Gemini Pro/Flash)
*   **База данных:** SQLite3 (хранение пользователей и file_id фотографий)
*   **Работа с медиа:** Pillow (PIL)
*   **Инфраструктура:** Docker, Docker Compose (интеграция в общий стек `infra`)

## 🏗 Архитектура
Проект построен по модульному принципу. Для проверки доступа используется `AccessControlMiddleware`, который перехватывает все события (сообщения и колбэки) и проверяет ID пользователя в базе данных перед передачей управления хэндлерам. 

Состояние (сессии) и данные хранятся в локальной базе SQLite, что делает бота полностью автономным.

## 🚀 Быстрый старт (Локальный запуск)

### 1. Клонирование репозитория
```bash
git clone https://github.com/Gothrun/summarizer_bot.git
cd summarizer_bot
Создайте файл .env в корне проекта и укажите все необходимые ключи:
env
BOT_TOKEN=ваш_токен_от_BotFather
GEMINI_API_KEY=ваш_ключ_от_google_ai_studio
ADMIN_ID=ваш_telegram_id
Запуск через Docker Compose
bash
docker-compose up -d --build
