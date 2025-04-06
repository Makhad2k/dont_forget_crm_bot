import asyncio
import logging
import datetime
import pytz
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from supabase import create_client
from dotenv import load_dotenv
import os

# Загружаем данные из файла .env
load_dotenv()

# === Конфигурация ===
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
smtp_email = os.getenv("SMTP_EMAIL")
smtp_password = os.getenv("SMTP_PASSWORD")

if not all([TOKEN_TELEGRAM, SUPABASE_URL, SUPABASE_KEY, SERVICE_ACCOUNT_FILE]):
    raise ValueError("Проверьте, что все переменные окружения заполнены в .env файле!")

CALENDAR_ID = {}

bot = Bot(token=TOKEN_TELEGRAM)
dp = Dispatcher(storage=MemoryStorage())
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=creds)

# === FSM ===
class AddMeeting(StatesGroup):
    calendar_choice = State()
    title = State()
    name = State()
    datetime = State()
    phone = State()
    comment = State()

class InviteParticipant(StatesGroup):
    waiting_for_email = State()


class SetCalendar(StatesGroup):
    input_url = State()
    input_name = State()

class EditCalendarName(StatesGroup):
    choose = State()
    new_name = State()
    delete_choose = State()
# === Клавиатуры ===
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Добавить встречу")],
    [KeyboardButton(text="Мои встречи")],
    [KeyboardButton(text="Мои календари")],
    [KeyboardButton(text="Информация о боте")],
], resize_keyboard=True)

cancel_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Главное меню / Отмена")]
], resize_keyboard=True)

edit_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Добавить новый календарь")],
    [KeyboardButton(text="Изменить название календаря")],
    [KeyboardButton(text="Удалить календарь")],
    [KeyboardButton(text="Главное меню / Отмена")]
], resize_keyboard=True)

appointments_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Главное меню")]
], resize_keyboard=True)

# === Мои календари ===
@dp.message(F.text.lower() == "мои календари")
async def list_calendars(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    result = supabase.table("settings").select("*").eq("telegram_id", user_id).execute()

    if not result.data:
        keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Добавить новый календарь")],
            [KeyboardButton(text="Главное меню / Отмена")]
        ], resize_keyboard=True)

        return await message.answer(
            "У вас нет подключённых календарей.\n\nХотите подключить новый календарь?",
            reply_markup=keyboard
        )

    await state.update_data(calendar_list=result.data)
    text = "📅 Ваши календари:\n\n"
    for i, c in enumerate(result.data, 1):
        text += f"{i}) *{c['calendar_name']}*\n`{c['calendar_id']}`\n\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=edit_menu)

@dp.message(F.text.lower() == "изменить название календаря")
async def start_rename_calendar(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    result = supabase.table("settings").select("*").eq("telegram_id", user_id).execute()

    if not result.data:
        return await message.answer("У вас нет календарей для изменения.", reply_markup=main_menu)

    await state.update_data(calendar_list=result.data)
    await state.set_state(EditCalendarName.choose)

    buttons = [[KeyboardButton(text=c["calendar_name"])] for c in result.data]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons + [[KeyboardButton(text="Главное меню / Отмена")]], resize_keyboard=True)

    await message.answer("Выберите календарь, который хотите переименовать:", reply_markup=keyboard)

# === Добавление нового календаря ===
@dp.message(F.text.lower() == "добавить новый календарь")
async def set_calendar_start_from_menu(message: types.Message, state: FSMContext):
    await state.set_state(SetCalendar.input_url)
    await message.answer(
        """
📘 *Инструкция по подключению Google Календаря:*

1️⃣ Перейдите в [Google Календарь](https://calendar.google.com)

2️⃣ Создайте новый календарь через:  
*Настройки → Добавить календарь → Создать календарь*

3️⃣ Перейдите в настройки этого календаря и найдите раздел *Доступ к календарю*

4️⃣ Добавьте следующую почту с правами *Редактор*:  
`don-t-forget-crm-bot@dont-forget-bot-000.iam.gserviceaccount.com`

5️⃣ Перейдите в раздел *Интеграция календаря* → найдите поле *Публичный адрес в формате iCal*

6️⃣ Скопируйте ссылку и отправьте её сюда. Пример:  
`https://calendar.google.com/calendar/ical/.../basic.ics`
""",
        parse_mode="Markdown",
        reply_markup=cancel_menu
    )
# === Обработчик информации о боте ===
@dp.message(F.text.lower() == "информация о боте")
async def bot_info(message: types.Message):
    await message.answer(
        "🤖 *Информация о Don't Forget CRM Bot*\n\n"
        "Бот предназначен для удобного занесения встреч в Google Calendar прямо из Telegram.\n\n"
        "📌 *Как это работает?*\n"
        "1. Сначала добавьте свой Google Calendar через раздел *Мои календари*.\n"
        "2. После этого используйте кнопку *Добавить встречу*, чтобы запланировать событие.\n"
        "3. Можно просмотреть и удалить встречи через *Мои встречи*.\n"
        "4. При необходимости отправьте приглашение участникам по email.\n\n"
        "🔹 В любой момент вы можете отменить действие, нажав *Главное меню / Отмена*.\n\n"
        "Приятного использования!",
        parse_mode="Markdown",
        reply_markup=main_menu
    )

# === Команды ===
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Добро пожаловать!\n\n"
        "Don't Forget CRM bot создан для занесения встреч в Google Calendar прямо из telegram, чтобы ты не забыл внести всю важную информацию!.\n\n"        
        "Чтобы начать пользоваться ботом, сначала установи Google Calendar в *Мои календари*, затем ты сможешь *Добавить встречу.*\n\n"
        "Выберите действие:",
        reply_markup=main_menu,
        parse_mode="Markdown"
    )


@dp.message(Command("cancel"))
@dp.message(F.text.lower().in_(["отмена", "главное меню", "главное меню / отмена"]))
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено. Вы в главном меню.", reply_markup=main_menu)

# === Установка календаря ===
@dp.message(F.text.lower() == "установить календарь")
async def set_calendar_start(message: types.Message, state: FSMContext):
    await state.set_state(SetCalendar.input_url)
    await message.answer(
        """
📘 *Инструкция по подключению Google Календаря:*

1️⃣ Перейдите в [Google Календарь](https://calendar.google.com)

2️⃣ Создайте новый календарь через:  
*Настройки → Добавить календарь → Создать календарь*

3️⃣ Перейдите в настройки этого календаря и найдите раздел *Доступ к календарю*

4️⃣ Добавьте следующую почту с правами *Редактор*:  
`don-t-forget-crm-bot@dont-forget-bot-000.iam.gserviceaccount.com`

5️⃣ Перейдите в раздел *Интеграция календаря* → найдите поле *Публичный адрес в формате iCal*

6️⃣ Скопируйте ссылку и отправьте её сюда. Пример:  
`https://calendar.google.com/calendar/ical/.../basic.ics`
""",
        parse_mode="Markdown",
        reply_markup=cancel_menu
    )

@dp.message(SetCalendar.input_url)
async def receive_calendar_url(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    raw_input = message.text.strip()
    match = re.search(r"ical/([^/]+)", raw_input)
    calendar_id = match.group(1) if match else raw_input
    calendar_id = calendar_id.replace('%2540', '@').replace('%40', '@')

    try:
        exists = supabase.table("settings").select("*").match({
            "telegram_id": user_id,
            "calendar_id": calendar_id
        }).execute().data

        if exists:
            await state.clear()
            return await message.answer("⚠️ Этот календарь уже добавлен.", reply_markup=main_menu)

        await state.update_data(calendar_id=calendar_id)
        await state.set_state(SetCalendar.input_name)
        await message.answer("Введите название для этого календаря:", reply_markup=cancel_menu)

    except Exception as e:
        await state.clear()
        await message.answer(f"❌ Ошибка при проверке: {e}", reply_markup=main_menu)

@dp.message(SetCalendar.input_name)
async def receive_calendar_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    calendar_id = data["calendar_id"]
    calendar_name = message.text.strip()

    try:
        supabase.table("settings").insert({
            "telegram_id": user_id,
            "calendar_id": calendar_id,
            "calendar_name": calendar_name
        }).execute()
        await message.answer(f"✅ Календарь *{calendar_name}* добавлен!", parse_mode="Markdown", reply_markup=main_menu)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_menu)

    await state.clear()

# === Мои календари ===
@dp.message(F.text.lower() == "мои календари")
async def list_calendars(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    result = supabase.table("settings").select("*").eq("telegram_id", user_id).execute()

    if not result.data:
        # Если календарей нет — показываем меню с возможностью добавить
        keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Установить календарь")],
            [KeyboardButton(text="Главное меню / Отмена")]
        ], resize_keyboard=True)

        return await message.answer(
            "У вас нет подключённых календарей.\n\nХотите подключить новый календарь?",
            reply_markup=keyboard
        )

    # Если календари есть — отображаем список и действия
    text = "📅 Ваши календари:\n\n"
    for i, c in enumerate(result.data, 1):
        text += f"{i}) *{c['calendar_name']}*\n`{c['calendar_id']}`\n\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=edit_menu)

@dp.message(EditCalendarName.choose)
async def choose_calendar_to_rename(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected_name = message.text.strip()

    for c in data["calendar_list"]:
        if c["calendar_name"].lower() == selected_name.lower():
            await state.update_data(calendar_id=c["calendar_id"])
            await state.set_state(EditCalendarName.new_name)
            await message.answer("Введите новое название календаря:", reply_markup=cancel_menu)
            return

    await message.answer("Пожалуйста, выберите календарь из предложенных кнопок.")

@dp.message(EditCalendarName.new_name)
async def rename_calendar(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    new_name = message.text.strip()
    calendar_id = data["calendar_id"]

    try:
        supabase.table("settings").update({"calendar_name": new_name}).match({
            "telegram_id": user_id,
            "calendar_id": calendar_id
        }).execute()
        await message.answer("✅ Название календаря обновлено!", reply_markup=main_menu)
    except Exception as e:
        await message.answer(f"❌ Ошибка при переименовании: {e}", reply_markup=main_menu)

    await state.clear()

# === Добавление встречи ===
@dp.message(F.text.lower() == "добавить встречу")
async def add_meeting_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    calendars = supabase.table("settings").select("*").eq("telegram_id", user_id).execute().data

    if not calendars:
        # Показываем кнопку "Установить календарь" только в этом случае
        keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Установить календарь")],
            [KeyboardButton(text="Главное меню / Отмена")]
        ], resize_keyboard=True)

        return await message.answer("Сначала добавьте хотя бы один календарь.", reply_markup=keyboard)

    buttons = [[KeyboardButton(text=c["calendar_name"])] for c in calendars]
    await state.update_data(calendar_list=calendars)
    await state.set_state(AddMeeting.calendar_choice)
    await message.answer("Выберите календарь для встречи:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(AddMeeting.calendar_choice)
async def select_calendar(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected = message.text.strip()
    for c in data["calendar_list"]:
        if c["calendar_name"].lower() == selected.lower():
            await state.update_data(calendar_id=c["calendar_id"])
            await state.set_state(AddMeeting.title)
            await message.answer("Введите название встречи:", reply_markup=cancel_menu)
            return
    await message.answer("Пожалуйста, выберите календарь из списка кнопок.")

@dp.message(AddMeeting.title)
async def get_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddMeeting.name)
    await message.answer("Введите имя клиента:")

@dp.message(AddMeeting.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddMeeting.datetime)
    await message.answer("Введите дату и время (YYYY-MM-DD HH:MM):")

@dp.message(AddMeeting.datetime)
async def get_datetime(message: types.Message, state: FSMContext):
    try:
        datetime.datetime.strptime(message.text, "%Y-%m-%d %H:%M")
        await state.update_data(datetime=message.text)
        await state.set_state(AddMeeting.phone)
        await message.answer("Введите номер телефона клиента в формате: +7XXXXXXXXXX")
    except ValueError:
        await message.answer("Неверный формат. Пример: 2025-03-30 14:00")

@dp.message(AddMeeting.phone)
async def get_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()

    if not re.fullmatch(r"\+7\d{10}", phone):
        return await message.answer("⚠️ Номер должен быть в формате +7XXXXXXXXXX.\n\nПожалуйста, введите корректный номер:")

    await state.update_data(phone=phone)
    await state.set_state(AddMeeting.comment)
    await message.answer("Комментарий к встрече:")

@dp.message(AddMeeting.comment)
async def get_comment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.update_data(comment=message.text)
    data = await state.get_data()
    await state.clear()

    try:
        dt = pytz.timezone("Europe/Moscow").localize(datetime.datetime.strptime(data["datetime"], "%Y-%m-%d %H:%M"))

        client_result = supabase.table("clients").select("*").eq("telegram_id", user_id).execute().data
        if client_result:
            client = client_result[0]
        else:
            client = supabase.table("clients").insert({
                "name": data["name"],
                "telegram_id": user_id,
                "phone_number": data["phone"]
            }).execute().data[0]

        appointment = supabase.table("appointments").insert({
            "client_id": client["id"],
            "meeting_date_time": dt.isoformat(),
            "phone_number": data["phone"],
            "title": data["title"],
            "calendar_id": data["calendar_id"]  # вот это добавляем
        }).execute().data[0]

        event = {
            "summary": data["title"],
            "description": (
                f"👤 Клиент: {data['name']}\n"
                f"📞 Телефон: {data['phone']}\n"
                f"📝 Комментарий: {data['comment'] or '—'}"
            ),
            "start": {"dateTime": dt.isoformat(), "timeZone": "Europe/Moscow"},
            "end": {"dateTime": (dt + datetime.timedelta(hours=1)).isoformat(), "timeZone": "Europe/Moscow"}
        }

        created_event = calendar_service.events().insert(
            calendarId=data["calendar_id"],
            body=event
        ).execute()

        supabase.table("calendar_events").insert({
            "appointment_id": appointment["id"],
            "event_id": created_event["id"],
            "event_status": created_event["status"]
        }).execute()

        event_link = created_event.get("htmlLink", None)

        if event_link:
            await message.answer(
                f"✅ Встреча добавлена!\n\n"
                f"📅 [Открыть событие в Google Календаре]({event_link})",
                parse_mode="Markdown",
                reply_markup=main_menu
            )
        else:
            await message.answer("✅ Встреча добавлена, но ссылка на событие не получена.", reply_markup=main_menu)

        # 🔹 Предложение отправить приглашение
        invite_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📨 Отправить приглашение другому участнику",
                callback_data=f"invite:{appointment['id']}"
            )]
        ])
        await message.answer("Хотите отправить приглашение другому участнику?", reply_markup=invite_keyboard)

    except Exception as e:
        await message.answer(f"❌ Ошибка при добавлении встречи: {e}", reply_markup=main_menu)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# === Обработчик информации о боте ===
@dp.message(F.text.lower() == "информация о боте")
async def bot_info(message: types.Message):
    await message.answer(
        "🤖 *Информация о Don't Forget CRM Bot*\n\n"
        "Бот предназначен для удобного занесения встреч в Google Calendar прямо из Telegram.\n\n"
        "📌 *Как это работает?*\n"
        "1. Сначала добавьте свой Google Calendar через раздел *Мои календари*.\n"
        "2. После этого используйте кнопку *Добавить встречу*, чтобы запланировать событие.\n"
        "3. Можно просмотреть и удалить встречи через *Мои встречи*.\n"
        "4. При необходимости отправьте приглашение участникам по email.\n\n"
        "🔹 В любой момент вы можете отменить действие, нажав *Главное меню / Отмена*.\n\n"
        "Приятного использования!",
        parse_mode="Markdown",
        reply_markup=main_menu
    )

# === Мои встречи (только кнопка «Главное меню») ===
@dp.message(F.text.lower() == "мои встречи")
async def show_appointments(message: types.Message):
    user_id = message.from_user.id

    client_result = supabase.table("clients").select("id").eq("telegram_id", user_id).execute()
    if not client_result.data:
        return await message.answer("У вас нет встреч.", reply_markup=appointments_menu)

    client_id = client_result.data[0]["id"]
    appointments = supabase.table("appointments").select("*").eq("client_id", client_id).execute().data

    if not appointments:
        return await message.answer("У вас нет встреч.", reply_markup=appointments_menu)

    for app in appointments:
        from_zone = pytz.utc
        to_zone = pytz.timezone("Europe/Moscow")
        raw_time = app["meeting_date_time"]
        utc_dt = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        moscow_dt = utc_dt.astimezone(to_zone)
        formatted_time = moscow_dt.strftime("%Y-%m-%d %H:%M")

        text = (
            f"📅 <b>{formatted_time}</b>\n"
            f"📌 <b>Название:</b> {app.get('title', '—')}\n"
            f"📞 <b>Телефон:</b> {app['phone_number']}"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📨 Отправить приглашение", callback_data=f"invite:{app['id']}")],
            [InlineKeyboardButton(text="❌ Удалить встречу", callback_data=f"delete_meeting:{app['id']}" )]
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    # Обновляем клавиатуру после всех сообщений
    await message.answer("Выберите действие 👆", reply_markup=appointments_menu)
    # Кнопка для отправки инвайта
@dp.callback_query(F.data.startswith("invite:"))
async def handle_invite_start(callback: types.CallbackQuery, state: FSMContext):
    appointment_id = int(callback.data.split(":")[1])
    await state.set_state(InviteParticipant.waiting_for_email)
    await state.update_data(appointment_id=appointment_id)

    await callback.message.answer("Введите email участника, которому нужно отправить приглашение:")
    await callback.answer()

# === Удаление встречи ===
@dp.callback_query(F.data.startswith("delete_meeting:"))
async def delete_meeting_callback(callback: types.CallbackQuery):
    meeting_id = int(callback.data.split(":")[1])
    user_message = ""

    try:
        # Получаем event_id и calendar_id
        event_data = supabase.table("calendar_events").select("*").eq("appointment_id", meeting_id).execute().data
        appointment_data = supabase.table("appointments").select("calendar_id").eq("id", meeting_id).execute().data

        if event_data and appointment_data:
            event_id = event_data[0]["event_id"]
            calendar_id = appointment_data[0]["calendar_id"]

            # Пытаемся удалить из Google Calendar
            try:
                calendar_service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            except Exception as e:
                logging.warning(f"⚠️ Событие не найдено в Google Calendar: {e}")
                user_message += "⚠️ Событие уже было удалено из Google Календаря.\n"

        # Удаляем из Supabase
        supabase.table("calendar_events").delete().eq("appointment_id", meeting_id).execute()
        supabase.table("appointments").delete().eq("id", meeting_id).execute()

        user_message += "❌ Встреча удалена из базы данных."
        await callback.message.edit_text(user_message)
        await callback.answer("Удалено.")
    except Exception as e:
        await callback.answer(f"Ошибка при удалении: {e}")

        # Удаляем из Supabase
        supabase.table("calendar_events").delete().eq("appointment_id", meeting_id).execute()
        supabase.table("appointments").delete().eq("id", meeting_id).execute()

        await callback.message.edit_text("❌ Встреча удалена из календаря и базы данных.")
        await callback.answer("Удалено.")
    except Exception as e:
        await callback.answer(f"Ошибка при удалении: {e}")

@dp.message(InviteParticipant.waiting_for_email)
async def handle_email_input(message: types.Message, state: FSMContext):
    email = message.text.strip()

    # 🔹 Проверка валидности email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return await message.answer("⚠️ Пожалуйста, введите корректный email.")

    data = await state.get_data()
    appointment_id = data["appointment_id"]

    try:
        appointment = supabase.table("appointments").select("*").eq("id", appointment_id).execute().data[0]
        dt = datetime.datetime.fromisoformat(appointment["meeting_date_time"])
        title = appointment.get("title", "Встреча")
        description = f"Встреча по теме: {title}"

        moscow_tz = pytz.timezone("Europe/Moscow")
        moscow_dt = dt.astimezone(moscow_tz)
        start = moscow_dt.strftime("%Y%m%dT%H%M%S")

        end = (dt + datetime.timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")

        # Генерация времени и ссылки
        import urllib.parse
        formatted_dt = dt.strftime("%Y-%m-%d %H:%M")
        moscow_tz = pytz.timezone("Europe/Moscow")
        moscow_dt = dt.astimezone(moscow_tz)
        start = moscow_dt.strftime("%Y%m%dT%H%M%S")

        # Ссылка с точным временем начала (без end)
        gcal_link = (
            "https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={urllib.parse.quote(title)}"
            f"&details={urllib.parse.quote(description)}"
            f"&dates={start}/{start}"
            f"&ctz=Europe/Moscow"
        )

        # Формируем тело письма с кликабельной ссылкой
        email_body = (
            f"Вы приглашены на встречу:\n\n"
            f"📅 Дата и время: {formatted_dt}\n"
            f"📝 Тема: {title}\n\n"
            f"👉 [Добавить в Google Календарь]({gcal_link})"
        )


        try:
            import urllib.parse

            moscow_dt = dt.astimezone(pytz.timezone("Europe/Moscow"))
            formatted_dt = moscow_dt.strftime("%Y-%m-%d %H:%M")
            moscow_tz = pytz.timezone("Europe/Moscow")
            moscow_dt = dt.astimezone(moscow_tz)
            start = moscow_dt.strftime("%Y%m%dT%H%M%S")

            gcal_link = (
                "https://calendar.google.com/calendar/render?action=TEMPLATE"
                f"&text={urllib.parse.quote(title)}"
                f"&details={urllib.parse.quote(description)}"
                f"&dates={start}/{start}"
                f"&ctz=Europe/Moscow"
            )

            # Текст письма
            body_text = (
                f"Вы приглашены на встречу:\n\n"
                f"📅 Дата и время: {formatted_dt}\n"
                f"📝 Тема: {title}\n\n"
                f"👉 Добавить в календарь: {gcal_link}"
            )

            # HTML-версия письма
            body_html = (
                f"<p>Вы приглашены на встречу:</p>"
                f"<p><b>📅 Дата и время:</b> {formatted_dt}<br>"
                f"<b>📝 Тема:</b> {title}</p>"
                f"<p><a href='{gcal_link}'>👉 Добавить в Google Календарь</a></p>"
            )

            await send_email_invite_with_image(
                to_email=email,
                subject=f"Приглашение на встречу: {title}",
                body_text=(
                    f"<p>📅 <b>Дата и время:</b> {formatted_dt}<br>"
                    f"📝 <b>Тема:</b> {title}</p>"
                    f"<p>👉 <a href='{gcal_link}'>Добавить в Google Календарь</a></p>"
                ),
                image_path="invite_email.jpg"
            )

            await message.answer("✅ Приглашение отправлено по email!", reply_markup=main_menu)
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке письма: {e}", reply_markup=main_menu)

    except Exception as e:
        await message.answer(f"❌ Ошибка при создании ссылки: {e}")
    await state.clear()

import ssl
import certifi
import aiosmtplib
from email.message import EmailMessage


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import ssl
import certifi
import aiosmtplib
import os

async def send_email_invite_with_image(to_email: str, subject: str, body_text: str, image_path: str):
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")

    # Основной контейнер письма
    msg = MIMEMultipart("related")
    msg["From"] = smtp_email
    msg["To"] = to_email
    msg["Subject"] = subject

    # HTML-версия письма
    html = f"""
    <html>
        <body>
            <p>{body_text.replace('\n', '<br>')}</p>
            <img src="cid:image1" width="400"/>
        </body>
    </html>
    """

    # Добавляем HTML как альтернативную часть
    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(html, "html"))
    msg.attach(alternative)

    # Встраиваем изображение
    with open(image_path, "rb") as f:
        img = MIMEImage(f.read())
        img.add_header("Content-ID", "<image1>")
        img.add_header("Content-Disposition", "inline", filename="invite.jpg")
        msg.attach(img)

    # Отправка
    context = ssl.create_default_context(cafile=certifi.where())
    await aiosmtplib.send(
        msg,
        hostname="smtp.gmail.com",
        port=587,
        start_tls=True,
        username=smtp_email,
        password=smtp_password,
        tls_context=context,
    )

# === Удаление Календаря ===
@dp.message(F.text.lower() == "удалить календарь")
async def start_calendar_delete(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    calendars = supabase.table("settings").select("*").eq("telegram_id", user_id).execute().data

    if not calendars:
        return await message.answer("У вас нет календарей для удаления.", reply_markup=main_menu)

    await state.set_state(EditCalendarName.delete_choose)
    await state.update_data(calendar_list=calendars)

    buttons = [[KeyboardButton(text=c["calendar_name"])] for c in calendars]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons + [[KeyboardButton(text="Главное меню / Отмена")]], resize_keyboard=True)
    await message.answer("Выберите календарь, который хотите удалить:", reply_markup=keyboard)
@dp.message(EditCalendarName.delete_choose)
async def delete_selected_calendar(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    selected_name = message.text.strip()
    data = await state.get_data()

    for calendar in data["calendar_list"]:
        if calendar["calendar_name"].lower() == selected_name.lower():
            supabase.table("settings").delete().match({
                "telegram_id": user_id,
                "calendar_id": calendar["calendar_id"]
            }).execute()

            await message.answer(f"✅ Календарь '{selected_name}' удалён.", reply_markup=main_menu)
            return await state.clear()

    await message.answer("❌ Не удалось найти календарь. Пожалуйста, выберите из списка.")

# === Запуск ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())