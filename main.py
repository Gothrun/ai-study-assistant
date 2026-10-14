import io
import os
import asyncio
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image

from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, TelegramObject,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from typing import Callable, Dict, Any, Awaitable
import google.generativeai as genai

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКА БАЗЫ ДАННЫХ
# ==========================================
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")

if not BOT_TOKEN or not GEMINI_API_KEY or not ADMIN_ID_RAW:
    print("❌ ОШИБКА: Проверь .env! Должны быть BOT_TOKEN, GEMINI_API_KEY и ADMIN_ID")
    exit(1)

ADMIN_ID = int(ADMIN_ID_RAW)

DB_PATH = Path(__file__).parent / "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id INTEGER PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Функции работы с Белым Списком (Whitelist) ---
def is_user_allowed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM allowed_users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def db_add_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO allowed_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def db_delete_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def db_get_allowed_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, added_at FROM allowed_users")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- Функции работы с сохраненными фото ---
def db_save_photo(user_id: int, file_id: str, description: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saved_photos (user_id, file_id, description) VALUES (?, ?, ?)",
        (user_id, file_id, description)
    )
    conn.commit()
    conn.close()

def db_get_user_photos(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, file_id, description, created_at FROM saved_photos WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_delete_photo(photo_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_photos WHERE id = ? AND user_id = ?", (photo_id, user_id))
    conn.commit()
    conn.close()

def db_clear_user_photos(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saved_photos WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==========================================
# 2. MIDDLEWARE ПРОВЕРКИ ДОСТУПА
# ==========================================
class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            user_id = user.id
            if is_user_allowed(user_id):
                return await handler(event, data)
            
            if isinstance(event, types.Message):
                await event.answer(
                    f"⛔ **У вас нет доступа к этому боту.**\n\n"
                    f"Ваш Telegram ID: `{user_id}`\n"
                    f"Отправьте этот ID администратору бота для получения доступа.",
                    parse_mode="Markdown"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ У вас нет доступа к боту.", show_alert=True)
            return
        return await handler(event, data)


# ==========================================
# 3. ИНИЦИАЛИЗАЦИЯ GEMINI И AIOGRAM
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)

def get_best_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority_models = ['models/gemini-3.6-flash', 'gemini-3.6-flash', 'models/gemini-1.5-flash']
        for target in priority_models:
            if target in models:
                return genai.GenerativeModel(target)
    except Exception as e:
        print(f"⚠️ Ошибка получения списка моделей: {e}")
    return genai.GenerativeModel('models/gemini-3.6-flash')

ai_model = get_best_model()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.message.outer_middleware(AccessControlMiddleware())
dp.callback_query.outer_middleware(AccessControlMiddleware())


# ==========================================
# 4. АДМИН-ПАНЕЛЬ (КНОПКИ ВНИЗУ ЭКРАНА)
# ==========================================
def get_admin_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Список пользователей")],
            [KeyboardButton(text="➕ Добавить пользователя"), KeyboardButton(text="🗑 Удалить пользователя")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

@dp.message(F.text == "👥 Список пользователей")
async def handle_list_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = db_get_allowed_users()
    text = f"👑 **Администратор:** `{ADMIN_ID}`\n\n👥 **Разрешенные пользователи ({len(users)}):**\n"
    if not users:
        text += "_Дополнительных пользователей пока нет._"
    else:
        for u_id, added_at in users:
            text += f"• `{u_id}` (добавлен: {added_at})\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text.in_({"➕ Добавить пользователя", "🗑 Удалить пользователя"}))
async def handle_manage_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    users = db_get_allowed_users()
    text = f"📋 **Текущие пользователи ({len(users)}):**\n"
    if not users:
        text += "_Список пуст._\n\n"
    else:
        for u_id, _ in users:
            text += f"• `{u_id}`\n"
        text += "\n"
        
    text += "✍️ **Просто отправь мне ID нужного человека цифрами** (например: `123456789`).\n"
    text += "💡 _Я сам пойму: если его нет в списке — добавлю, если есть — удалю._"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text.regexp(r'^\d+$'))
async def handle_id_input(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    target_id = int(message.text)
    if target_id == ADMIN_ID:
        await message.answer("❌ Нельзя изменить доступ самому себе!")
        return
        
    if is_user_allowed(target_id):
        db_delete_user(target_id)
        await message.answer(f"🗑 Пользователь `{target_id}` **УДАЛЕН** из белого списка!", parse_mode="Markdown")
    else:
        db_add_user(target_id)
        await message.answer(f"✅ Пользователь `{target_id}` **ДОБАВЛЕН** в белый список!", parse_mode="Markdown")


# ==========================================
# 5. ОСНОВНЫЕ ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Если пишет админ - показываем кнопки управления, если обычный юзер - убираем их
    kb = get_admin_reply_keyboard() if message.from_user.id == ADMIN_ID else ReplyKeyboardRemove()
    
    await message.answer(
        "🎓 **Привет! Я твой студенческий ассистент-репетитор.**\n\n"
        "📸 **Отправь мне фото:** задачи, слайда, теста или кода.\n"
        "• Если задач несколько — я решу их все и пришлю **по очереди**.\n"
        "• Если на фото нет задачи — скажу об этом и предложу сохранить в личный архив.\n\n"
        "📁 Посмотреть свои сохраненные фото можно командой: /saved",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(Command("saved"))
async def cmd_saved(message: types.Message):
    await show_saved_photo_page(message.from_user.id, page_index=0, target_message=message)

@dp.message(F.photo)
async def handle_study_photo(message: types.Message):
    status_msg = await message.answer("🔍 Анализирую фото...")

    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(downloaded_file.read()))
        
        user_caption = message.caption or "Дай решение и разбор"

        prompt = f"""
        Ты — заботливый и опытный преподаватель-репетитор. Внимательно изучи изображение.
        Пожелание студента: "{user_caption}"

        ИНСТРУКЦИЯ ПО АНАЛИЗУ:

        СЦЕНАРИЙ 1: На фото НЕТ учебных задач, тестов, уравнений, конспекта или кода (например: мем, животное, случайное фото).
        НАЧНИ СВОЙ ОТВЕТ СТРОГО С ТЕГА: `[NOT_A_TASK]`
        После тега кратко опиши, что изображено на фото.

        СЦЕНАРИЙ 2: На фото ЕСТЬ одна или НЕСКОЛЬКО учебных задач/вопросов.
        Если задач НЕСКОЛЬКО, обязательно раздели решение каждой задачи строкой-разделителем: `===NEXT_TASK===`

        Для каждой задачи используй следующий шаблон:

        💻 **Текст / задание с фото:**
        ```
        (Текст задачи или вопроса 1 в 1)
        ```

        🎯 **Готовый ответ / решение:**
        (Точный и четкий ответ)

        💡 **Как и почему (разбор как от учителя):**
        (Объясни по шагам: Шаг 1, Шаг 2 и т.д. Понятно и без сложных терминов)

        СТРОГИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ:
        1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать знаки доллара ($ или $$) и команды LaTeX (типа \\frac, \\ln, \\dots).
        2. Пиши формулы обычным текстом: `a / b`, `x^2`, `ln(x)`.
        """

        response = ai_model.generate_content([prompt, image])
        text_res = response.text.strip()

        if text_res.startswith("[NOT_A_TASK]"):
            clean_desc = text_res.replace("[NOT_A_TASK]", "").strip()
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="💾 Сохранить фото", callback_data=f"save_p:{photo.file_id}"),
                    InlineKeyboardButton(text="❌ Не сохранять", callback_data="cancel_action")
                ]
            ])
            
            await status_msg.edit_text(
                f"📝 **На фото:** {clean_desc}\n\n"
                f"⚠️ *Это не похоже на учебную задачу.* Пожалуйста, пришли фото задачи или конспекта!\n\n"
                f"Хочешь сохранить это фото в свой личный архив?",
                reply_markup=kb,
                parse_mode="Markdown"
            )
            return

        await status_msg.delete()
        
        tasks = text_res.split("===NEXT_TASK===")
        for idx, task_content in enumerate(tasks, start=1):
            task_text = task_content.strip()
            if task_text:
                header = f"📌 **Задание №{idx} из {len(tasks)}**\n\n" if len(tasks) > 1 else ""
                await message.answer(header + task_text, parse_mode="Markdown")

    except Exception as e:
        await status_msg.edit_text(
            f"❌ Не удалось обработать фото.\n\n`Детали ошибки: {str(e)}`",
            parse_mode="Markdown"
        )


# ==========================================
# 6. CALLBACK-ОБРАБОТЧИКИ КНОПОК
# ==========================================
@dp.callback_query(F.data.startswith("save_p:"))
async def cb_save_photo(callback: CallbackQuery):
    file_id = callback.data.split("save_p:")[1]
    user_id = callback.from_user.id
    
    db_save_photo(user_id=user_id, file_id=file_id, description="Сохраненное фото")
    await callback.message.edit_text("✅ **Фото успешно сохранено в твой личный архив!**\nПросмотр: /saved", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text("👌 Понял! Жду фото с задачей.")
    await callback.answer()


# ==========================================
# 7. ГАЛЕРЕЯ СОХРАНЕННЫХ ФОТО (/saved)
# ==========================================
async def show_saved_photo_page(user_id: int, page_index: int, target_message: types.Message = None, callback: CallbackQuery = None):
    photos = db_get_user_photos(user_id)

    if not photos:
        text = "📁 **Твой архив пуст.**\nУ тебя пока нет сохраненных фото."
        if callback:
            await callback.message.edit_text(text, parse_mode="Markdown")
        else:
            await target_message.answer(text, parse_mode="Markdown")
        return

    if page_index < 0:
        page_index = 0
    if page_index >= len(photos):
        page_index = len(photos) - 1

    photo_id, file_id, desc, created_at = photos[page_index]

    caption = (
        f"🖼 **Сохраненное фото [{page_index + 1} из {len(photos)}]\n"
        f"📅 Дата: `{created_at}`**"
    )

    nav_buttons = []
    if page_index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{page_index - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page_index + 1} / {len(photos)}", callback_data="ignore"))
    if page_index < len(photos) - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page:{page_index + 1}"))

    action_buttons = [
        InlineKeyboardButton(text="🗑 Удалить это фото", callback_data=f"del_p:{photo_id}:{page_index}"),
        InlineKeyboardButton(text="🧹 Очистить весь архив", callback_data="ask_clear_all")
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons, action_buttons])

    if callback:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await target_message.answer_photo(
            photo=file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@dp.callback_query(F.data.startswith("page:"))
async def cb_page_navigation(callback: CallbackQuery):
    page_index = int(callback.data.split(":")[1])
    await show_saved_photo_page(callback.from_user.id, page_index, callback=callback)
    await callback.answer()

@dp.callback_query(F.data.startswith("del_p:"))
async def cb_delete_photo(callback: CallbackQuery):
    parts = callback.data.split(":")
    photo_id = int(parts[1])
    page_index = int(parts[2])
    user_id = callback.from_user.id

    db_delete_photo(photo_id, user_id)
    await callback.answer("🗑 Фото удалено из архива")
    await show_saved_photo_page(user_id, page_index=max(0, page_index - 1), callback=callback)

@dp.callback_query(F.data == "ask_clear_all")
async def cb_ask_clear_all(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить всё", callback_data="confirm_clear_all"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear_all")
        ]
    ])
    await callback.message.reply("⚠️ **Вы уверены, что хотите полностью очистить весь ваш архив?**", reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "confirm_clear_all")
async def cb_confirm_clear_all(callback: CallbackQuery):
    user_id = callback.from_user.id
    db_clear_user_photos(user_id)
    await callback.message.edit_text("🧹 **Ваш личный архив полностью очищен!**", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "cancel_clear_all")
async def cb_cancel_clear_all(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer("Очистка отменена")


# ==========================================
# 8. ЗАПУСК БОТА
# ==========================================
async def main():
    print("🚀 Бот запущен! Кнопки администратора готовы.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())