import asyncio
import os
import json
import base64
import struct
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from pyrogram import Client
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# ====== المتغيرات - عدل دول ======
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
DEVELOPER_ID = ADMIN_ID # المطور = الادمن
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
DEVELOPER_USERNAME = "Devazf"
FORCE_SUB_CHANNEL = os.environ.get('FORCE_SUB_CHANNEL', '')
SUPPORT_GROUP = "vaazef"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ====== قاعدة البيانات ======
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                  joined TEXT, is_banned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                  action TEXT, details TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats
                 (key TEXT PRIMARY KEY, value INTEGER)''')
    c.execute("INSERT OR IGNORE INTO stats VALUES ('total_extractions', 0)")
    c.execute("INSERT OR IGNORE INTO stats VALUES ('total_conversions', 0)")
    conn.commit()
    conn.close()

init_db()

def db_add_user(user_id, username, first_name):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?, 0)",
              (user_id, username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

def db_log(user_id, action, details=""):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, action, details, timestamp) VALUES (?,?,?,?)",
              (user_id, action, details, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def db_is_banned(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def db_ban_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def db_unban_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def db_increment_stat(key):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE stats SET value = value + 1 WHERE key=?", (key,))
    conn.commit()
    conn.close()

def db_get_stats():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT value FROM stats WHERE key='total_extractions'")
    extractions = c.fetchone()[0]
    c.execute("SELECT value FROM stats WHERE key='total_conversions'")
    conversions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned = c.fetchone()[0]
    conn.close()
    return total_users, extractions, conversions, banned

def db_get_all_users():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def db_get_logs(limit=20):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT?", (limit,))
    logs = c.fetchall()
    conn.close()
    return logs

async def check_force_sub(user_id):
    if not FORCE_SUB_CHANNEL or user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(f"@{FORCE_SUB_CHANNEL}", user_id)
        return member.status not in ['left', 'kicked']
    except:
        return False

user_last_action = {}
async def check_rate_limit(user_id):
    now = time.time()
    if user_id in user_last_action:
        if now - user_last_action[user_id] < 3:
            return False
    user_last_action[user_id] = now
    return True

sessions_temp = {}

class SessionStates(StatesGroup):
    waiting_phone_telethon = State()
    waiting_code_telethon = State()
    waiting_password_telethon = State()
    waiting_phone_pyro = State()
    waiting_code_pyro = State()
    waiting_password_pyro = State()
    waiting_string_telethon = State()
    waiting_string_pyro = State()
    waiting_check_tele = State()
    waiting_check_pyro = State()
    waiting_broadcast = State()
    waiting_ban_id = State()

def main_menu(uid):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 استخراج تليثون", callback_data="extract_telethon"),
        InlineKeyboardButton(text="📱 استخراج بايوجرام", callback_data="extract_pyro")
    )
    builder.row(
        InlineKeyboardButton(text="🔄 تليثون → بايوجرام", callback_data="tele_to_pyro"),
        InlineKeyboardButton(text="🔄 بايوجرام → تليثون", callback_data="pyro_to_tele")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 فحص جلسة", callback_data="check_session"),
        InlineKeyboardButton(text="👨‍💻 المطور", callback_data="developer_info")
    )
    if uid == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ لوحة التحكم", callback_data="admin_panel"))
    return builder.as_markup()

def admin_panel_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 الاحصائيات", callback_data="stats"),
        InlineKeyboardButton(text="📢 رسالة جماعية", callback_data="broadcast")
    )
    builder.row(
        InlineKeyboardButton(text="👥 المستخدمين", callback_data="users_list"),
        InlineKeyboardButton(text="🚫 حظر/فك حظر", callback_data="ban_user")
    )
    builder.row(
        InlineKeyboardButton(text="📋 السجلات", callback_data="logs"),
        InlineKeyboardButton(text="♻️ ريستارت", callback_data="restart")
    )
    builder.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="back"))
    return builder.as_markup()

@dp.message(CommandStart())
async def start(message: types.Message):
    uid = message.from_user.id

    if db_is_banned(uid):
        await message.reply("🚫 انت محظور من استخدام البوت\n\nتواصل مع المطور لفك الحظر")
        return

    if not await check_force_sub(uid):
        btns = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{FORCE_SUB_CHANNEL}")],
            [InlineKeyboardButton(text="✅ تحققت", callback_data="check_sub")]
        ])
        await message.reply(f"""
❌ لازم تشترك في القناة عشان تستخدم البوت

📢 @{FORCE_SUB_CHANNEL}

بعد الاشتراك دوس "تحققت" 👇
""", reply_markup=btns)
        return

    db_add_user(uid, message.from_user.username, message.from_user.first_name)
    db_log(uid, "start")

    text = f"""
🔐 Session Extractor & Converter Pro v3.0

اهلاً {message.from_user.first_name} 👋

الميزات المتقدمة:
1️⃣ استخراج جلسة Telethon
2️⃣ استخراج جلسة Pyrogram
3️⃣ تحويل Telethon ↔️ Pyrogram
4️⃣ فحص صلاحية الجلسة
5️⃣ حذف تلقائي للأمان
6️⃣ حماية Rate Limit
7️⃣ سجل عمليات كامل

⚠️ تحذير أمني: لا تشارك جلستك مع أي حد أبداً

الدعم: @{SUPPORT_GROUP}

اختار من القايمة 👇
"""
    await message.reply(text, reply_markup=main_menu(uid))

@dp.callback_query(F.data == "extract_telethon")
async def extract_telethon(call: CallbackQuery, state: FSMContext):
    if not await check_rate_limit(call.from_user.id):
        await call.answer("⏳ استنى 3 ثواني بين كل عملية", show_alert=True)
        return

    await call.message.edit_text(
        "📱 استخراج جلسة Telethon\n\n"
        "ابعت رقم تليفونك مع كود الدولة:\n"
        "مثال: +201234567890\n\n"
        "⚠️ الرقم لازم يكون مربوط بحسابك\n"
        "⏱ الكود صالح لمدة 5 دقايق",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]
        ])
    )
    await state.set_state(SessionStates.waiting_phone_telethon)

@dp.message(SessionStates.waiting_phone_telethon)
async def get_phone_telethon(message: types.Message, state: FSMContext):
    if db_is_banned(message.from_user.id): return

    phone = message.text.strip()
    await state.update_data(phone=phone)

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    try:
        sent = await client.send_code_request(phone)
        sessions_temp[message.from_user.id] = {"client": client, "phone_hash": sent.phone_code_hash}
        db_log(message.from_user.id, "extract_telethon_start", phone)

        await message.reply(
            "✅ تم ارسال الكود على تليجرام\n\n"
            "ابعت الكود اللي وصلك كده: 12345\n\n"
            "لو مجاش شوف الرسايل المحفوظة"
        )
        await state.set_state(SessionStates.waiting_code_telethon)
    except Exception as e:
        await message.reply(f"❌ خطأ: {str(e)}")
        await state.clear()

@dp.message(SessionStates.waiting_code_telethon)
async def get_code_telethon(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    temp = sessions_temp.get(message.from_user.id)

    if not temp:
        await message.reply("❌ انتهت الجلسة. ابدأ من جديد /start")
        await state.clear()
        return

    client = temp["client"]
    phone = data["phone"]
    phone_hash = temp["phone_hash"]

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_hash)
        string_session = client.session.save()
        me = await client.get_me()
        db_increment_stat('total_extractions')
        db_log(message.from_user.id, "extract_telethon_success", me.username)

        msg = await message.reply(f"""
✅ تم استخراج الجلسة بنجاح

الحساب: @{me.username or 'None'}
الاسم: {me.first_name}
ID: {me.id}
الرقم: {phone}

STRING_SESSION:
{string_session}

⚠️ تحذيرات مهمة:
1. احفظ الجلسة في مكان آمن
2. لا تشاركها مع حد أبداً
3. اللي ياخدها يتحكم في حسابك كامل
4. الرسالة هتتمسح بعد 5 دقايق للأمان

✅ الجلسة شغالة 100%
""", reply_markup=main_menu(message.from_user.id))

        await client.disconnect()
        del sessions_temp[message.from_user.id]
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
            await message.reply("🗑️ تم حذف الجلسة للأمان")
        except: pass

    except Exception as e:
        if "password" in str(e).lower() or "2fa" in str(e).lower():
            await message.reply("🔒 حسابك عليه تحقق بخطوتين\n\nابعت الباسورد:")
            await state.set_state(SessionStates.waiting_password_telethon)
        else:
            await message.reply(f"❌ خطأ: {str(e)}")
            await client.disconnect()
            await state.clear()

@dp.message(SessionStates.waiting_password_telethon)
async def get_password_telethon(message: types.Message, state: FSMContext):
    password = message.text.strip()
    temp = sessions_temp.get(message.from_user.id)

    if not temp:
        await message.reply("❌ انتهت الجلسة")
        await state.clear()
        return

    client = temp["client"]

    try:
        await client.sign_in(password=password)
        string_session = client.session.save()
        me = await client.get_me()
        db_increment_stat('total_extractions')
        db_log(message.from_user.id, "extract_telethon_success", me.username)

        msg = await message.reply(f"""
✅ تم استخراج الجلسة بنجاح

الحساب: @{me.username or 'None'}
ID: {me.id}

STRING_SESSION:
{string_session}

⚠️ الرسالة هتتمسح بعد 5 دقايق
""", reply_markup=main_menu(message.from_user.id))

        await client.disconnect()
        del sessions_temp[message.from_user.id]
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
        except: pass

    except Exception as e:
        await message.reply(f"❌ الباسورد غلط: {str(e)}")
        await client.disconnect()
        await state.clear()

@dp.callback_query(F.data == "extract_pyro")
async def extract_pyro(call: CallbackQuery, state: FSMContext):
    if not await check_rate_limit(call.from_user.id):
        await call.answer("⏳ استنى 3 ثواني", show_alert=True)
        return

    await call.message.edit_text(
        "📱 استخراج جلسة Pyrogram\n\n"
        "ابعت رقم تليفونك مع كود الدولة:\n"
        "مثال: +201234567890",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]
        ])
    )
    await state.set_state(SessionStates.waiting_phone_pyro)

@dp.message(SessionStates.waiting_phone_pyro)
async def get_phone_pyro(message: types.Message, state: FSMContext):
    if db_is_banned(message.from_user.id): return

    phone = message.text.strip()
    await state.update_data(phone=phone)

    client = Client(":memory:", API_ID, API_HASH)
    await client.connect()

    try:
        sent = await client.send_code(phone)
        sessions_temp[message.from_user.id] = {"client": client, "phone_hash": sent.phone_code_hash}
        db_log(message.from_user.id, "extract_pyro_start", phone)

        await message.reply("✅ تم ارسال الكود\n\nابعت الكود: 12345")
        await state.set_state(SessionStates.waiting_code_pyro)
    except Exception as e:
        await message.reply(f"❌ خطأ: {str(e)}")
        await state.clear()

@dp.message(SessionStates.waiting_code_pyro)
async def get_code_pyro(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    temp = sessions_temp.get(message.from_user.id)

    if not temp:
        await message.reply("❌ انتهت الجلسة")
        await state.clear()
        return

    client = temp["client"]
    phone = data["phone"]
    phone_hash = temp["phone_hash"]

    try:
        await client.sign_in(phone, phone_hash, code)
        string_session = await client.export_session_string()
        me = await client.get_me()
        db_increment_stat('total_extractions')
        db_log(message.from_user.id, "extract_pyro_success", me.username)

        msg = await message.reply(f"""
✅ تم استخراج جلسة Pyrogram بنجاح

الحساب: @{me.username or 'None'}
ID: {me.id}

PYROGRAM_SESSION:
{string_session}

⚠️ الرسالة هتتمسح بعد 5 دقايق
""", reply_markup=main_menu(message.from_user.id))

        await client.disconnect()
        del sessions_temp[message.from_user.id]
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
        except: pass

    except Exception as e:
        if "password" in str(e).lower():
            await message.reply("🔒 حسابك عليه تحقق بخطوتين\n\nابعت الباسورد:")
            await state.set_state(SessionStates.waiting_password_pyro)
        else:
            await message.reply(f"❌ خطأ: {str(e)}")
            await client.disconnect()
            await state.clear()

@dp.message(SessionStates.waiting_password_pyro)
async def get_password_pyro(message: types.Message, state: FSMContext):
    password = message.text.strip()
    temp = sessions_temp.get(message.from_user.id)

    if not temp:
        await message.reply("❌ انتهت الجلسة")
        await state.clear()
        return

    client = temp["client"]

    try:
        await client.check_password(password)
        string_session = await client.export_session_string()
        me = await client.get_me()
        db_increment_stat('total_extractions')
        db_log(message.from_user.id, "extract_pyro_success", me.username)

        msg = await message.reply(f"""
✅ تم استخراج جلسة Pyrogram بنجاح

الحساب: @{me.username or 'None'}
ID: {me.id}

PYROGRAM_SESSION:
{string_session}

⚠️ الرسالة هتتمسح بعد 5 دقايق
""", reply_markup=main_menu(message.from_user.id))

        await client.disconnect()
        del sessions_temp[message.from_user.id]
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
        except: pass

    except Exception as e:
        await message.reply(f"❌ الباسورد غلط: {str(e)}")
        await client.disconnect()
        await state.clear()

@dp.callback_query(F.data == "tele_to_pyro")
async def tele_to_pyro(call: CallbackQuery, state: FSMContext):
    if not await check_rate_limit(call.from_user.id):
        await call.answer("⏳ استنى 3 ثواني", show_alert=True)
        return

    await call.message.edit_text(
        "🔄 تحويل Telethon → Pyrogram\n\n"
        "ابعت الـ STRING_SESSION بتاع تليثون:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]
        ])
    )
    await state.set_state(SessionStates.waiting_string_telethon)

@dp.message(SessionStates.waiting_string_telethon)
async def convert_tele_to_pyro(message: types.Message, state: FSMContext):
    tele_string = message.text.strip()

    try:
        dc_id, ip, port, auth_key = StringSession.decode_string(tele_string)
        pyro_data = struct.pack('>BI?256sQ', dc_id, 0, True, auth_key, 0)
        pyro_string = base64.urlsafe_b64encode(pyro_data).decode().rstrip('=')

        db_increment_stat('total_conversions')
        db_log(message.from_user.id, "convert_tele_to_pyro")

        msg = await message.reply(f"""
✅ تم التحويل بنجاح

Pyrogram Session:
{pyro_string}

Telethon Session الأصلي:
{tele_string}

✅ الاتنين شغالين
⚠️ الرسالة هتتمسح بعد 5 دقايق
""", reply_markup=main_menu(message.from_user.id))
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
        except: pass

    except Exception as e:
        await message.reply(f"❌ سترنج غلط: {str(e)}")
        await state.clear()

@dp.callback_query(F.data == "pyro_to_tele")
async def pyro_to_tele(call: CallbackQuery, state: FSMContext):
    if not await check_rate_limit(call.from_user.id):
        await call.answer("⏳ استنى 3 ثواني", show_alert=True)
        return

    await call.message.edit_text(
        "🔄 تحويل Pyrogram → Telethon\n\n"
        "ابعت الـ SESSION_STRING بتاع بايوجرام:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]
        ])
    )
    await state.set_state(SessionStates.waiting_string_pyro)

@dp.message(SessionStates.waiting_string_pyro)
async def convert_pyro_to_tele(message: types.Message, state: FSMContext):
    pyro_string = message.text.strip()

    try:
        padding = 4 - len(pyro_string) % 4
        if padding!= 4:
            pyro_string += '=' * padding

        data = base64.urlsafe_b64decode(pyro_string)
        dc_id, test_mode, ipv6, auth_key, user_id = struct.unpack('>BI?256sQ', data)
        tele_string = StringSession.encode_string(dc_id, None, None, auth_key)

        db_increment_stat('total_conversions')
        db_log(message.from_user.id, "convert_pyro_to_tele")

        msg = await message.reply(f"""
✅ تم التحويل بنجاح

Telethon Session:
{tele_string}

Pyrogram Session الأصلي:
{pyro_string}

✅ الاتنين شغالين
⚠️ الرسالة هتتمسح بعد 5 دقايق
""", reply_markup=main_menu(message.from_user.id))
        await state.clear()

        await asyncio.sleep(300)
        try:
            await msg.delete()
        except: pass

    except Exception as e:
        await message.reply(f"❌ سترنج غلط: {str(e)}")
        await state.clear()

@dp.callback_query(F.data == "check_session")
async def check_session_menu(call: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 فحص تليثون", callback_data="check_tele"),
        InlineKeyboardButton(text="📱 فحص بايوجرام", callback_data="check_pyro")
    )
    builder.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="back"))
    await call.message.edit_text("🔍 فحص صلاحية الجلسة\n\nاختار نوع الجلسة:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "check_tele")
async def check_tele_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔍 فحص جلسة Telethon\n\nابعت الـ STRING_SESSION:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]]))
    await state.set_state(SessionStates.waiting_check_tele)

@dp.message(SessionStates.waiting_check_tele)
async def check_tele_session(message: types.Message, state: FSMContext):
    string_session = message.text.strip()

    try:
        client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            await message.reply(f"""
✅ الجلسة شغالة 100%

الحساب: @{me.username or 'None'}
الاسم: {me.first_name}
ID: {me.id}
الرقم: {me.phone or 'مخفي'}

الحالة: نشطة ✅
""", reply_markup=main_menu(message.from_user.id))
            db_log(message.from_user.id, "check_session_tele_success")
        else:
            await message.reply("❌ الجلسة منتهية أو غلط")

        await client.disconnect()
        await state.clear()
    except Exception as e:
        await message.reply(f"❌ الجلسة غلط: {str(e)}")
        await state.clear()

@dp.callback_query(F.data == "check_pyro")
async def check_pyro_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔍 فحص جلسة Pyrogram\n\nابعت الـ SESSION_STRING:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الغاء", callback_data="back")]]))
    await state.set_state(SessionStates.waiting_check_pyro)

@dp.message(SessionStates.waiting_check_pyro)
async def check_pyro_session(message: types.Message, state: FSMContext):
    string_session = message.text.strip()

    try:
        client = Client(":memory:", API_ID, API_HASH, session_string=string_session)
        await client.connect()
        me = await client.get_me()
        await message.reply(f"""
✅ الجلسة شغالة 100%

الحساب: @{me.username or 'None'}
الاسم: {me.first_name}
ID: {me.id}

الحالة: نشطة ✅
""", reply_markup=main_menu(message.from_user.id))
        db_log(message.from_user.id, "check_session_pyro_success")
        await client.disconnect()
        await state.clear()
    except Exception as e:
        await message.reply(f"❌ الجلسة غلط: {str(e)}")
        await state.clear()

@dp.callback_query(F.data == "developer_info")
async def developer_info(call: CallbackQuery):
    text = f"""
👨‍💻 Developer Info

المطور: @{DEVELOPER_USERNAME}
ID: {DEVELOPER_ID}
الدعم: @{SUPPORT_GROUP}

ملاحظات مهمة:
⚠️ البوت مجاني 100%
⚠️ لا تشارك جلستك مع أي حد حتى المطور
⚠️ المطور غير مسؤول عن سوء الاستخدام
⚠️ استخدامك للبوت على مسؤوليتك

للتبليغ عن مشكلة أو اقتراح: راسل المطور
"""
    btns = InlineKeyboardBuilder()
    btns.row(InlineKeyboardButton(text="📩 راسل المطور", url=f"https://t.me/{DEVELOPER_USERNAME}"))
    btns.row(InlineKeyboardButton(text="👥 جروب الدعم", url=f"https://t.me/{SUPPORT_GROUP}"))
    btns.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="back"))

    await call.message.edit_text(text, reply_markup=btns.as_markup())

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id!= ADMIN_ID:
        await call.answer("❌ انت مش المطور", show_alert=True)
        return
    await call.message.edit_text("⚙️ لوحة تحكم المطور\n\nاختار اجراء:", reply_markup=admin_panel_menu())

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id!= ADMIN_ID: return
    total_users, extractions, conversions, banned = db_get_stats()
    text = f"""
📊 احصائيات البوت

👥 المستخدمين: {total_users}
📱 الاستخراجات: {extractions}
🔄 التحويلات: {conversions}
🚫 المحظورين: {banned}
⏰ التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}

السيرفر: Railway
الاصدار: Pro v3.0
الحالة: ✅ يعمل
"""
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_panel")]
    ]))

@dp.callback_query(F.data == "users_list")
async def users_list(call: CallbackQuery):
    if call.from_user.id!= ADMIN_ID: return
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, is_banned FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    conn.close()

    text = "👥 آخر 20 مستخدم:\n\n"
    for u in users:
        status = "🚫" if u[3] else "✅"
        text += f"{status} {u[0]} - @{u[1] or 'None'} - {u[2]}\n"

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_panel")]
    ]))

@dp.callback_query(F.data == "logs")
async def show_logs(call: CallbackQuery):
    if call.from_user.id!= ADMIN_ID: return
    logs = db_get_logs(15)

    text = "📋 آخر 15 عملية:\n\n"
    for log in logs:
        text += f"{log[0]} - {log[1]} - {log[2]} - {log[4]}\n"

    await call.message.edit_text(text[:4000], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_panel")]
    ]))

@dp.callback_query(F.data == "broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id!= ADMIN_ID: return
    await call.message.edit_text(
        "📢 رسالة جماعية\n\n"
        "ابعت الرسالة اللي عايز تبعتها لكل اليوزرز:\n\n"
        "اكتب /cancel للالغاء",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="admin_panel")]
        ])
    )
    await state.set_state(SessionStates.waiting_broadcast)

@dp.message(SessionStates.waiting_broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    if message.text == '/cancel':
        await message.reply("❌ تم الالغاء", reply_markup=main_menu(message.from_user.id))
        await state.clear()
        return

    users = db_get_all_users()
    sent = 0
    failed = 0

    status = await message.reply(f"⏳ جاري الارسال لـ {len(users)} مستخدم...")

    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 رسالة من المطور:\n\n{message.text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await status.edit_text(f"""
✅ تم الارسال

نجح: {sent}
فشل: {failed}
المجموع: {len(users)}
""", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "ban_user")
async def ban_user_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id!= ADMIN_ID: return
    await call.message.edit_text(
        "🚫 حظر/فك حظر مستخدم\n\n"
        "ابعت ID المستخدم:\n\n"
        "اكتب /cancel للالغاء",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 الغاء", callback_data="admin_panel")]
        ])
    )
    await state.set_state(SessionStates.waiting_ban_id)

@dp.message(SessionStates.waiting_ban_id)
async def ban_user_action(message: types.Message, state: FSMContext):
    if message.text == '/cancel':
        await message.reply("❌ تم الالغاء", reply_markup=main_menu(message.from_user.id))
        await state.clear()
        return

    try:
        user_id = int(message.text)
        if db_is_banned(user_id):
            db_unban_user(user_id)
            await message.reply(f"✅ تم فك حظر {user_id}", reply_markup=main_menu(message.from_user.id))
        else:
            db_ban_user(user_id)
            await message.reply(f"✅ تم حظر {user_id}", reply_markup=main_menu(message.from_user.id))
        await state.clear()
    except:
        await message.reply("❌ ID غلط")

@dp.callback_query(F.data == "restart")
async def restart_bot(call: CallbackQuery):
    if call.from_user.id!= ADMIN_ID: return
    await call.message.edit_text("♻️ جاري اعادة التشغيل...")
    os._exit(0)

@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await call.message.edit_text(
        "🔐 Session Extractor & Converter Pro v3.0\n\nاختار من القايمة 👇",
        reply_markup=main_menu(call.from_user.id)
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await check_force_sub(call.from_user.id):
        await call.message.edit_text(
            "✅ تم التحقق بنجاح\n\nاختار من القايمة 👇",
            reply_markup=main_menu(call.from_user.id)
        )
    else:
        await call.answer("❌ لسه مشتركتش في القناة", show_alert=True)

async def main():
    print("✅ Bot Started - Pro Version v3.0")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
