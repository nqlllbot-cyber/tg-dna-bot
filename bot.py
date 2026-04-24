import asyncio
import os
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events, Button
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetFullChannelRequest, GetAdminedPublicChannelsRequest, GetParticipantRequest
from telethon.tl.functions.messages import GetCommonChatsRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.types import Channel, User, UserStatusOnline, UserStatusRecently
from telethon.tl.types import UserStatusOffline, UserStatusLastWeek, UserStatusLastMonth
from telethon.sessions import StringSession
from telethon.errors import UserNotParticipantError

API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
STRING_SESSION = os.environ.get('STRING_SESSION', '')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))
FORCE_SUB_CHANNEL = os.environ.get('FORCE_SUB_CHANNEL', '')

bot = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

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

async def check_force_sub(uid):
    if not FORCE_SUB_CHANNEL or uid == ADMIN_ID:
        return True
    try:
        await bot(GetParticipantRequest(channel=FORCE_SUB_CHANNEL, participant=uid))
        return True
    except UserNotParticipantError:
        return False
    except:
        return True

def estimate_creation_from_id(user_id):
    """تخمين تاريخ الانشاء من الـ ID - زي بوت TG DNA"""
    telegram_epoch = 1388534400 # 2014-01-01
    estimated_timestamp = telegram_epoch + (user_id / 100000000) * 37.8
    estimated_date = datetime.fromtimestamp(estimated_timestamp, tz=timezone.utc)
    return estimated_date

def calculate_age(created_date):
    if not created_date:
        return "Unknown", 0
    now = datetime.now(timezone.utc)
    diff = now - created_date
    years = diff.days // 365
    months = (diff.days % 365) // 30
    days = (diff.days % 365) % 30
    hours = diff.seconds // 3600
    total_days = diff.days
    if years > 0:
        return f"{years}y {months}m {days}d {hours}h", total_days
    elif months > 0:
        return f"{months}m {days}d {hours}h", total_days
    else:
        return f"{days}d {hours}h", total_days

def main_menu(uid):
    buttons = [
        [Button.inline("👤 User Info", b"user"), Button.inline("📢 Channel/Group", b"channel")],
        [Button.inline("📦 Owner Groups", b"og"), Button.inline("📢 Owner Channels", b"oc")],
        [Button.inline("🔗 Common Chats", b"common"), Button.inline("📸 Photos", b"photos")]
    ]
    if uid == ADMIN_ID:
        buttons.append([Button.inline("⚙️ Developer Panel", b"admin_panel")])
    return buttons

def admin_panel_menu():
    return [
        [Button.inline("📊 الاحصائيات", b"stats"), Button.inline("📢 رسالة جماعية", b"broadcast")],
        [Button.inline("👥 المستخدمين", b"users_list"), Button.inline("🚫 حظر/فك حظر", b"ban")],
        [Button.inline("📢 تغيير قناة الاشتراك", b"change_channel"), Button.inline("♻️ ريستارت", b"restart")],
        [Button.inline("🔙 رجوع", b"back")]
    ]

def get_status_detailed(user):
    if isinstance(user.status, UserStatusOnline):
        return "Online 🟢"
    elif isinstance(user.status, UserStatusRecently):
        return "Recently 🟡"
    elif isinstance(user.status, UserStatusLastWeek):
        return "Last week 🟠"
    elif isinstance(user.status, UserStatusLastMonth):
        return "Last month 🔴"
    elif isinstance(user.status, UserStatusOffline):
        return f"Offline ⚫ {user.status.was_online.strftime('%Y-%m-%d %H:%M')}"
    else:
        return "Long ago ⚫"

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    if uid in blocked_users:
        await event.reply("🚫 انت محظور من استخدام البوت")
        return

    if not await check_force_sub(uid):
        btns = [[Button.url("📢 اشترك في القناة", f"https://t.me/{FORCE_SUB_CHANNEL}")],
                [Button.inline("✅ تحققت", b"check_sub")]]
        await event.reply(f"""
❌ **لازم تشترك في القناة عشان تستخدم البوت**

📢 @{FORCE_SUB_CHANNEL}

بعد الاشتراك دوس "تحققت" 👇
""", buttons=btns)
        return

    users_db[str(uid)] = {
        "name": event.sender.first_name,
        "username": event.sender.username,
        "joined": datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    save_data()

    text = """
🔍 **TG DNA Pro Max - UserBot Edition**

✅ تاريخ الانشاء: دقة 100% أو تقريبي من ID
✅ معلومات كاملة بدون قيود

ابعت @username أو ID أو فورارد رسالة 👇
"""
    await event.reply(text, buttons=main_menu(uid))

@bot.on(events.NewMessage(pattern=r'^@?\w+$|^t\.me/\w+$|^\d+$'))
async def get_info(event):
    uid = event.sender_id
    if uid in blocked_users: return

    if not await check_force_sub(uid):
        btns = [[Button.url("📢 اشترك في القناة", f"https://t.me/{FORCE_SUB_CHANNEL}")],
                [Button.inline("✅ تحققت", b"check_sub")]]
        await event.reply(f"❌ **اشترك الأول**\n\n📢 @{FORCE_SUB_CHANNEL}", buttons=btns)
        return

    stats["total_requests"] += 1
    stats["today_requests"] += 1
    save_data()

    text = event.raw_text.strip()
    if text.startswith('t.me/'):
        username = text.split('/')[-1]
    elif text.startswith('@'):
        username = text[1:]
    else:
        username = text

    msg = await event.reply("⏳ **جاري التحليل...**")

    try:
        entity = await bot.get_entity(username)
        if isinstance(entity, User):
            full = await bot(GetFullUserRequest(entity))
            user = full.users[0]

            # التاريخ الحقيقي أو التقريبي
            if hasattr(user, 'date') and user.date:
                created = user.date.strftime('%Y-%m-%d %H:%M:%S UTC')
                age, total_days = calculate_age(user.date)
                accuracy = "✅ دقة 100%"
            else:
                estimated_date = estimate_creation_from_id(user.id)
                created = estimated_date.strftime('%Y-%m')
                age, total_days = calculate_age(estimated_date)
                accuracy = "⚠️ تقريبي من ID"

            dc_id = user.photo.dc_id if user.photo else "None"
            premium = "Active 💎" if user.premium else "Inactive"
            verified = "Yes ✅" if user.verified else "No"
            status = get_status_detailed(user)
            phone = f"`+{user.phone}`" if user.phone else "Hidden 🔒"
            scam = "Yes ⚠️" if user.scam else "No"
            fake = "Yes ⚠️" if user.fake else "No"
            restricted = "Yes 🔴" if user.restricted else "No"
            bot_flag = "Yes 🤖" if user.bot else "No"

            try:
                photos = await bot(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=100))
                photos_count = photos.count
                photos_status = "Set" if photos_count > 0 else "None"
            except:
                photos_count = 0
                photos_status = "None"

            try:
                common = await bot(GetCommonChatsRequest(user_id=user.id, max_id=0, limit=100))
                common_count = len(common.chats)
            except:
                common_count = 0

            info_msg = f"""
**👤 User Information** {accuracy}

- **ID:** `{user.id}` - {len(str(user.id))} Digits
- **Name:** {user.first_name or ''} {user.last_name or ''}
- **Username:** @{user.username or 'None'}
- **Phone:** {phone}
- **DC:** {dc_id}
- **Created:** {created}
- **Premium:** {premium}
- **Date:** {datetime.now().strftime('%Y-%m-%d US %H:%M')}
- **Photos:** {photos_status}
- **Scam Label:** {scam}
- **Fake Label:** {fake}
- **Paid Message:** No
- **Account Age:** {age.split()[0] if age!= "Unknown" else "Unknown"}
- **Verified:** {verified}
- **Status:** {status}
- **Common Chats:** {common_count}
- **Restricted:** {restricted} | **Bot:** {bot_flag}

**Bio:** {full.full_user.about[:300] if full.full_user.about else 'None'}
"""
            btns = [
                [Button.inline("📦 Owner Groups", f"og_{user.id}".encode())],
                [Button.inline("📢 Owner Channels", f"oc_{user.id}".encode())],
                [Button.inline("🔗 Common Chats", f"cc_{user.id}".encode())],
                [Button.inline("🔙 Back", b"back")]
            ]
            await msg.edit(info_msg, buttons=btns)

        elif isinstance(entity, Channel):
            full = await bot(GetFullChannelRequest(entity))
            channel = full.chats[0]

            if hasattr(channel, 'date') and channel.date:
                created = channel.date.strftime('%Y-%m-%d %H:%M:%S UTC')
            else:
                estimated_date = estimate_creation_from_id(channel.id)
                created = estimated_date.strftime('%Y-%m ⚠️ تقريبي')

            info_msg = f"""
**📢 Channel/Group Information**

- **ID:** `{channel.id}`
- **Title:** {channel.title}
- **Username:** @{channel.username or 'None'}
- **Type:** {'Channel 📢' if channel.broadcast else 'Group 👥'}
- **Members:** {full.full_chat.participants_count or 'Hidden'}
- **DC:** {channel.photo.dc_id if channel.photo else 'None'}
- **Created:** {created}
- **Verified:** {'Yes ✅' if channel.verified else 'No'}
- **Scam:** {'Yes ⚠️' if channel.scam else 'No'}

**About:** {full.full_chat.about[:400] or 'None'}
"""
            await msg.edit(info_msg, buttons=[[Button.inline("🔙 Back", b"back")]])

    except Exception as e:
        await msg.edit(f"❌ **خطأ:**\n\n{str(e)}")

@bot.on(events.CallbackQuery)
async def callback(event):
    uid = event.sender_id
    data = event.data.decode()

    if data == "check_sub":
        if await check_force_sub(uid):
            await event.edit("✅ **تم التحقق بنجاح**\n\nابعت @username أو ID أو فورارد رسالة 👇", buttons=main_menu(uid))
        else:
            await event.answer("❌ لسه مشتركتش في القناة", alert=True)

    elif data == "admin_panel":
        if uid!= ADMIN_ID:
            await event.answer("❌ انت مش المطور", alert=True)
            return
        await event.edit("⚙️ **Developer Panel**\n\nاختار اجراء:", buttons=admin_panel_menu())

    elif data == "stats":
        if uid!= ADMIN_ID: return
        text = f"""
📊 **احصائيات البوت**

👥 المستخدمين: `{len(users_db)}`
📈 اجمالي الطلبات: `{stats['total_requests']}`
📅 طلبات اليوم: `{stats['today_requests']}`
🚫 المحظورين: `{len(blocked_users)}`
📢 قناة الاشتراك: `@{FORCE_SUB_CHANNEL or 'None'}`
⏰ التاريخ: `{datetime.now().strftime('%Y-%m-%d %H:%M')}`
🔐 النوع: UserBot
"""
        await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"admin_panel")]])

    elif data == "change_channel":
        if uid!= ADMIN_ID: return
        await event.edit(f"📢 **قناة الاشتراك الحالية:** @{FORCE_SUB_CHANNEL or 'None'}\n\nابعت يوزر القناة الجديدة بدون @\n\nاكتب /cancel للالغاء")
        bot.add_event_handler(change_channel_handler, events.NewMessage(from_users=ADMIN_ID))

    elif data == "back":
        await event.edit("🔍 **TG DNA Pro Max**\n\nابعت يوزر أو ايدي أو فورارد", buttons=main_menu(uid))

    elif data == "users_list":
        if uid!= ADMIN_ID: return
        text = "👥 **آخر 20 مستخدم:**\n\n"
        for i, (user_id, info) in enumerate(list(users_db.items())[-20:], 1):
            text += f"{i}. {info['name']} - @{info.get('username', 'None')} - `{user_id}`\n"
        await event.edit(text[:4000], buttons=[[Button.inline("🔙 رجوع", b"admin_panel")]])

    elif data == "broadcast":
        if uid!= ADMIN_ID: return
        await event.edit("📢 **ارسل الرسالة للكل:**\n\nاكتب /cancel للالغاء")
        bot.add_event_handler(broadcast_handler, events.NewMessage(from_users=ADMIN_ID))

    elif data == "ban":
        if uid!= ADMIN_ID: return
        await event.edit("🚫 **ارسل ايدي المستخدم للحظر/فك الحظر:**\n\nاكتب /cancel للالغاء")
        bot.add_event_handler(ban_handler, events.NewMessage(from_users=ADMIN_ID))

    elif data == "restart":
        if uid!= ADMIN_ID: return
        await event.edit("♻️ **جاري اعادة التشغيل...**")
        os._exit(0)

async def change_channel_handler(event):
    global FORCE_SUB_CHANNEL
    if event.raw_text == '/cancel':
        await event.reply("❌ تم الالغاء")
        bot.remove_event_handler(change_channel_handler)
        return
    FORCE_SUB_CHANNEL = event.raw_text.replace('@', '')
    await event.reply(f"✅ **تم تغيير قناة الاشتراك إلى:** @{FORCE_SUB_CHANNEL}\n\nاعمل Redeploy عشان التغيير يتثبت")
    bot.remove_event_handler(change_channel_handler)

async def broadcast_handler(event):
    if event.raw_text == '/cancel':
        await event.reply("❌ تم الالغاء")
        bot.remove_event_handler(broadcast_handler)
        return
    msg = event.raw_text
    sent = 0
    failed = 0
    status = await event.reply("⏳ جاري الارسال...")
    for user_id in users_db.keys():
        try:
            await bot.send_message(int(user_id), f"📢 **رسالة من المطور:**\n\n{msg}")
            sent += 1
            await asyncio.sleep(0.3)
        except: failed += 1
    await status.edit(f"✅ **تم الارسال**\n\nنجح: {sent}\nفشل: {failed}")
    bot.remove_event_handler(broadcast_handler)

async def ban_handler(event):
    if event.raw_text == '/cancel':
        await event.reply("❌ تم الالغاء")
        bot.remove_event_handler(ban_handler)
        return
    try:
        user_id = int(event.raw_text)
        if user_id in blocked_users:
            blocked_users.remove(user_id)
            await event.reply(f"✅ تم فك حظر `{user_id}`")
        else:
            blocked_users.add(user_id)
            await event.reply(f"✅ تم حظر `{user_id}`")
        save_data()
    except:
        await event.reply("❌ ايدي غلط")
    bot.remove_event_handler(ban_handler)

async def main():
    await bot.start()
    print("✅ TG DNA UserBot شغال")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
