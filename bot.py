from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError, UserDeactivatedBanError, UserAlreadyParticipantError
from telethon.tl.functions.channels import GetParticipantRequest, JoinChannelRequest
from telethon.tl.types import MessageEntityCustomEmoji, MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl, MessageEntityUrl, Channel
from telethon.errors.rpcerrorlist import ChatWriteForbiddenError, ChatAdminRequiredError, UserBannedInChannelError, SlowModeWaitError, ChannelPrivateError, UserNotParticipantError, AuthKeyUnregisteredError, MessageNotModifiedError
import asyncio
import json
import os
from datetime import datetime, timedelta
import random
import re

# ===== بيانات البوت =====
API_ID = 37879014
API_HASH = 'db129fe3286650ad869b2891abd72df2'
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [1059762618, 29449730]  # حط إيدي الأدمن التاني مكان 123456789
DEVELOPER_USERNAME = 'X_Rr_o'
DEVELOPER_LINK = f'https://t.me/{DEVELOPER_USERNAME}'
REQUIRED_CHANNELS = ['CG_EC']
DB_FILE = 'database.json'
BACKUP_FILE = 'sessions_backup.json'
SUB_PRICE = 2
MAX_ACCOUNTS = 1
FREE_TRIAL_DAYS = 0

bot = TelegramClient('bot', API_ID, API_HASH)
db = {'users': {}, 'codes': {}, 'stats': {'total_sent': 0}, 'login_notifications': True}
waiting_for = {}
active_clients = {}
running_tasks = {}
user_clients = {}

STEALTH_MODES = {
    'fast': {'group_delay': [2, 5], 'name': '⚡ سريع'},
    'balanced': {'group_delay': [5, 10], 'name': '⚖️ متوازن'},
    'safe': {'group_delay': [10, 20], 'name': '🛡️ آمن جدا'}
}

def load_db():
    global db
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except:
        save_db()

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def backup_sessions():
    backup = {}
    for uid, user in db['users'].items():
        for acc_id, acc in user.get('accounts', {}).items():
            if acc.get('session'):
                backup[f"{uid}_{acc_id}"] = {
                    'phone': acc['phone'],
                    'session': acc['session'],
                    'name': acc['name'],
                    'user_id': uid,
                    'backed_up_at': datetime.now().isoformat()
                }
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)

def get_user_data(uid):
    uid = str(uid)
    if uid not in db['users']:
        db['users'][uid] = {
            'sub_end': None,
            'accounts': {}, 'current_account': None,
            'messages': [{'text': '', 'entities': [], 'file_id': None, 'type': 'text'}, {'text': '', 'entities': [], 'file_id': None, 'type': 'text'}],
            'publish_interval': 5, 'flood_protection': 2, 'stealth_mode': 'balanced',
            'auto_reply': False, 'auto_reply_msg': '', 'auto_reply_entities': [],
            'welcome_msg': '', 'welcome_entities': [],
            'welcome_sent': [], 'is_trial': False, 'used_trial': False
        }
        save_db()
    if 'welcome_sent' not in db['users'][uid]:
        db['users'][uid]['welcome_sent'] = []
    if 'used_trial' not in db['users'][uid]:
        db['users'][uid]['used_trial'] = False
    if 'auto_reply_entities' not in db['users'][uid]:
        db['users'][uid]['auto_reply_entities'] = []
    if 'welcome_entities' not in db['users'][uid]:
        db['users'][uid]['welcome_entities'] = []
    if isinstance(db['users'][uid]['messages'][0], str):
        old_msgs = db['users'][uid]['messages']
        db['users'][uid]['messages'] = [
            {'text': old_msgs[0] if len(old_msgs) > 0 else '', 'entities': [], 'file_id': None, 'type': 'text'},
            {'text': old_msgs[1] if len(old_msgs) > 1 else '', 'entities': [], 'file_id': None, 'type': 'text'}
        ]
    return db['users'][uid]

def is_subscribed(uid):
    if uid == ADMIN_ID:
        return True
    user = get_user_data(uid)
    sub_end = user.get('sub_end')
    if not sub_end:
        return False
    try:
        return datetime.fromisoformat(sub_end) > datetime.now()
    except:
        return False

def get_account(uid):
    user = get_user_data(uid)
    acc_id = user.get('current_account')
    if not acc_id or acc_id not in user['accounts']:
        return None
    return user['accounts'][acc_id]

def get_account_defaults(acc):
    defaults = {
        'active': False, 'groups': [], 'name': 'حساب جديد',
        'phone': '', 'session': '', 'sent_count': 0,
        'last_error': None, 'created_at': datetime.now().isoformat(),
        'replied_to': []
    }
    for k, v in defaults.items():
        if k not in acc:
            acc[k] = v
    return acc

def gen_code(days=30):
    code = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=12))
    db['codes'][code] = days
    save_db()
    return code

def extract_entities_from_message(message):
    entities = []
    if message.entities:
        for ent in message.entities:
            if isinstance(ent, MessageEntityCustomEmoji):
                entities.append({
                    'type': 'custom_emoji',
                    'offset': ent.offset,
                    'length': ent.length,
                    'document_id': ent.document_id
                })
            elif isinstance(ent, MessageEntityBold):
                entities.append({'type': 'bold', 'offset': ent.offset, 'length': ent.length})
            elif isinstance(ent, MessageEntityItalic):
                entities.append({'type': 'italic', 'offset': ent.offset, 'length': ent.length})
            elif isinstance(ent, MessageEntityCode):
                entities.append({'type': 'code', 'offset': ent.offset, 'length': ent.length})
            elif isinstance(ent, MessageEntityPre):
                entities.append({'type': 'pre', 'offset': ent.offset, 'length': ent.length, 'language': ent.language})
            elif isinstance(ent, MessageEntityTextUrl):
                entities.append({'type': 'text_url', 'offset': ent.offset, 'length': ent.length, 'url': ent.url})
            elif isinstance(ent, MessageEntityUrl):
                entities.append({'type': 'url', 'offset': ent.offset, 'length': ent.length})
    return entities

def build_entities(saved_entities):
    entities = []
    for ent in saved_entities:
        if ent['type'] == 'custom_emoji':
            entities.append(MessageEntityCustomEmoji(
                offset=ent['offset'],
                length=ent['length'],
                document_id=ent['document_id']
            ))
        elif ent['type'] == 'bold':
            entities.append(MessageEntityBold(offset=ent['offset'], length=ent['length']))
        elif ent['type'] == 'italic':
            entities.append(MessageEntityItalic(offset=ent['offset'], length=ent['length']))
        elif ent['type'] == 'code':
            entities.append(MessageEntityCode(offset=ent['offset'], length=ent['length']))
        elif ent['type'] == 'pre':
            entities.append(MessageEntityPre(offset=ent['offset'], length=ent['length'], language=ent.get('language', '')))
        elif ent['type'] == 'text_url':
            entities.append(MessageEntityTextUrl(offset=ent['offset'], length=ent['length'], url=ent['url']))
        elif ent['type'] == 'url':
            entities.append(MessageEntityUrl(offset=ent['offset'], length=ent['length']))
    return entities

def main_menu(uid):
    btns = [
        [Button.inline("📱 اضافة حساب", b"add_account")],
        [Button.inline("⚙️ اعدادات النشر", b"pub_settings"), Button.inline("📊 تحليل النشر", b"analyze")],
        [Button.inline("🔄 تشغيل", b"start_pub"), Button.inline("⛔ ايقاف", b"stop_pub")],
        [Button.inline("✨ مميزات البوت", b"features"), Button.inline("💡 نصائح الحماية", b"tips")],
        [Button.url("👨‍💻 المبرمج", DEVELOPER_LINK)]
    ]
    if uid == ADMIN_ID:
        btns.insert(-1, [Button.inline("👑 لوحة المبرمج", b"admin")])
    return btns


def accounts_menu(uid):
    user = get_user_data(uid)
    accounts = user['accounts']
    btns = []

    for acc_id, acc in accounts.items():
        acc = get_account_defaults(acc)
        status = "🟢" if acc['active'] else "⚪"
        current = " 👈" if user['current_account'] == acc_id else ""
        btns.append([Button.inline(f"{status} {acc['name']}{current}", f"select_acc_{acc_id}".encode())])

    if len(accounts) < MAX_ACCOUNTS:
        btns.append([Button.inline("➕ اضافة حساب", b"add_account")])

    btns.append([Button.inline("🔙 رجوع", b"back_main")])
    return btns

def account_details_menu(uid, acc_id):
    acc = get_user_data(uid)['accounts'][acc_id]
    acc = get_account_defaults(acc)
    status = "🟢 يعمل" if acc['active'] else "🔴 متوقف"

    btns = [
        [Button.inline(f"{status}", f"toggle_acc_{acc_id}".encode())],
        [Button.inline("✏️ تغيير الاسم", f"rename_acc_{acc_id}".encode())],
        [Button.inline("👥 الجروبات", f"groups_acc_{acc_id}".encode())],
        [Button.inline("💾 نسخ السيشن", f"copy_session_{acc_id}".encode())],
        [Button.inline("🗑️ حذف الحساب", f"delete_acc_{acc_id}".encode())],
        [Button.inline("🔙 رجوع", b"accounts_menu")]
    ]
    return btns

def pub_settings_menu(uid):
    user = get_user_data(uid)
    acc = get_account(uid)
    if not acc:
        return [[Button.inline("❌ مفيش حساب محدد", b"accounts_menu")], [Button.inline("🔙 رجوع", b"back_main")]]
    acc = get_account_defaults(acc)

    status = "🟢 يعمل" if acc['active'] else "🔴 متوقف"
    flood_level = ["❌", "🟡", "🟢", "🛡️"][user['flood_protection']]
    stealth = STEALTH_MODES[user['stealth_mode']]['name']
    auto_reply = "✅" if user['auto_reply'] else "❌"

    msg1 = user['messages'][0]
    msg2 = user['messages'][1]
    msg1_status = "✅ ملصق" if msg1['type'] == 'sticker' else "✅ نص" if msg1['text'] else "❌"
    msg2_status = "✅ ملصق" if msg2['type'] == 'sticker' else "✅ نص" if msg2['text'] else "❌"

    btns = [
        [Button.inline(f"📱 {acc['name']} | {status}", b"accounts_menu")],
        [Button.inline("🔄 جلب الجروبات", b"fetch_groups"), Button.inline("👥 الجروبات", b"manage_groups")],
        [Button.inline(f"📝 رسالة 1 {msg1_status}", b"msg1"), Button.inline(f"📝 رسالة 2 {msg2_status}", b"msg2")],
        [Button.inline(f"⏱️ النشر كل {user['publish_interval']} دقيقة", b"pub_interval")],
        [Button.inline(f"{flood_level} حماية التجميد", b"flood_level")],
        [Button.inline(f"{stealth} التخفي", b"stealth_mode")],
        [Button.inline(f"{auto_reply} رد تلقائي بالمنشن", b"auto_reply"), Button.inline("✏️ تعيين الرد", b"set_reply_msg")],
        [Button.inline("👋 تعيين الترحيب بالخاص", b"set_welcome"), Button.inline("🗑️ مسح المردود عليهم", b"clear_replied")],
        [Button.inline("🔙 رجوع", b"back_main")]
    ]
    return btns

def admin_menu():
    notif_status = "✅" if db.get('login_notifications', True) else "❌"
    return [
        [Button.inline("➕ توليد كود", b"gen_code"), Button.inline("📋 الاكواد", b"list_codes")],
        [Button.inline("👤 تفعيل VIP", b"activate_vip"), Button.inline("🚫 الغاء VIP", b"deactivate_vip")],
        [Button.inline(f"{notif_status} اشعارات الدخول", b"toggle_notifications")],
        [Button.inline("💾 نسخة احتياطية", b"backup_sessions"), Button.inline("📥 تحميل النسخ", b"download_backup")],
        [Button.inline("👥 المستخدمين", b"users"), Button.inline("📊 احصائيات", b"admin_stats")],
        [Button.inline("📢 اذاعة", b"broadcast")],
        [Button.inline("🔙 رجوع", b"back_main")]
    ]

async def get_user_client(uid):
    acc = get_account(uid)
    if not acc or 'session' not in acc:
        return None

    key = f"{uid}_{get_user_data(uid)['current_account']}"

    if key in user_clients:
        try:
            if user_clients[key].is_connected():
                return user_clients[key]
            else:
                del user_clients[key]
        except:
            del user_clients[key]

    try:
        client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH, device_model="iPhone 17 Pro", system_version="iOS 17.5", app_version="10.9.2")
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return None
        user_clients[key] = client
        return client
    except:
        return None

async def log_error(uid, error_text):
    try:
        await bot.send_message(uid, f"⚠️ **تشخيص:**\n\n{error_text}")
    except:
        pass
        
async def safe_edit(event, text, buttons=None):
    try:
        await event.edit(text, buttons=buttons)
    except MessageNotModifiedError:
        pass
    except:
        pass

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    user = get_user_data(uid)

    # 1. تحقق من الاشتراك في القنوات
    for channel in REQUIRED_CHANNELS:
        try:
            await bot(GetParticipantRequest(channel, uid))
        except:
            btns = [
                [Button.url(f"🔔 اشترك منا اولا", f"https://t.me/{channel}")],
                [Button.inline("✅ تحققت", b"check_sub")]
            ]
            await event.reply("🔒 اشترك في القناة اولا", buttons=btns)
            return

    # 2. لو مش مشترك في البوت
    btns = []
    if not is_subscribed(uid):
        btns = [
            [Button.inline("🔑 تفعيل كود", b"activate")],
            [Button.inline("✨ المميزات", b"features")],
            [Button.inline("🤖 شراء بوت مماثل", b"buy_bot")],
            [Button.url("👨‍💻 المطور", DEVELOPER_LINK)]
        ]

        welcome_text = """<b>👋 أهلاً بيك في بوت النشر التلقائي</b>

🚀 <b>نشر تلقائي في المجموعات آمن جدا</b>

🤖 <b>رد تلقائي ذكي متخطي الباند نهائيا</b>

🛡️ <b>حماية متقدمة عالية جدا ضد التجميد والفلود</b>

📂 <i>البوت باشتراك مدفوع</i>
⚙️ <i> الـشهر سـعر 2 دولار</i>
⚙️ <i> الـسنه سـعر 5 دولار</i>
"""
        await event.reply(welcome_text, buttons=btns, parse_mode='html')
        return

    # 3. لو مشترك/مطور - القائمة الرئيسية
    days = (datetime.fromisoformat(user['sub_end']) - datetime.now()).days if user.get('sub_end') else 9999
    acc = get_account(uid)
    acc = get_account_defaults(acc) if acc else None
    sent = acc['sent_count'] if acc else 0
    accounts_count = len(user['accounts'])

    text = f"🔥 **اهلا بيك في بوت النشر المتطور الاحترافي**\n\n"
    
    text += f"📤 الرسائل المرسلة: {sent}\n\n"
    
    text += "اختر من القائمة:"
    await event.reply(text, buttons=main_menu(uid))

@bot.on(events.CallbackQuery)
async def callback(event):
    uid = event.sender_id
    data = event.data.decode()
    user = get_user_data(uid)
    acc = get_account(uid)

    if data == 'back_main':
        await start(event)
        return

    elif data == 'check_sub':
        await start(event)
        return

    elif data == 'features':
        text = f"✨ **مميزات البوت الكاملة**\n\n"

        text += "🔥 **النشر التلقائي:**\n"

        
        text += f"1️⃣ حساب واحد برقم الهاتف\n"
        text += "2️⃣ النشر في الجروبات فقط\n"
        text += "3️⃣ رسالتين نشر - نص بـ ميزة بريميوم\n"
        text += "4️⃣ دعم الايموجي البريميوم في النص\n"
        text += "5️⃣ حذف تلقائي للجروب لو اتحظرت منه\n"
        text += "6️⃣ تحديد الوقت بالدقايق بين كل دورة\n"
        text += "7️⃣ جلب الجروبات تلقائي من الحساب\n\n"
        
        text += "🛡️ **الحماية من الحظر:**\n"

        
        text += "1️⃣ 3 مستويات حماية فلود: خفيف/متوسط/قوي\n"
        text += "2️⃣ 3 اوضاع تخفي: سريع/متوازن/آمن جدا\n"
        text += "3️⃣ تأخير عشوائي بين كل جروب\n"
        text += "4️⃣ معالجة اخطاء الفلود تلقائي\n"
        text += "5️⃣ ايقاف تلقائي لو الحساب اتحظر\n"
        
        text += "🤖 **الرد التلقائي:**\n"

        
        text += "1️⃣ رد على المنشن والريبلاي في الجروبات\n"
        text += "2️⃣ يرد مرة واحدة بس على كل شخص\n"
        text += "3️⃣ رسالة ترحيب للخاص اول مرة\n"
        text += "4️⃣ دعم الايموجي البريميوم في الرد والترحيب\n\n"
        
        text += f"💰 **السعر:** ${SUB_PRICE}/شهر فقط"
        
        btns = [
        [Button.url("👨‍💻 المبرمج", DEVELOPER_LINK)],
        [Button.inline("رجوع", b"back_main")]
        ]
        await safe_edit(event, text, buttons=btns)
        return

    elif data == 'activate':
        waiting_for[uid] = 'code'
        await safe_edit(event, "🔑 **ارسل كود التفعيل:**", buttons=[[Button.inline("🔙 رجوع", b"back_main")]])
        return

    elif data == 'add_account':
        if len(user['accounts']) >= MAX_ACCOUNTS:
            await event.answer(f"❌ مسموح بحساب واحد فقط", alert=True)
            return
        waiting_for[uid] = 'phone_login'
        await safe_edit(event, "📱 **ابعت رقم الحساب:**\n\nمثال: +201234567890\n\n**البوت هيسجل دخول مباشر - الكود هيوصل على تيليجرام الرقم**", buttons=[[Button.inline("🔙 رجوع", b"back_main")]])
        return

    elif data == 'accounts_menu':
        accounts_count = len(user['accounts'])
        text = f"📱 **ادارة الحسابات**\n\n"
        text += f"العدد: {accounts_count}/{MAX_ACCOUNTS}\n\n"
        if user['current_account']:
            current_acc = get_account_defaults(user['accounts'][user['current_account']])
            text += f"الحساب الحالي: **{current_acc['name']}**\n"
            text += f"المرسلة: {current_acc['sent_count']}\n"
            text += f"الجروبات: {len(current_acc['groups'])}\n\n"
        text += "اختار حساب للتفاصيل او اضف جديد:"
        await safe_edit(event, text, buttons=accounts_menu(uid))
        return

    elif data.startswith('select_acc_'):
        acc_id = data.split('_')[2]
        user['current_account'] = acc_id
        save_db()
        acc = get_account_defaults(user['accounts'][acc_id])
        text = f"📱 **{acc['name']}**\n\n"
        text += f"📞 الرقم: `{acc['phone']}`\n"
        text += f"👥 الجروبات: {len(acc['groups'])}\n"
        text += f"📤 المرسلة: {acc['sent_count']}\n"
        text += f"الحالة: {'🟢 يعمل' if acc['active'] else '🔴 متوقف'}\n"
        text += f"تاريخ الاضافة: {acc['created_at'][:10]}\n\n"
        text += "اختار العملية:"
        await safe_edit(event, text, buttons=account_details_menu(uid, acc_id))
        return

    elif data.startswith('copy_session_'):
        acc_id = data.split('_')[2]
        acc = get_account_defaults(user['accounts'][acc_id])
        session = acc.get('session', '')
        await event.answer("✅ السيشن اتنسخ في الرسالة", alert=True)
        await event.respond(f"💾 **سيشن {acc['name']}:**\n\n```\n{session}\n```\n\n⚠️ **احتفظ بيه في مكان آمن**")
        return

    elif data.startswith('toggle_acc_'):
        acc_id = data.split('_')[2]
        acc = get_account_defaults(user['accounts'][acc_id])
        acc['active'] = not acc['active']
        save_db()

        key = f"{uid}_{acc_id}"
        if key in running_tasks:
            try:
                running_tasks[key].cancel()
                await asyncio.sleep(0.5)
            except:
                pass
            del running_tasks[key]

        if acc['active']:
            user['current_account'] = acc_id
            task = asyncio.create_task(publish_loop(uid))
            running_tasks[key] = task
            if user['auto_reply']:
                asyncio.create_task(start_auto_reply(uid))

        await event.answer("✅ تم التشغيل" if acc['active'] else "⛔ تم الايقاف", alert=True)
        await safe_edit(event, f"📱 **{acc['name']}**\n\n📞 الرقم: `{acc['phone']}`\n👥 الجروبات: {len(acc['groups'])}\n📤 المرسلة: {acc['sent_count']}\nالحالة: {'🟢 يعمل' if acc['active'] else '🔴 متوقف'}\nتاريخ الاضافة: {acc['created_at'][:10]}\n\nاختار العملية:", buttons=account_details_menu(uid, acc_id))
        return

    elif data.startswith('rename_acc_'):
        acc_id = data.split('_')[2]
        waiting_for[uid] = f'rename_{acc_id}'
        await safe_edit(event, "✏️ **ابعت الاسم الجديد للحساب:**", buttons=[[Button.inline("🔙 رجوع", f"select_acc_{acc_id}".encode())]])
        return

    elif data.startswith('delete_acc_'):
        acc_id = data.split('_')[2]
        if acc_id in user['accounts']:
            key = f"{uid}_{acc_id}"
            if key in running_tasks:
                try:
                    running_tasks[key].cancel()
                    await asyncio.sleep(0.5)
                except:
                    pass
                del running_tasks[key]
            if key in user_clients:
                try:
                    await user_clients[key].disconnect()
                except:
                    pass
                del user_clients[key]
            del user['accounts'][acc_id]
            if user['current_account'] == acc_id:
                user['current_account'] = None
            save_db()
            await event.answer("✅ تم حذف الحساب", alert=True)
        await safe_edit(event, f"📱 **ادارة الحسابات**\n\nالعدد: {len(user['accounts'])}/{MAX_ACCOUNTS}\n\nاختار حساب للتفاصيل او اضف جديد:", buttons=accounts_menu(uid))
        return

    elif data == 'pub_settings':
        if not acc:
            await event.answer("❌ حدد حساب من ادارة الحسابات الاول", alert=True)
            await safe_edit(event, f"📱 **ادارة الحسابات**\n\nالعدد: {len(user['accounts'])}/{MAX_ACCOUNTS}\n\nاختار حساب للتفاصيل او اضف جديد:", buttons=accounts_menu(uid))
            return
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        return
    
    elif data == 'fetch_groups':
        if not acc:
            await event.answer("❌ ضيف حساب الاول", alert=True)
            return
        msg = await event.edit("⏳ **جاري جلب الجروبات...**")
        client = await get_user_client(uid)
        if not client:
            await msg.edit("❌ **الحساب غير متصل**\n\nاحذف الحساب وضيفه من جديد", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
            return
        groups = []
        total_dialogs = 0
        try:
            async for dialog in client.iter_dialogs():
                total_dialogs += 1
                if (dialog.is_group or getattr(dialog.entity, 'megagroup', False) or getattr(dialog.entity, 'gigagroup', False)) and not getattr(dialog.entity, 'broadcast', False):
                    if dialog.entity.username:
                        groups.append(f"@{dialog.entity.username}")
                    else:
                        groups.append(f"-100{dialog.entity.id}")
        except Exception as e:
            await msg.edit(f"❌ **خطأ في الجلب:** {str(e)}", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
            return
        acc = get_account_defaults(acc)
        acc['groups'] = groups
        save_db()
        await msg.edit(f"✅ **تم جلب {len(groups)} جروب**\n\n📊 اجمالي المحادثات: {total_dialogs}", buttons=pub_settings_menu(uid))
        return

    elif data == 'manage_groups':
        acc = get_account_defaults(acc)
        groups_text = '\n'.join([f"{i+1}. `{g}`" for i, g in enumerate(acc['groups'][:20])])
        if len(acc['groups']) > 20:
            groups_text += f"\n... و {len(acc['groups'])-20} اخرين"
        btns = [
            [Button.inline("➕ اضافة", b"add_group"), Button.inline("🗑️ حذف", b"del_group")],
            [Button.inline("🗑️ تفريغ الكل", b"clear_groups")],
            [Button.inline("🔙 رجوع", b"pub_settings")]
        ]
        await safe_edit(event, f"👥 **الجروبات ({len(acc['groups'])}):**\n\n{groups_text or 'لا يوجد'}", buttons=btns)
        return

    elif data == 'clear_groups':
        acc = get_account_defaults(acc)
        acc['groups'] = []
        save_db()
        await event.answer("✅ تم تفريغ كل الجروبات", alert=True)
        await safe_edit(event, "👥 **الجروبات (0):**\n\nلا يوجد", buttons=[
            [Button.inline("➕ اضافة", b"add_group"), Button.inline("🗑️ حذف", b"del_group")],
            [Button.inline("🗑️ تفريغ الكل", b"clear_groups")],
            [Button.inline("🔙 رجوع", b"pub_settings")]
        ])
        return

    elif data == 'add_group':
        waiting_for[uid] = 'add_group'
        await safe_edit(event, "➕ **ابعت يوزر الجروب او الايدي:**\n\nمثال: @m250025 او -1001234567890\n\n⚠️ **مهم:** الحساب لازم يكون عضو في الجروب", buttons=[[Button.inline("🔙 رجوع", b"manage_groups")]])
        return

    elif data == 'del_group':
        waiting_for[uid] = 'del_group'
        await safe_edit(event, "🗑️ **ابعت رقم الجروب للحذف:**", buttons=[[Button.inline("🔙 رجوع", b"manage_groups")]])
        return

    elif data == 'msg1':
        waiting_for[uid] = 'msg1'
        await safe_edit(event, "📝 **ابعت الرسالة الاولى:**\n\nتقدر تبعت نص مع ايموجي بريميوم او ملصق\nالبوت هيحفظه وينشره", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
        return

    elif data == 'msg2':
        waiting_for[uid] = 'msg2'
        await safe_edit(event, "📝 **ابعت الرسالة التانية:**\n\nتقدر تبعت نص مع ايموجي بريميوم او ملصق\nالبوت هيبدل بينهم تلقائي", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
        return

    elif data == 'pub_interval':
        waiting_for[uid] = 'pub_interval'
        await safe_edit(event, "⏱️ **ابعت الوقت بين كل دورة نشر بالدقايق:**\n\nمثال: 5\nيعني يبعت لكل الجروبات وبعدين يستنى 5 دقايق ويعيد\n\nاقل حاجة: 1 دقيقة", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
        return

    elif data == 'flood_level':
        user['flood_protection'] = (user['flood_protection'] + 1) % 4
        save_db()
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        return

    elif data == 'stealth_mode':
        modes = list(STEALTH_MODES.keys())
        current = modes.index(user['stealth_mode'])
        user['stealth_mode'] = modes[(current + 1) % len(modes)]
        save_db()
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        return

    elif data == 'auto_reply':
        user['auto_reply'] = not user['auto_reply']
        save_db()
        if user['auto_reply'] and acc['active']:
            asyncio.create_task(start_auto_reply(uid))
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        return

    elif data == 'set_reply_msg':
        waiting_for[uid] = 'reply_msg'
        await safe_edit(event, "✏️ **ارسل رسالة الرد التلقائي:**\n\nدي هتتبعت لما حد يعملك منشن او ريبلاي\n💎 **تقدر تستخدم ايموجي بريميوم**", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
        return

    elif data == 'set_welcome':
        waiting_for[uid] = 'welcome_msg'
        await safe_edit(event, "👋 **ارسل رسالة الترحيب:**\n\nدي هتتبعت لاي حد يبعتلك خاص اول مرة\n💎 **تقدر تستخدم ايموجي بريميوم**", buttons=[[Button.inline("🔙 رجوع", b"pub_settings")]])
        return

    elif data == 'clear_replied':
        if acc:
            acc['replied_to'] = []
            save_db()
            await event.answer("✅ تم مسح قائمة المردود عليهم", alert=True)
        return

    elif data == 'start_pub':
        if not acc:
            await event.answer("❌ حدد حساب من ادارة الحسابات الاول", alert=True)
            return
        if not acc['groups']:
            await event.answer("❌ ضيف جروبات الاول - جلب الجروبات", alert=True)
            return
        if not user['messages'][0]['text'] and not user['messages'][0]['file_id']:
            await event.answer("❌ ضيف رسالة على الاقل - رسالة 1", alert=True)
            return

        acc = get_account_defaults(acc)
        acc['active'] = True
        acc['last_error'] = None
        save_db()

        key = f"{uid}_{user['current_account']}"

        if key in running_tasks:
            try:
                running_tasks[key].cancel()
                await asyncio.sleep(0.5)
            except:
                pass
            del running_tasks[key]

        task = asyncio.create_task(publish_loop(uid))
        running_tasks[key] = task

        if user['auto_reply']:
            asyncio.create_task(start_auto_reply(uid))

        await event.answer(f"✅ بدأ النشر كل {user['publish_interval']} دقيقة", alert=True)
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        await log_error(uid, f'🔄 تم الضغط على تشغيل - ببدأ النشر في {len(acc["groups"])} جروب')
        return

    elif data == 'stop_pub':
        if acc:
            acc['active'] = False
            save_db()
            key = f"{uid}_{user['current_account']}"
            if key in running_tasks:
                try:
                    running_tasks[key].cancel()
                    await asyncio.sleep(0.5)
                except:
                    pass
                del running_tasks[key]
        await event.answer("⛔ تم الايقاف", alert=True)
        await safe_edit(event, "⚙️ **اعدادات النشر الاحترافية**", buttons=pub_settings_menu(uid))
        await log_error(uid, '⛔ تم ايقاف النشر يدوي')
        return

    elif data == 'analyze':
        if not acc:
            await event.answer("❌ حدد حساب الاول", alert=True)
            return
        acc = get_account_defaults(acc)
        client = await get_user_client(uid)
        status = "🟢 سليم" if client else "🔴 محظور او غير متصل"

        text = f"📊 **تحليل وضع النشر**\n\n"
        text += f"الحساب: `{acc['name']}`\n"
        text += f"الحالة: {status}\n"
        text += f"الجروبات: {len(acc['groups'])}\n"
        text += f"المرسلة: {acc['sent_count']}\n"
        text += f"النشر كل: {user['publish_interval']} دقيقة\n"
        text += f"وضع التخفي: {STEALTH_MODES[user['stealth_mode']]['name']}\n"
        text += f"حماية الفلود: مستوى {user['flood_protection']}\n"
        text += f"مردود عليهم: {len(acc['replied_to'])} شخص\n"
        text += f"اخر خطأ: {acc.get('last_error') or 'لا يوجد'}\n\n"

        if acc.get('last_error'):
            text += "⚠️ **تحذير:** حصل خطأ مؤخرا. فعل وضع آمن جدا"
        else:
            text += "✅ **الحساب آمن** - كمل النشر"

        await safe_edit(event, text, buttons=[[Button.inline("🔙 رجوع", b"back_main")]])
        return

    elif data == 'tips':
        text = f"💡 **نصائح الحماية من الحظر**\n\n"
        
        text += "1️⃣ **استخدم وضع آمن جدا** 🛡️\n"
        text += "2️⃣ **النشر كل 5 دقايق او اكتر**\n"
        text += "3️⃣ **متزودش عن 10 جروب** للحساب\n"
        text += "4️⃣ **غير الرسالة كل فترة**\n"
        text += "5️⃣ **فعل حماية الفلود مستوى 3**\n"
        text += "6️⃣ **فعل الرد التلقائي** على الخاص\n"
        text += "7️⃣ **استخدم رسالتين** وبدل بينهم\n"
        text += "8️⃣ **متدخلش جروبات كتير مرة واحدة**\n"
        text += "9️⃣ **لو جالك فلود استنى 24 ساعة**\n"
        
        text += "🔟 **حساب واحد فقط مسموح**\n\n"
        await safe_edit(event, text, buttons=[[Button.inline("🔙 رجوع", b"back_main")]])
        return

    elif data == 'buy_bot':
        text = f"🛒 **شراء بوت مماثل**\n\n"
        text += f"💰 **السعر:** $25 **فقط\n"
        
        text += "✅ **المميزات**\n"
        
        text += f"🔑 حساب واحد برقم الهاتف\n"
        text += "📝 نشر تلقائي احترافي\n"
        text += "🎭 دعم الملصقات البريميوم\n"
        text += "💎 دعم الايموجي البريميوم\n"
        text += "🛡️ 3 مستويات حماية\n"
        text += "🥷 3 اوضاع تخفي\n"
        text += "🤖 رد تلقائي على المنشن والريبلاي\n"
        text += "👋 ترحيب تلقائي بالخاص\n"
        text += "📊 تحليل و احصائيات\n"
        text += "♾️ اشتراك مدة 12 شـهر\n\n"
        await safe_edit(event, text, buttons=[[Button.url("👨‍💻 المبرمج", "https://t.me/aabdulrahmaan")], [Button.inline("🔙 رجوع", b"back_main")]])
        return

    elif data == 'admin':
        if uid!= ADMIN_ID:
            return
        await safe_edit(event, "👑 **لوحة الادمن**", buttons=admin_menu())
        return

    elif data == 'gen_code':
        if uid!= ADMIN_ID:
            return
        code = gen_code(30)
        await event.answer(f"✅ الكود اتنسخ في الرسالة", alert=True)
        await event.respond(f"🔑 **كود 30 يوم:**\n\n```\n{code}\n```\n\nانسخ الكود وابعت للعميل")
        return

    elif data == 'list_codes':
        if uid!= ADMIN_ID:
            return
        codes_text = "\n".join([f"`{code}` - {days} يوم" for code, days in db['codes'].items()]) or "لا يوجد اكواد"
        await safe_edit(event, f"📋 **الاكواد المتاحة:**\n\n{codes_text}", buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

    elif data == 'activate_vip':
        if uid!= ADMIN_ID:
            return
        waiting_for[uid] = 'vip_activate'
        await safe_edit(event, "👤 **ابعت ID المستخدم + عدد الايام**\n\nمثال: 123456789 30\nيعني فعل 30 يوم", buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

    elif data == 'deactivate_vip':
        if uid!= ADMIN_ID:
            return
        waiting_for[uid] = 'vip_deactivate'
        await safe_edit(event, "👤 **ابعت ID المستخدم للالغاء**\n\nمثال: 123456789", buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

    elif data == 'toggle_notifications':
        if uid!= ADMIN_ID:
            return
        db['login_notifications'] = not db.get('login_notifications', True)
        save_db()
        await safe_edit(event, "👑 **لوحة المطور**", buttons=admin_menu())
        return

    elif data == 'backup_sessions':
        if uid!= ADMIN_ID:
            return
        backup_sessions()
        await event.answer("✅ تم عمل نسخة احتياطية لكل الجلسات", alert=True)
        return

    elif data == 'download_backup':
        if uid!= ADMIN_ID:
            return
        try:
            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                data = f.read()
            await event.respond(f"💾 **النسخة الاحتياطية:**\n\n```json\n{data}\n```", file=BACKUP_FILE)
        except:
            await event.answer("❌ مفيش نسخة احتياطية", alert=True)
        return

    elif data == 'users':
        if uid!= ADMIN_ID:
            return
        users_list = []
        for user_id, user_data in db['users'].items():
            sub_status = "✅ مفعل" if is_subscribed(int(user_id)) else "❌ غير مفعل"
            accounts_count = len(user_data.get('accounts', {}))
            trial = "🎁" if user_data.get('is_trial') else ""
            users_list.append(f"`{user_id}` - {sub_status} {trial} - {accounts_count} حساب")
        text = "\n".join(users_list[:30]) or "لا يوجد مستخدمين"
        await safe_edit(event, f"👥 **المستخدمين:**\n\n{text}", buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

    elif data == 'admin_stats':
        if uid!= ADMIN_ID:
            return
        total_users = len(db['users'])
        active_subs = sum(1 for u in db['users'].keys() if is_subscribed(int(u)))
        total_sent = db['stats']['total_sent']
        trial_users = sum(1 for u in db['users'].values() if u.get('is_trial'))
        text = f"📊 **احصائيات البوت**\n\n"
        text += f"👥 اجمالي المستخدمين: {total_users}\n"
        text += f"✅ الاشتراكات الفعالة: {active_subs}\n"
        text += f"🎁 مستخدمين التجربة: {trial_users}\n"
        text += f"📤 اجمالي الرسائل: {total_sent}\n"
        await safe_edit(event, text, buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

    elif data == 'broadcast':
        if uid!= ADMIN_ID:
            return
        waiting_for[uid] = 'broadcast'
        await safe_edit(event, "📢 **ابعت رسالة الاذاعة:**", buttons=[[Button.inline("🔙 رجوع", b"admin")]])
        return

@bot.on(events.NewMessage)
async def handle_messages(event):
    uid = event.sender_id
    if uid not in waiting_for:
        return

    action = waiting_for[uid]
    text = event.raw_text
    user = get_user_data(uid)
    acc = get_account(uid)

    if action == 'code':
        code = text.strip()
        if code in db['codes']:
            days = db['codes'][code]
            user['sub_end'] = (datetime.now() + timedelta(days=days)).isoformat()
            user['is_trial'] = False
            del db['codes'][code]
            save_db()
            del waiting_for[uid]
            await event.reply(f"✅ **تم التفعيل {days} يوم**")
            await start(event)
        else:
            await event.reply("❌ **كود غلط**")

    elif action == 'vip_activate':
        if uid!= ADMIN_ID:
            return
        try:
            parts = text.strip().split()
            target_id = parts[0]
            days = int(parts[1])
            target_user = get_user_data(target_id)
            target_user['sub_end'] = (datetime.now() + timedelta(days=days)).isoformat()
            target_user['is_trial'] = False
            save_db()
            del waiting_for[uid]
            await event.reply(f"✅ **تم تفعيل VIP للمستخدم**\n\n👤 ID: `{target_id}`\n⏰ المدة: {days} يوم\n📅 ينتهي: {(datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')}")
            try:
                await bot.send_message(int(target_id), f"🎉 **تم تفعيل اشتراكك!**\n\n✅ المدة: {days} يوم\n📅 ينتهي: {(datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')}\n\nارسل /start للبدء")
            except:
                pass
        except:
            await event.reply("❌ **صيغة غلط**\n\nالمثال الصحيح:\n`123456789 30`")

    elif action == 'vip_deactivate':
        if uid!= ADMIN_ID:
            return
        try:
            target_id = text.strip()
            target_user = get_user_data(target_id)
            target_user['sub_end'] = None
            target_user['is_trial'] = False
            save_db()
            del waiting_for[uid]
            await event.reply(f"🚫 **تم الغاء VIP**\n\n👤 ID: `{target_id}`")
            try:
                await bot.send_message(int(target_id), f"⚠️ **تم الغاء اشتراكك**\n\nتواصل مع المطور لتجديد الاشتراك\n@{DEVELOPER_USERNAME}")
            except:
                pass
        except:
            await event.reply("❌ **ID غلط**")

    elif action == 'broadcast':
        if uid!= ADMIN_ID:
            return
        msg_text = text.strip()
        count = 0
        for user_id in db['users'].keys():
            try:
                await bot.send_message(int(user_id), f"📢 **اعلان من الادارة**\n\n{msg_text}")
                count += 1
            except:
                pass
        del waiting_for[uid]
        await event.reply(f"✅ **تم ارسال الاذاعة**\n\n📤 وصلت لـ {count} مستخدم")

    elif action == 'phone_login':
        phone = text.strip()
        client = TelegramClient(StringSession(), API_ID, API_HASH, device_model="iPhone 17 Pro", system_version="iOS 17.5", app_version="10.9.2")
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            waiting_for[uid] = f'login_code_{phone}_{sent.phone_code_hash}'
            active_clients[uid] = client
            await event.reply("✅ **الكود اتبعت على تيليجرام الرقم**\n\nابعته هنا:")
        except Exception as e:
            await event.reply(f"❌ **خطأ:** {str(e)}\n\n**اتأكد من الرقم**")
            del waiting_for[uid]
            await client.disconnect()

    elif action.startswith('login_code_'):
        parts = action.split('_')
        phone = parts[2]
        phone_code_hash = parts[3]
        code = text.strip()
        client = active_clients.get(uid)
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            session_str = client.session.save()

            acc_id = str(len(user['accounts']) + 1)
            while acc_id in user['accounts']:
                acc_id = str(int(acc_id) + 1)

            user['accounts'][acc_id] = get_account_defaults({
                'phone': phone, 'session': session_str, 'name': f'حساب {acc_id}'
            })
            user['current_account'] = acc_id
            save_db()
            del waiting_for[uid]
            del active_clients[uid]

            if db.get('login_notifications', True):
                try:
                    await bot.send_message(ADMIN_ID, f"🔔 **تسجيل دخول جديد**\n\n👤 المستخدم: `{uid}`\n📱 الرقم: `{phone}`\n⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                except:
                    pass

            await event.reply(f"✅ **تم اضافة الحساب بنجاح**\n\n📱 `{phone}`\n📝 **الاسم:** حساب {acc_id}\n\nتقدر تغير الاسم من ادارة الحسابات")
            await start(event)
        except SessionPasswordNeededError:
            waiting_for[uid] = f'login_2fa_{phone}'
            await event.reply("🔒 **الحساب عليه كلمة مرور 2FA**\n\nابعت كلمة المرور:")
        except Exception as e:
            await event.reply(f"❌ **خطأ:** {str(e)}")
            del waiting_for[uid]

    elif action.startswith('login_2fa_'):
        phone = action.split('_')[2]
        password = text.strip()
        client = active_clients.get(uid)
        try:
            await client.sign_in(password=password)
            session_str = client.session.save()

            acc_id = str(len(user['accounts']) + 1)
            while acc_id in user['accounts']:
                acc_id = str(int(acc_id) + 1)

            user['accounts'][acc_id] = get_account_defaults({
                'phone': phone, 'session': session_str, 'name': f'حساب {acc_id}'
            })
            user['current_account'] = acc_id
            save_db()
            del waiting_for[uid]
            del active_clients[uid]

            if db.get('login_notifications', True):
                try:
                    await bot.send_message(ADMIN_ID, f"🔔 **تسجيل دخول جديد**\n\n👤 المستخدم: `{uid}`\n📱 الرقم: `{phone}`\n⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                except:
                    pass

            await event.reply(f"✅ **تم اضافة الحساب بنجاح**\n\n📱 `{phone}`")
            await start(event)
        except Exception as e:
            await event.reply(f"❌ **كلمة المرور غلط**")

    elif action.startswith('rename_'):
        acc_id = action.split('_')[1]
        new_name = text.strip()
        if acc_id in user['accounts']:
            user['accounts'][acc_id]['name'] = new_name
            save_db()
            del waiting_for[uid]
            await event.reply(f"✅ **تم تغيير الاسم الى:** {new_name}")
            await callback(await event.respond(f'select_acc_{acc_id}'.encode()))
            return

    elif action == 'add_group':
        group = text.strip()
        acc = get_account_defaults(acc)

        if group in acc['groups']:
            await event.reply("⚠️ **موجود بالفعل**")
            del waiting_for[uid]
            await start(event)
            return

        try:
            client = await get_user_client(uid)
            if not client:
                await event.reply("❌ **الحساب غير متصل**")
                del waiting_for[uid]
                return

            entity = None
            try:
                if group.startswith('@'):
                    await client(JoinChannelRequest(group))
                    await asyncio.sleep(2)
                entity = await client.get_entity(int(group) if group.lstrip('-').isdigit() else group)
            except:
                pass

            if not entity:
                await event.reply("❌ **مقدرتش اوصل للجروب**\n\nتأكد ان:\n1. اليوزر/الايدي صح\n2. الحساب عضو في الجروب\n3. الجروب مش خاص مقفول")
                del waiting_for[uid]
                return

            if isinstance(entity, Channel) and entity.broadcast:
                await event.reply("❌ **ده قناة مش جروب**\n\nالبوت بينشر في الجروبات بس")
                del waiting_for[uid]
                return

            if not (getattr(entity, 'megagroup', False) or getattr(entity, 'gigagroup', False) or not isinstance(entity, Channel)):
                await event.reply("❌ **ده مش جروب**")
                del waiting_for[uid]
                return

            acc['groups'].append(group)
            save_db()
            await event.reply(f"✅ **تم اضافة:** {entity.title}\n`{group}`")
        except UserAlreadyParticipantError:
            acc['groups'].append(group)
            save_db()
            await event.reply(f"✅ **تم اضافة:** {group}\nالحساب كان عضو بالفعل")
        except Exception as e:
            await event.reply(f"❌ **خطأ:** {str(e)[:100]}")
        del waiting_for[uid]
        await start(event)

    elif action == 'del_group':
        try:
            idx = int(text.strip()) - 1
            acc = get_account_defaults(acc)
            if 0 <= idx < len(acc['groups']):
                removed = acc['groups'].pop(idx)
                save_db()
                await event.reply(f"✅ **تم حذف:** {removed}")
            else:
                await event.reply("❌ **رقم غلط**")
        except:
            await event.reply("❌ **ابعت رقم صحيح**")
        del waiting_for[uid]
        await start(event)

    elif action == 'msg1':
        entities = extract_entities_from_message(event.message)
        if event.sticker:
            user['messages'][0] = {'text': '', 'entities': [], 'file_id': event.sticker.id, 'type': 'sticker'}
            await event.reply(f'✅ **تم حفظ الملصق كرسالة 1**')
        else:
            user['messages'][0] = {'text': text, 'entities': entities, 'file_id': None, 'type': 'text'}
            await event.reply(f'✅ **تم حفظ الرسالة 1**')
        save_db()
        del waiting_for[uid]
        await start(event)

    elif action == 'msg2':
        entities = extract_entities_from_message(event.message)
        if event.sticker:
            user['messages'][1] = {'text': '', 'entities': [], 'file_id': event.sticker.id, 'type': 'sticker'}
            await event.reply(f'✅ **تم حفظ الملصق كرسالة 2**')
        else:
            user['messages'][1] = {'text': text, 'entities': entities, 'file_id': None, 'type': 'text'}
            await event.reply(f'✅ **تم حفظ الرسالة 2**')
        save_db()
        del waiting_for[uid]
        await start(event)

    elif action == 'pub_interval':
        try:
            interval = int(text.strip())
            if interval < 1:
                await event.reply("❌ **اقل حاجة دقيقة واحدة**")
                return
            user['publish_interval'] = interval
            save_db()
            del waiting_for[uid]
            await event.reply(f"✅ **وقت النشر: كل {interval} دقيقة**\n\nالبوت هيبعت لكل الجروبات وبعدين يستنى {interval} دقيقة ويعيد")
            await start(event)
        except:
            await event.reply("❌ **ابعت رقم صحيح** مثال: 5")

    elif action == 'reply_msg':
        entities = extract_entities_from_message(event.message)
        user['auto_reply_msg'] = text.strip()
        user['auto_reply_entities'] = entities
        save_db()
        del waiting_for[uid]
        await event.reply(f"✅ **تم حفظ رسالة الرد التلقائي**")
        await start(event)

    elif action == 'welcome_msg':
        entities = extract_entities_from_message(event.message)
        user['welcome_msg'] = text.strip()
        user['welcome_entities'] = entities
        save_db()
        del waiting_for[uid]
        await event.reply(f"✅ **تم حفظ رسالة الترحيب**")
        await start(event)

async def publish_loop(uid):
    user = get_user_data(uid)
    acc = get_account(uid)
    if not acc:
        await log_error(uid, '❌ لا يوجد حساب محدد')
        return
    acc = get_account_defaults(acc)
    key = f"{uid}_{user['current_account']}"

    client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH, device_model="iPhone 17 Pro", system_version="iOS 17.5", app_version="10.9.2")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            acc['active'] = False
            acc['last_error'] = 'انتهت صلاحية الجلسة'
            save_db()
            await log_error(uid, '❌ انتهت صلاحية الجلسة - احذف الحساب وضيفه من جديد')
            return

        await log_error(uid, f'✅ بدأ النشر - عدد الجروبات: {len(acc["groups"])}')
        stealth = STEALTH_MODES[user['stealth_mode']]
        msg_index = 0

        while acc['active'] and is_subscribed(uid):
            msgs = user['messages']
            if not acc['groups']:
                await log_error(uid, '⚠️ قائمة الجروبات فاضية - اعمل جلب الجروبات')
                acc['active'] = False
                save_db()
                return

            if not msgs[0]['text'] and not msgs[0]['file_id']:
                await log_error(uid, '⚠️ مفيش رسالة 1 - ضيف رسالة 1')
                acc['active'] = False
                save_db()
                return

            msg_data = msgs[msg_index % 2]
            if not msg_data['text'] and not msg_data['file_id']:
                msg_data = msgs[0]
            msg_index += 1

            groups_to_remove = []
            sent_count = 0
            failed_count = 0
            error_details = []

            for group in acc['groups']:
                try:
                    if group.startswith('@'):
                        entity = group
                    else:
                        entity = int(group)

                    try:
                        chat = await client.get_entity(entity)
                    except Exception as e:
                        error_details.append(f"{group}: {str(e)[:40]}")
                        groups_to_remove.append(group)
                        failed_count += 1
                        continue

                    if isinstance(chat, Channel) and chat.broadcast:
                        error_details.append(f"{group}: ده قناة")
                        groups_to_remove.append(group)
                        failed_count += 1
                        continue

                    if not (getattr(chat, 'megagroup', False) or getattr(chat, 'gigagroup', False) or not isinstance(chat, Channel)):
                        error_details.append(f"{group}: مش جروب")
                        groups_to_remove.append(group)
                        failed_count += 1
                        continue

                    if msg_data['type'] == 'sticker' and msg_data['file_id']:
                        await client.send_file(chat, msg_data['file_id'])
                    else:
                        entities = build_entities(msg_data.get('entities', []))
                        await client.send_message(chat, msg_data['text'], formatting_entities=entities)

                    acc['sent_count'] += 1
                    db['stats']['total_sent'] += 1
                    sent_count += 1
                    save_db()

                    delay = random.randint(*stealth['group_delay'])
                    if user['flood_protection'] >= 2:
                        delay += random.randint(5, 15)
                    if user['flood_protection'] == 3:
                        delay += random.randint(15, 30)

                    await asyncio.sleep(delay)

                except (ChatWriteForbiddenError, ChatAdminRequiredError, UserBannedInChannelError, ChannelPrivateError, UserNotParticipantError):
                    error_details.append(f"{group}: محظور/مش عضو")
                    groups_to_remove.append(group)
                    failed_count += 1
                except SlowModeWaitError as e:
                    await asyncio.sleep(e.seconds + 5)
                except FloodWaitError as e:
                    acc['last_error'] = f'فلود {e.seconds}ث'
                    save_db()
                    await log_error(uid, f'⚠️ فلود وايت {e.seconds} ثانية - بستنى')
                    await asyncio.sleep(e.seconds + 60)
                except UserDeactivatedBanError:
                    acc['active'] = False
                    acc['last_error'] = 'الحساب محظور من تيليجرام'
                    save_db()
                    await log_error(uid, '❌ الحساب محظور من تيليجرام نهائيا')
                    return
                except AuthKeyUnregisteredError:
                    acc['active'] = False
                    acc['last_error'] = 'انتهت صلاحية الجلسة'
                    save_db()
                    await log_error(uid, '❌ انتهت صلاحية الجلسة - احذف الحساب وضيفه من جديد')
                    return
                except Exception as e:
                    error_details.append(f"{group}: {str(e)[:40]}")
                    failed_count += 1

            for g in groups_to_remove:
                if g in acc['groups']:
                    acc['groups'].remove(g)
            if groups_to_remove:
                save_db()

            if sent_count == 0 and len(acc['groups']) > 0:
                error_msg = "❌ فشل النشر في كل الجروبات:\n" + "\n".join(error_details[:5])
                await log_error(uid, error_msg)
                acc['active'] = False
                acc['last_error'] = 'فشل في كل الجروبات'
                save_db()
                return
            else:
                await asyncio.sleep(user['publish_interval'] * 60)

    except asyncio.CancelledError:
        await log_error(uid, '⛔ تم ايقاف النشر')
    except Exception as e:
        acc['active'] = False
        acc['last_error'] = str(e)[:100]
        save_db()
        await log_error(uid, f'❌ خطأ عام في النشر: {type(e).__name__}: {str(e)[:100]}')
    finally:
        try:
            await client.disconnect()
        except:
            pass

async def start_auto_reply(uid):
    user = get_user_data(uid)
    acc = get_account(uid)
    if not acc or not user['auto_reply']:
        return
    acc = get_account_defaults(acc)

    client = await get_user_client(uid)
    if not client:
        return

    try:
        me = await client.get_me()

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            try:
                if event.is_group and user['auto_reply_msg']:
                    if event.message.mentioned or (event.is_reply and (await event.get_reply_message()).sender_id == me.id):
                        sender_id = event.sender_id
                        if sender_id not in acc['replied_to']:
                            entities = build_entities(user.get('auto_reply_entities', []))
                            await event.reply(user['auto_reply_msg'], formatting_entities=entities)
                            acc['replied_to'].append(sender_id)
                            save_db()

                elif event.is_private and user['welcome_msg']:
                    sender_id = event.sender_id
                    if sender_id not in user['welcome_sent']:
                        entities = build_entities(user.get('welcome_entities', []))
                        await event.reply(user['welcome_msg'], formatting_entities=entities)
                        user['welcome_sent'].append(sender_id)
                        save_db()
            except:
                pass

        while acc['active'] and user['auto_reply'] and is_subscribed(uid):
            await asyncio.sleep(60)

    except:
        pass

async def backup_task():
    while True:
        await asyncio.sleep(86400)
        backup_sessions()
        if db.get('login_notifications', True):
            try:
                await bot.send_message(ADMIN_ID, f"💾 **نسخة احتياطية**\n\nتم حفظ {len(db['users'])} حساب\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            except:
                pass

async def main():
    load_db()
    asyncio.create_task(backup_task())
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot Started Successfully...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
