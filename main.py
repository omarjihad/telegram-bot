import os, sqlite3, asyncio, logging
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, MessageNotModifiedError, FloodWaitError
from telethon.tl.functions.channels import GetParticipantRequest
from aiohttp import web

# --- ⚙️ إعدادات البوت ---
API_ID = 35717556
API_HASH = '0adf0db68ac4a48af97930e557a8d20b'
BOT_TOKEN = '8534245617:AAENxrNSpCGjdCdiAUriE_fOQwcP3peUzg4'

# --- 🔗 معلومات المطور ---
DEV_USER = "serxoin"
SUPPORT_URL = "https://t.me/asazt1"

# --- 🖼️ روابط الصور (ضفت خدعة صغيرة بنهاية الرابط عشان تنقبل كصورة) ---
# ضفنا &.jpg بالنهاية عشان البوت يفهم انها صورة
START_IMG = "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=2070&auto=format&fit=crop&.jpg" 
LOGIN_IMG = "https://images.unsplash.com/photo-1563986768609-322da13575f3?q=80&w=1470&auto=format&fit=crop&.jpg"   
DASHBOARD_IMG = "https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop&.jpg" 

# إعداد اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.path.exists('sessions'): os.makedirs('sessions')

# --- 🗄️ المتغيرات ---
active_sessions = {}
verified_users = {}
warning_cache = {}

# --- 🌐 سيرفر الهوست ---
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is Running Successfully!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# --- 🗃️ قاعدة البيانات ---
def db_query(sql, params=(), fetch=False):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        data = cursor.fetchall() if fetch else None
        conn.commit()
        return data
    except Exception as e:
        return []
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect('bot_database.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS accounts (
                user_id INTEGER, phone TEXT, name TEXT, channel TEXT, 
                custom_msg TEXT DEFAULT 'عذراً، الخاص مغلق للمشتركين فقط.',
                is_active INTEGER DEFAULT 0, PRIMARY KEY(user_id, phone))''')
    conn.commit()
    conn.close()

init_db()

# --- 🤖 تشغيل البوت ---
try:
    bot = TelegramClient('main_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
except Exception as e:
    print(f"❌ خطأ التشغيل: {e}")
    exit()

# --- 🛠️ دالة مساعدة لإرسال الصور (الحل هنا) ---
async def send_safe(chat_id, text, img_url, buttons=None):
    try:
        # force_document=False: هذا الامر يخليها غصبا عليها تصير صورة مو ملف
        await bot.send_message(chat_id, text, file=img_url, buttons=buttons, force_document=False)
    except Exception as e:
        # اذا فشلت الصورة، نرسل نص فقط
        await bot.send_message(chat_id, text, buttons=buttons)

# --- 🛡️ نظام الحماية ---
async def start_protection(phone, channel, custom_msg):
    try:
        session_file = phone.replace("+", "")
        client = TelegramClient(f"sessions/{session_file}", API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            return False

        active_sessions[phone] = client 
        clean_ch = channel.replace("https://t.me/", "").replace("@", "").strip()
        full_warning = f"{custom_msg}\n\n📢 **عليك الاشتراك في القناة لمراسلتي:**\n@{clean_ch}"

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def handler(event):
            sender = await event.get_sender()
            if not sender or sender.bot or sender.is_self: return
            user_key = f"{phone}_{sender.id}"
            if user_key in verified_users: return

            try:
                try:
                    await bot(GetParticipantRequest(channel=clean_ch, participant=sender.id))
                    if user_key not in verified_users:
                        if user_key in warning_cache:
                            try: await client.delete_messages(event.chat_id, warning_cache[user_key])
                            except: pass
                            del warning_cache[user_key]
                        await client.send_message(event.chat_id, "✅ **نورت، هسة تكدر تراسلني.**")
                        verified_users[user_key] = True
                except:
                    try: await event.delete()
                    except: pass
                    if user_key in warning_cache: return 
                    sent = await client.send_message(event.chat_id, full_warning)
                    warning_cache[user_key] = sent.id
            except: pass
        return True
    except Exception as e:
        logger.error(f"Connection Error ({phone}): {e}")
        return False

async def stop_protection(phone):
    if phone in active_sessions:
        await active_sessions[phone].disconnect()
        del active_sessions[phone]
        keys_to_del = [k for k in warning_cache if k.startswith(f"{phone}_")]
        for k in keys_to_del: del warning_cache[k]

# --- 📱 الواجهة ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    btns = [
        [Button.inline("➕ ضيف حساب", b"login")],
        [Button.inline("🗂 حساباتك", b"manage")],
        [Button.url("المطور", f"https://t.me/{DEV_USER}"), Button.url("كروب البوت", SUPPORT_URL)]
    ]
    # استخدام الدالة الآمنة
    await send_safe(
        event.chat_id,
        "**هلا والله 👋**\n\nهذا البوت يخليك تقفل الخاص مالتك 🔒\nيعني محد يكدر يراسلك الا يشترك بقناتك.\n\nدوس الازرار جوة ورتب وضعك 👇",
        START_IMG,
        btns
    )

# --- 🔑 تسجيل الدخول ---
@bot.on(events.CallbackQuery(data=b"login"))
async def login(event):
    await event.delete()
    async with bot.conversation(event.sender_id, timeout=300) as conv:
        try:
            # محاولة ارسال الصورة بأمان داخل المحادثة
            try:
                # force_document=False ضروري هنا
                await conv.send_message(
                    "دز رقمك مع مفتاح الدولة (+) \nمثال: `+9647700000000`",
                    file=LOGIN_IMG,
                    buttons=Button.clear(),
                    force_document=False
                )
            except:
                await conv.send_message(
                    "دز رقمك مع مفتاح الدولة (+) \nمثال: `+9647700000000`",
                    buttons=Button.clear()
                )

            phone_resp = await conv.get_response()
            phone = phone_resp.text.replace(" ", "").strip()
            
            session_file = phone.replace("+", "")
            client = TelegramClient(f"sessions/{session_file}", API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                try:
                    await client.send_code_request(phone, force_sms=False)
                except FloodWaitError as e:
                    await conv.send_message(f"❌ **محاولات هواي!** انتظر {e.seconds} ثانية.")
                    return
                except Exception as e:
                    await conv.send_message(f"❌ **تأكد من صحة الرقم:** {e}")
                    return

                await conv.send_message("📩 **وصلك كود ع التليكرام!**\n\nاكتب الكود **مع مسافات** بين الأرقام لضمان الوصول:\nمثال: `1 2 3 4 5`")
                code_resp = await conv.get_response()
                code = code_resp.text.replace(" ", "").strip()
                
                try: 
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    await conv.send_message("🔒 **حسابك مقفول بكلمة سر (2FA)، دزها:**")
                    pw_resp = await conv.get_response()
                    password = pw_resp.text
                    try:
                        await client.sign_in(password=password)
                    except:
                        await conv.send_message("❌ **الباسورد غلط!**")
                        return
                except Exception as e:
                    await conv.send_message(f"❌ **الكود غلط او منتهي:** {e}")
                    return
            
            me = await client.get_me()
            name = me.first_name if me.first_name else phone
            db_query("INSERT OR REPLACE INTO accounts (user_id, phone, name) VALUES (?, ?, ?)", (event.sender_id, phone, name))
            await conv.send_message("✅ **تم، الحساب انحفظ.**", buttons=[Button.inline("رجوع للقائمة", b"manage")])
            await client.disconnect()
            
        except asyncio.TimeoutError:
            await conv.send_message("⏱ **تأخرت بالرد، عيد العملية.**")
        except Exception as e:
            await conv.send_message(f"❌ **صار خطأ:** {e}")
            if client.is_connected(): await client.disconnect()

# --- 🔄 تحديث القائمة ---
async def refresh_menu(event, phone):
    res = db_query("SELECT name, channel, is_active FROM accounts WHERE phone=?", (phone,), fetch=True)
    if not res: return await event.edit("الحساب ممسوح.", buttons=[Button.inline("رجوع", b"manage")])
    name, ch, db_active = res[0]
    is_running = phone in active_sessions
    status = "🟢 شغال" if is_running else "🔴 طافي"
    btn_action = "🛑 طفي البوت" if is_running else "▶️ شغل البوت"
    ch_txt = ch if ch else "⚠️ ماكو"
    btns = [
        [Button.inline(f"القناة: {ch_txt}", f"ch:{phone}".encode())],
        [Button.inline("رسالة التحذير", f"msg:{phone}".encode())],
        [Button.inline(btn_action, f"tog:{phone}".encode())],
        [Button.inline("حذف الحساب", f"del:{phone}".encode())],
        [Button.inline("رجوع", b"manage")]
    ]
    txt = f"👤 **الحساب:** {name}\n📞 **الرقم:** `{phone}`\n🔋 **الوضع:** {status}"
    
    await event.delete()
    await send_safe(event.chat_id, txt, DASHBOARD_IMG, btns)

@bot.on(events.CallbackQuery(pattern=b"(manage|acc:|tog:|del:|ch:|msg:|back)"))
async def callback_handler(event):
    data = event.data.decode()
    if data == "manage":
        accs = db_query("SELECT name, phone FROM accounts WHERE user_id=?", (event.sender_id,), fetch=True)
        btns = []
        if accs:
            for a in accs:
                btns.append([Button.inline(f"👤 {a[0]}", f"acc:{a[1]}".encode())])
        btns.append([Button.inline("➕ حساب جديد", b"login")])
        btns.append([Button.inline("رجوع", b"back")])
        
        await event.delete()
        await bot.send_message(event.chat_id, "**اختار الحساب الي تريد تضبطه:**", buttons=btns)

    elif data.startswith("acc:"):
        phone = data.split(":")[1]
        await refresh_menu(event, phone)
    elif data.startswith("tog:"):
        phone = data.split(":")[1]
        res = db_query("SELECT channel, custom_msg FROM accounts WHERE phone=?", (phone,), fetch=True)
        if not res: return
        ch, msg = res[0]
        if phone in active_sessions:
            await event.answer("⏳ جاري الايقاف...")
            await stop_protection(phone)
            await asyncio.sleep(0.5)
            await refresh_menu(event, phone)
        else:
            if not ch: return await event.answer("⚠️ لازم تحط قناة بالاول!", alert=True)
            await event.answer("⏳ جاري التشغيل...")
            success = await start_protection(phone, ch, msg)
            if success:
                client = active_sessions[phone]
                asyncio.create_task(client.run_until_disconnected())
                await asyncio.sleep(1) 
                await refresh_menu(event, phone)
            else:
                await event.answer(f"❌ فشل الاتصال بالحساب.", alert=True)
    elif data.startswith("del:"):
        phone = data.split(":")[1]
        await stop_protection(phone)
        db_query("DELETE FROM accounts WHERE phone=?", (phone,))
        try: os.remove(f"sessions/{phone.replace('+', '')}.session")
        except: pass
        await event.answer("تم الحذف", alert=True)
        await callback_handler(events.CallbackQuery.Event(original_update=None, data=b"manage", sender_id=event.sender_id, chat_id=event.chat_id))
    elif data.startswith("ch:"):
        phone = data.split(":")[1]
        await event.delete()
        async with bot.conversation(event.sender_id) as conv:
            await conv.send_message("1️⃣ دز يوزر القناة (مثلا: `@AbnBasha`).\n⚠ **ارفعني (البوت) مشرف بالقناة اول شي!**")
            try:
                ch = (await conv.get_response()).text.strip()
                db_query("UPDATE accounts SET channel=? WHERE phone=?", (ch, phone))
                await conv.send_message("✅ **حلو، انحفظت.**")
                if phone in active_sessions:
                    await stop_protection(phone)
                    res = db_query("SELECT custom_msg FROM accounts WHERE phone=?", (phone,), fetch=True)
                    await start_protection(phone, ch, res[0][0])
                    client = active_sessions[phone]
                    asyncio.create_task(client.run_until_disconnected())
            except: pass
            await conv.send_message("راجعين...", buttons=Button.inline("عودة", f"acc:{phone}".encode()))
    elif data.startswith("msg:"):
        phone = data.split(":")[1]
        await event.delete()
        async with bot.conversation(event.sender_id) as conv:
            await conv.send_message("📝 **دز الرسالة الي تطلع للي مامشترك:**")
            msg = (await conv.get_response()).text
            db_query("UPDATE accounts SET custom_msg=? WHERE phone=?", (msg, phone))
            await conv.send_message("✅ **تم الحفظ.**")
            await conv.send_message("راجعين...", buttons=Button.inline("عودة", f"acc:{phone}".encode()))
    elif data == "back":
        await start(event)

print("✅ البوت شغال وجاهز...")
loop = asyncio.get_event_loop()
loop.create_task(web_server())
bot.run_until_disconnected()
