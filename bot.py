import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
FORCE_SUB_CHANNEL = os.environ.get('FORCE_SUB_CHANNEL', '')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

users_db = {}
stats = {"total_requests": 0, "today_requests": 0, "last_reset": str(datetime.now().date())}
blocked_users = set()

def save_data():
    with open('bot_data.json', 'w') as f:
        json.dump({"users": users_db, "stats": stats, "blocked": list(blocked_users)}, f, default=str)

def load_data():
    global users_db, stats, blocked_users
    try:
        with open('bot_data.json', 'r') as f:
            data = json.load(f)
            users_db = data.get("users", {})
            stats = data.get("stats", stats)
            blocked_users = set(data.get("blocked", []))
            if stats["last_reset"]!= str(datetime.now().date()):
                stats["today_requests"] = 0
                stats["last_reset"] = str(datetime.now().date())
    except: pass

load_data()

async def check_force_sub(user_id):
    if not FORCE_SUB_CHANNEL or user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(f"@{FORCE_SUB_CHANNEL}", user_id)
        return member.status not in ['left', 'kicked']
    except:
        return True

def estimate_creation_from_id(user_id):
    """تخمين من الـ ID - زي TG DNA"""
    if user_id < 100000000: # 2013
        base_date = datetime(2013, 8, 1, tzinfo=timezone.utc)
        offset = user_id / 1000000
    elif user_id < 500000000: # 2014-2016
        base_date = datetime(2014, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 100000000) / 2000000
    elif user_id < 1000000000: # 2016-2018
        base_date = datetime(2016, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 500000000) / 3000000
    elif user_id < 2000000000: # 2018-2021
        base_date = datetime(2018, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 1000000000) / 4000000
    elif user_id < 5000000000: # 2021-2023
        base_date = datetime(2021, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 2000000000) / 8000000
    elif user_id < 7000000000: # 2023-2024
        base_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 5000000000) / 10000000
    elif user_id < 7500000000: # 2024
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 7000000000) / 10000000
    elif user_id < 8000000000: # 2024-2025
        base_date = datetime(2024, 6, 1, tzinfo=timezone.utc)
        offset = (user_id - 7500000000) / 10000000
    else: # 2025+
        base_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        offset = (user_id - 8000000000) / 10000000

    estimated_date = base_date + timedelta(days=offset * 30)
    return estimated_date

def calculate_age(created_date):
    now = datetime.now(timezone.utc)
    diff = now - created_date
    years = diff.days // 365
    months = (diff.days % 365) // 30
    days = (diff.days % 365) % 30
    if years > 0:
        return f"{years}y {months}m {days}d"
    elif months > 0:
        return f"{months}m {days}d"
    else:
        return f"{days}d"

def main_menu(uid):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👤 User Info", callback_data="user"),
        InlineKeyboardButton(text="📢 Channel/Group", callback_data="channel")
    )
    if uid == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ Developer Panel", callback_data="admin_panel"))
    return builder.as_markup()

def admin_panel_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 الاحصائيات", callback_data="stats"),
        InlineKeyboardButton(text="📢 رسالة جماعية", callback_data="broadcast")
    )
    builder.row(
        InlineKeyboardButton(text="👥 المستخدمين", callback_data="users_list"),
        InlineKeyboardButton(text="🚫 حظر/فك حظر", callback_data="ban")
    )
    builder.row(InlineKeyboardButton(text="🔙 رجوع", callback_data="back"))
    return builder.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    if uid in blocked_users:
        await message.reply("🚫 انت محظور من استخدام البوت")
        return

    if not await check_force_sub(uid):
        btns = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{FORCE_SUB_CHANNEL}")],
            [InlineKeyboardButton(text="✅ تحققت", callback_data="check_sub")]
        ])
        await message.reply(f"""
❌ **لازم تشترك في القناة عشان تستخدم البوت**

📢 @{FORCE_SUB_CHANNEL}

بعد الاشتراك دوس "تحققت" 👇
""", reply_markup=btns)
        return

    users_db[str(uid)] = {
        "name": message.from_user.first_name,
        "username": message.from_user.username,
        "joined": datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    save_data()

    text = """
🔍 **TG DNA Bot**

⚠️ **ملاحظة:** البوت العادي ميقدرش يجيب تاريخ الانشاء الحقيقي
التاريخ الظاهر تقريبي من ID الحساب

ابعت @username أو ID 👇
"""
    await message.reply(text, reply_markup=main_menu(uid))

@dp.message(F.text.regexp(r'^@?\w+$|^t\.me/\w+$|^\d+$'))
async def get_info(message: types.Message):
    uid = message.from_user.id
    if uid in blocked_users: return

    if not await check_force_sub(uid):
        btns = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{FORCE_SUB_CHANNEL}")],
            [InlineKeyboardButton(text="✅ تحققت", callback_data="check_sub")]
        ])
        await message.reply(f"❌ **اشترك الأول**\n\n📢 @{FORCE_SUB_CHANNEL}", reply_markup=btns)
        return

    stats["total_requests"] += 1
    stats["today_requests"] += 1
    save_data()

    text = message.text.strip()
    if text.startswith('t.me/'):
        username = text.split('/')[-1]
    elif text.startswith('@'):
        username = text[1:]
    else:
        username = text

    msg = await message.reply("⏳ **جاري التحليل...**")

    try:
        chat = await bot.get_chat(username)
        
        estimated_date = estimate_creation_from_id(chat.id)
        created = estimated_date.strftime('%Y-%m')
        age = calculate_age(estimated_date)

        if chat.type == 'private':
            info_msg = f"""
**👤 User Information** ⚠️ تقريبي من ID

- **ID:** `{chat.id}` - {len(str(chat.id))} Digits
- **Name:** {chat.first_name or ''} {chat.last_name or ''}
- **Username:** @{chat.username or 'None'}
- **Created:** {created} ⚠️ تقريبي
- **Account Age:** {age}
- **Bio:** {chat.bio[:300] if chat.bio else 'None'}

⚠️ **البوت العادي ميقدرش يجيب:**
التاريخ الحقيقي، الرقم، Common Chats، Owner Groups
"""
        else:
            info_msg = f"""
**📢 Channel/Group Information**

- **ID:** `{chat.id}`
- **Title:** {chat.title}
- **Username:** @{chat.username or 'None'}
- **Type:** {chat.type}
- **Members:** {await bot.get_chat_member_count(chat.id)}
- **Created:** {created} ⚠️ تقريبي
- **Description:** {chat.description[:300] if chat.description else 'None'}
"""
        await msg.edit_text(info_msg)

    except Exception as e:
        await msg.edit_text(f"❌ **خطأ:**\n\n{str(e)}")

@dp.callback_query()
async def callback(call: types.CallbackQuery):
    uid = call.from_user.id
    data = call.data

    if data == "check_sub":
        if await check_force_sub(uid):
            await call.message.edit_text("✅ **تم التحقق بنجاح**\n\nابعت @username أو ID 👇", reply_markup=main_menu(uid))
        else:
            await call.answer("❌ لسه مشتركتش في القناة", show_alert=True)

    elif data == "admin_panel":
        if uid!= ADMIN_ID:
            await call.answer("❌ انت مش المطور", show_alert=True)
            return
        await call.message.edit_text("⚙️ **Developer Panel**", reply_markup=admin_panel_menu())

    elif data == "stats":
        if uid!= ADMIN_ID: return
        text = f"""
📊 **احصائيات البوت**

👥 المستخدمين: `{len(users_db)}`
📈 اجمالي الطلبات: `{stats['total_requests']}`
📅 طلبات اليوم: `{stats['today_requests']}`
🚫 المحظورين: `{len(blocked_users)}`
📢 قناة الاشتراك: `@{FORCE_SUB_CHANNEL or 'None'}`
"""
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 رجوع", callback_data="admin_panel")]
        ]))

    elif data == "back":
        await call.message.edit_text("🔍 **TG DNA Bot**\n\nابعت يوزر أو ايدي", reply_markup=main_menu(uid))

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
