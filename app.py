import os
import time
import aiohttp
import logging
import threading
import asyncio
import re
import html 
import json
import websockets
from datetime import datetime
from flask import Flask
from urllib.parse import unquote

# مكاتب تيليجرام الأساسية للبوت
from telegram import Update
from telegram.ext import Application, MessageHandler, ConversationHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ChatMemberHandler
from telegram.request import HTTPXRequest

# مكاتب Telethon لـ MRKT
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName
from curl_cffi.requests import AsyncSession

# إخفاء اللوجات المزعجة وتحذيرات PTB
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.ERROR) 
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.ERROR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

TOKEN = "8679057078:AAE-k1jPdS77wPbDsz43aMlKeZqYZynipt8"
ADMIN_IDS = [7126816492, 1955081272]
DB_FILE = "tonnel_db.json"

# ==========================================
# إعدادات جلسة Telethon لـ MRKT
# ==========================================
TELE_API_ID = int(os.environ.get("TELE_API_ID", 12345678)) 
TELE_API_HASH = os.environ.get("TELE_API_HASH", "PUT_YOUR_API_HASH_HERE")

# سحب الجلسة من السيكرت (يدعم Session File و String Session)
RAW_SESSION = os.environ.get("SESSION_NAME", "mrkt_session")
if len(RAW_SESSION) > 50:
    SESSION_DATA = StringSession(RAW_SESSION)
else:
    SESSION_DATA = RAW_SESSION

tele_client = None

# نظام الكاش والبيانات
CACHE_TIME = 2
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000
crypto_prices = {'BTC': 0, 'GRAM': 0, 'BATH': 0.03} 
crypto_24h_trend = {'BTC': 0.0, 'GRAM': 0.0, 'BATH': 0.0} 
daily_iqd = {'date': '', 'open_price': 0} 

alerts_db = []
user_wallets = {} 
bot_users = set() 
whale_alert_users = {} 
banned_users = set() 
user_mapping = {} 

# حالات المحادثة
ASK_CURRENCY, ASK_PRICE = range(2)
ASK_WALLET = 3 
ASK_MARKET_CHOICE = 4
ASK_GIFT_SEARCH_TONNEL = 5
ASK_GIFT_SEARCH_MRKT = 6
ASK_BAN = 7
ASK_UNBAN = 8

# --- متغيرات السوق وقاعدة البيانات لـ Tonnel ---
WS_URL = 'wss://gifts.coffin.meme/api/marketplace/ws'
active_listings = {}
last_event_id = ""
seen_events = set()
needs_db_save = False

gift_floor = {
    "price": "0", 
    "url_tonnel": "https://t.me/tonnel_network_bot", 
    "url_telegram": "https://t.me/nft",
    "name": "جاري التحديث..."
}

# --- متغيرات السوق لـ MRKT ---
mrkt_token = None
mrkt_floor = {
    "price": "0", 
    "url_mrkt": "https://t.me/mrkt", 
    "url_telegram": "https://t.me/nft",
    "name": "جاري التحديث..."
}

# --- الملصقات المميزة ---
GIFT_FLOOR_EMOJI = '<tg-emoji emoji-id="5255980157058975232">🎁</tg-emoji>'
MRKT_TEXT_EMOJI = '<tg-emoji emoji-id="6041916763719866213">🛒</tg-emoji>'
MRKT_ICON_ID = "6041916763719866213"
TONNEL_ICON_ID = "5210956306952758910"

UP_EMOJI = '<tg-emoji emoji-id="5449683594425410231">📈</tg-emoji>'
DOWN_EMOJI = '<tg-emoji emoji-id="5447183459602669338">📉</tg-emoji>'
WHALE_BELL = '<tg-emoji emoji-id="5215372534060428125">🔔</tg-emoji>'
WHALE_EMOJI = '<tg-emoji emoji-id="5461151367559141950">🐋</tg-emoji>'
ASIA_EMOJI = '<tg-emoji emoji-id="5183779703818814840">🔴</tg-emoji>'
MASTER_EMOJI = '<tg-emoji emoji-id="5812036009365343919">💳</tg-emoji>'
GRAM_EMOJI = '<tg-emoji emoji-id="5300919220215780911">💎</tg-emoji>' 
BATH_EMOJI = '<tg-emoji emoji-id="5330015905659264283">🛁</tg-emoji>' 
FOOL_EMOJI = '<tg-emoji emoji-id="5841545015964209734">😂</tg-emoji>' 
CLIPBOARD_EMOJI = '<tg-emoji emoji-id="5800769433974611462">📋</tg-emoji>'
END_EMOJIS = '<tg-emoji emoji-id="5210956306952758910">✔️</tg-emoji> <tg-emoji emoji-id="5958605483488055761">✅</tg-emoji>'
WARN_EMOJI = '<tg-emoji emoji-id="5213195952008997792">⚠️</tg-emoji>'
CROWN_EMOJI = '<tg-emoji emoji-id="6048861163196783957">👑</tg-emoji>'
PLANE_EMOJI = '<tg-emoji emoji-id="5319250406923051255">✈️</tg-emoji>'
SEARCH_EMOJI = '<tg-emoji emoji-id="5411597774359653692">🔍</tg-emoji>'
WAIT_EMOJI = '<tg-emoji emoji-id="5215484787325676090">⏳</tg-emoji>'
SUCCESS_EMOJI = '<tg-emoji emoji-id="5215492745900077682">✅</tg-emoji>'
FAIL_EMOJI = '<tg-emoji emoji-id="5215204871422093648">❌</tg-emoji>'
USDT_CASH = '<tg-emoji emoji-id="5213170203680060059">💵</tg-emoji>'
HELLO_EMOJI = '<tg-emoji emoji-id="5800769433974611462">👋</tg-emoji>'
NUM_EMOJIS = {1: '1️⃣', 2: '2️⃣', 3: '3️⃣', 4: '4️⃣', 5: '5️⃣', 6: '6️⃣'}

CANCEL_BTN = [{"text": "الغاء", "callback_data": "cancel", "style": "primary", "icon_custom_emoji_id": "5440681540541502133"}]

# قواميس بحث MRKT
ALIASES = {
    "durov": "Durov’s Figurine", "pavel": "Durov’s Figurine", "pepe": "Plush Pepe",
    "cap": "Durov’s Cap", "boots": "Durov’s Boots", "coat": "Durov’s Coat",
    "glasses": "Durov’s Glasses", "liberty": "Liberty Figure", "ufc": "UFC Strike",
    "star": "Star", "box": "Box", "gift": "Gift", "heart": "Heart", "rose": "Rose"
}
KNOWN_GIFTS = [
    "Durov’s Cap", "Durov’s Boots", "Durov’s Coat", "Durov’s Figurine", "Durov’s Glasses", 
    "Khabib’s Papakha", "Snoop Dogg", "Snoop Cigar", "Plush Pepe", "Lol Pop", "Fine Pen", 
    "Bunny Muffin", "Jelly Star", "Lunar Snake", "Mr. Duck", "Mr. Deer", "Mr. Bear", 
    "Spicy Sausage", "Jedi Donut", "Anonymous", "Whale", "Pigeon", "Star", "Telegram Premium", 
    "Gift", "Box", "Heart", "Rose", "Cake", "Diamond", "Vintage Cigar", "Magic Potion",
    "Airplane", "Artisan Brick", "Astral Shard", "B-Day Candle", "Berry Box", "Big Year", 
    "Bling Binky", "Bonded Ring", "Bow Tie", "Candy Cane", "Chill Flame", "Clover Pin", 
    "Coffin", "Cookie Heart", "Crystal Ball", "Cupid Charm", "Desk Calendar", "Diamond Ring", 
    "Easter Egg", "Electric Skull", "Eternal Candle", "Eternal Rose", "Evil Eye", "Faith Amulet", 
    "Flying Broom", "Fresh Socks", "Gem Signet", "Genie Lamp", "Ginger Cookie", "Gravestone", 
    "Hanging Star", "Happy Brownie", "Heart Locket", "Heroic Helmet", "Hex Pot", "Holiday Drink", 
    "Homemade Cake", "Hypno Lollipop", "Ice Cream", "Input Key", "Instant Ramen", "Ion Gem", 
    "Ionic Dryer", "Jack-In-the-Box", "Jelly Bunny", "Jester Hat", "Jingle Bells", "Jolly Chimp", 
    "Joyful Bundle", "Kissed Frog", "Liberty Figure", "Light Sword", "Loot Bag", "Love Candle", 
    "Love Potion", "Low Rider", "Lush Bouquet", "Mad Pumpkin", "Mask", "Mighty Arm", "Mini Oscar", 
    "Money Pot", "Mood Pack", "Moon Pendant", "Mousse Cake", "Nail Bracelet", "Neko Helmet", 
    "Party Sparkler", "Perfume Bottle", "Pet Snake", "Pool Float", "Precious Peach", "Pretty Posy",
    "Rare Bird", "Record Player", "Restless Jar", "Sakura Flower", "Santa Hat", "Scared Cat", 
    "Sharp Tongue", "Signet Ring", "Skull Flower", "Sky Stilettos", "Sleigh Bell", "Snake Box", 
    "Snow Globe", "Snow Mittens", "Spiced Wine", "Spring Basket", "Spy Agaric", "Star Notepad", 
    "Stellar Rocket", "Surge Board", "Swag Bag", "Swiss Watch", "Tama Gadget", "Timeless Book", 
    "Top Hat", "Toy Bear", "Trapped Heart", "Trojan Horse", "UFC box", "UFC Strike", "Valentine Box", 
    "Vice Cream", "Victory Medal", "Voodoo Doll", "Westside Sign", "Whip Cupcake", "Winter Wreath", 
    "Witch Hat", "Xmas Stocking"
]

def format_exact_price(price):
    if price == int(price): return str(int(price))
    return f"{price:.6f}".rstrip('0').rstrip('.')

# ==========================================
# MRKT API Functions (بالاعتماد على Telethon)
# ==========================================
async def get_mrkt_auth_token():
    global tele_client
    try:
        if tele_client is None:
            tele_client = TelegramClient(SESSION_DATA, TELE_API_ID, TELE_API_HASH)
            
        if not tele_client.is_connected():
            print("🔄 [MRKT] جاري الاتصال بحساب تيليجرام...")
            await tele_client.connect()
            
        # فحص تسجيل الدخول (لمنع تعليق البوت إذا كانت الجلسة خطأ)
        if not await tele_client.is_user_authorized():
            print("⚠️ [MRKT] خطأ: الجلسة غير مسجلة دخول! تأكد من ملف الجلسة أو السيكرت.")
            return None

        print("✅ [MRKT] الحساب متصل. جاري جلب بيانات WebView...")
        bot_entity = await tele_client.get_entity('mrkt')
        input_bot = await tele_client.get_input_entity(bot_entity)
        bot_app = InputBotAppShortName(bot_id=input_bot, short_name="app")

        web_view = await tele_client(
            RequestAppWebViewRequest(
                peer=input_bot,
                app=bot_app,
                platform="android",
                write_allowed=True,
                start_param=""
            )
        )

        url = web_view.url
        init_data = url.split("tgWebAppData=", 1)[1].split("&tgWebAppVersion", 1)[0]
        init_data = unquote(init_data)

        print("🔄 [MRKT] تم استخراج init_data. جاري جلب التوكن من السيرفر...")
        async with AsyncSession(impersonate="chrome") as s:
            r = await s.post(
                "https://api.tgmrkt.io/api/v1/auth", 
                json={"data": init_data},
                headers={"Referer": "https://cdn.tgmrkt.io/", "Origin": "https://cdn.tgmrkt.io", "Accept": "application/json"}
            )
            if r.status_code == 200:
                token = r.json().get('token')
                if token:
                    print("🎉 [MRKT] تم الحصول على التوكن بنجاح!")
                    return token
            else:
                print(f"⚠️ [MRKT] فشل جلب التوكن، كود الخطأ: {r.status_code}")
                
    except Exception as e:
        print(f"⚠️ [MRKT] حدث خطأ عام: {e}")
    return None

async def mrkt_updater_loop():
    global mrkt_token, mrkt_floor
    while True:
        try:
            if not mrkt_token:
                mrkt_token = await get_mrkt_auth_token()
            
            if mrkt_token:
                headers = {'Authorization': str(mrkt_token), 'Referer': 'https://cdn.tgmrkt.io/'}
                json_data = {
                    "collectionNames": [], "modelNames": [], "backdropNames": [], "symbolNames": [],
                    "ordering": "Price", "lowToHigh": True, "count": 1, "cursor": '', "promotedFirst": False
                }
                async with AsyncSession(impersonate="chrome") as s:
                    r = await s.post('https://api.tgmrkt.io/api/v1/gifts/saling', headers=headers, json=json_data)
                    if r.status_code == 401:
                        print("⚠️ [MRKT] التوكن انتهت صلاحيته، سيتم التجديد...")
                        mrkt_token = None 
                        continue
                    
                    if r.status_code == 200:
                        rj = r.json()
                        gifts = rj.get('gifts', [])
                        if gifts:
                            cheapest = gifts[0]
                            price = None
                            for key in ["salePrice", "salePriceWithoutFee", "floorPriceNanoTONsByCollection"]:
                                val = cheapest.get(key)
                                if isinstance(val, (int, float)) and val > 0:
                                    price = int(val)
                                    break
                            
                            if price:
                                ton_price = price / 1_000_000_000
                                mrkt_floor['price'] = format_exact_price(ton_price)
                                mrkt_floor['name'] = cheapest.get("title") or cheapest.get("collectionTitle") or cheapest.get("collectionName") or "Unknown"
                                
                                gift_id = cheapest.get("id")
                                mrkt_floor['url_mrkt'] = f"https://t.me/mrkt/app?startapp={gift_id}"
                                clean_url_name = mrkt_floor['name'].lower().replace(' ', '')
                                mrkt_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}"
        except Exception:
            pass
        await asyncio.sleep(15) 

# ==========================================
# دالة إرسال الرسائل وتعديلها
# ==========================================
async def send_custom_msg(chat_id, text, reply_to_message_id=None, extra_buttons=None, skip_news=False):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    inline_keyboard = []
    if extra_buttons: 
        for btn_group in extra_buttons:
            if isinstance(btn_group, list): inline_keyboard.append(btn_group)
            else: inline_keyboard.append([btn_group])
            
    if not skip_news:
        inline_keyboard.append([{"text": "اخبار الهدايا", "url": "https://t.me/Guidance_nft", "style": "danger", "icon_custom_emoji_id": "5224257782013769471"}])
        
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}, "disable_web_page_preview": True}
    if reply_to_message_id: payload["reply_parameters"] = {"message_id": reply_to_message_id}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", {}).get("message_id")
        except Exception: pass
    return None

async def edit_custom_msg(chat_id, message_id, text, extra_buttons=None, skip_news=False):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    inline_keyboard = []
    if extra_buttons:
        for btn_group in extra_buttons:
            if isinstance(btn_group, list): inline_keyboard.append(btn_group)
            else: inline_keyboard.append([btn_group])
            
    if not skip_news:
        inline_keyboard.append([{"text": "اخبار الهدايا", "url": "https://t.me/Guidance_nft", "style": "danger", "icon_custom_emoji_id": "5224257782013769471"}])
        
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}, "disable_web_page_preview": True}
    async with aiohttp.ClientSession() as session:
        try: await session.post(url, json=payload, timeout=10)
        except Exception: pass

# ==========================================
# إدارة قاعدة بيانات Tonnel
# ==========================================
def load_market_db():
    global active_listings, last_event_id
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                active_listings = data.get('listings', {})
                last_event_id = data.get('last_event_id', "")
        except:
            active_listings = {}
            last_event_id = ""

def save_market_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_event_id': last_event_id, 'listings': active_listings}, f)
    except: pass

async def floor_updater_loop():
    global needs_db_save, gift_floor, active_listings
    while True:
        await asyncio.sleep(3) 
        if needs_db_save:
            needs_db_save = False
            if active_listings:
                try:
                    valid_listings = {k: v for k, v in active_listings.items() if float(v.get('price', 0)) > 0}
                    if valid_listings:
                        lowest_gift_id = min(valid_listings, key=lambda k: float(valid_listings[k]['price']))
                        lowest_data = valid_listings[lowest_gift_id]
                        
                        gift_floor['price'] = format_exact_price(float(lowest_data['price']))
                        gift_floor['name'] = lowest_data['name']
                        
                        clean_url_name = lowest_data['name'].lower().replace(' ', '')
                        gift_num = lowest_data.get('num', '')
                        
                        gift_floor['url_tonnel'] = f"https://t.me/tonnel_network_bot/gift?startapp={lowest_gift_id}"
                        if gift_num: gift_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}-{gift_num}"
                        else: gift_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}"
                except Exception: pass
            else:
                gift_floor['price'] = "0"
                gift_floor['name'] = "لا توجد هدايا معروضة"
            save_market_db()

async def process_event(event):
    global active_listings, last_event_id, seen_events, needs_db_save
    
    ev_id = event.get('eventId')
    if not ev_id: return
    
    if ev_id in seen_events: return
    seen_events.add(ev_id)
    if len(seen_events) > 10000: seen_events.clear()
    
    ev_type = event.get('type')
    ev_data = event.get('data', {})
    
    gift_info = ev_data.get('gift')
    if not gift_info and 'gift_id' in ev_data: gift_info = ev_data
    gift_id = str(gift_info.get('gift_id')) if gift_info else None
    if not gift_id: return

    if ev_type in ["listing.created", "premarket.listing_created", "listing.price_changed"]:
        if ev_data.get('asset') == 'TON':
            active_listings[gift_id] = {
                'price': float(ev_data.get('price', 0)),
                'name': gift_info.get('gift_name', 'Unknown'),
                'num': gift_info.get('gift_num', '') 
            }
            needs_db_save = True
    elif ev_type in ["listing.cancelled", "premarket.listing_cancelled", "sale.completed", "premarket.sale_completed", "auction.cancelled"]:
        if gift_id in active_listings:
            del active_listings[gift_id]
            needs_db_save = True
            
    last_event_id = ev_id

async def replay_events():
    global last_event_id
    url = "https://gifts.coffin.meme/api/marketplace/events"
    while True:
        params = {"limit": "500"}
        if last_event_id: params["after"] = last_event_id
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 400:
                        last_event_id = "" 
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        events = data.get('events', [])
                        if not events: break
                        for ev in events: await process_event(ev)
                        if len(events) < 500: break 
                    else: break
        except Exception: break

async def tonnel_websocket_loop():
    load_market_db()
    while True:
        await replay_events() 
        global needs_db_save
        needs_db_save = True 
        
        try:
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as websocket:
                async for message in websocket:
                    try:
                        event = json.loads(message)
                        if event.get('type') == "marketplace.connected": continue
                        await process_event(event)
                    except json.JSONDecodeError: pass
        except Exception: 
            await asyncio.sleep(2)

# ==========================================
# نظام الريسيت المتطور (Reset)
# ==========================================
async def reset_market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    
    msg = "اختر السوق الذي تريد عمل تفريغ (Reset) له:"
    btn = [
        [{"text": "مركت (MRKT)", "callback_data": "reset_mrkt", "style": "primary", "icon_custom_emoji_id": MRKT_ICON_ID}],
        [{"text": "تونيل (Tonnel)", "callback_data": "reset_tonnel", "style": "success", "icon_custom_emoji_id": TONNEL_ICON_ID}],
        [{"text": "تفريغ الاثنين", "callback_data": "reset_both", "style": "danger"}]
    ]
    await send_custom_msg(update.message.chat_id, msg, skip_news=True, extra_buttons=btn)

async def handle_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("ليس لديك صلاحية!", show_alert=True)
        return
    
    await query.answer("جاري التفريغ... ⏳")
    data = query.data
    chat_id = query.message.chat.id
    msg_id = query.message.message_id
    
    global active_listings, last_event_id, needs_db_save, mrkt_token, mrkt_floor
    
    if data == "reset_tonnel" or data == "reset_both":
        active_listings.clear()
        last_event_id = ""
        save_market_db()
        await replay_events()
        needs_db_save = True
        
    if data == "reset_mrkt" or data == "reset_both":
        mrkt_token = None 
        mrkt_floor['price'] = "0"
        mrkt_floor['name'] = "جاري التحديث..."
        
    txt = "✅ تم تفريغ السوق وجلب البيانات الجديدة بنجاح."
    await edit_custom_msg(chat_id, msg_id, txt, skip_news=True)


async def track_new_user(user, context: ContextTypes.DEFAULT_TYPE):
    if user.id not in bot_users: bot_users.add(user.id)
    if user.username: user_mapping[user.username.lower()] = user.id

async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result.new_chat_member.status in ["member", "administrator"] and result.old_chat_member.status not in ["member", "administrator"]:
        chat = result.chat
        msg = f"تم تشغيل البوت اكتب الاوامر او اوامر لعرض الشرح {HELLO_EMOJI}"
        try: await send_custom_msg(chat.id, msg)
        except: pass

async def is_user_banned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_user: return False
    user_id = update.effective_user.id
    
    if user_id in banned_users:
        msg = update.message
        if not msg or not msg.text: return True
        
        chat_type = msg.chat.type
        text = msg.text.lower()
        trigger_warning = False
        
        if chat_type == 'private': trigger_warning = True
        elif text.startswith('/'): trigger_warning = True
        elif msg.reply_to_message and context.bot.id == msg.reply_to_message.from_user.id: trigger_warning = True
        elif context.bot.username and context.bot.username.lower() in text: trigger_warning = True
        else:
            bot_keywords = ["الاوامر", "اوامر", "فلور الهدايا", "فلور", "هدايا", "رصيدي", "تغيير محفظتي", "تفعيل التنبيهات", "بحث", "صرف", "سعر", "نبهني"]
            if any(kw in text for kw in bot_keywords): trigger_warning = True

        if trigger_warning:
            warning_msg = 'دروح عمو روح خل واحد من المطورين يفك الحظر منك عود تعال <tg-emoji emoji-id="5872697861166075790">🚫</tg-emoji>'
            btn = [
                [{"text": "الروسي", "url": "https://t.me/M6M9N", "style": "success", "icon_custom_emoji_id": "5372930329822659547"}],
                [{"text": "ساسكي", "url": "https://t.me/O1916", "style": "danger", "icon_custom_emoji_id": "5258021357446268553"}]
            ]
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            inline_keyboard = [btn[0], btn[1], [{"text": "اخبار الهدايا", "url": "https://t.me/Guidance_nft", "style": "primary", "icon_custom_emoji_id": "5224257782013769471"}]]
            payload = {"chat_id": msg.chat_id, "text": warning_msg, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}}
            if msg.message_id: payload["reply_parameters"] = {"message_id": msg.message_id}
            async with aiohttp.ClientSession() as session:
                try: await session.post(url, json=payload)
                except: pass
        return True 
    return False

async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        chat_id = update.callback_query.message.chat.id
        msg_id = update.callback_query.message.message_id
        await edit_custom_msg(chat_id, msg_id, f"تم الإلغاء بنجاح. {SUCCESS_EMOJI}")
    else:
        chat_id = update.message.chat_id
        msg_id = update.message.message_id
        await send_custom_msg(chat_id, f"تم الإلغاء بنجاح. {SUCCESS_EMOJI}", msg_id)
    return ConversationHandler.END

# ==========================================
# نظام الحظر وإلغاء الحظر
# ==========================================
async def process_ban(chat_id, msg_id, target_input, context):
    target_id, target_name = None, target_input
    if target_input.startswith('@'):
        username = target_input.replace('@', '').lower()
        if username in user_mapping: target_id = user_mapping[username]
    elif target_input.isdigit(): target_id = int(target_input)
        
    if target_id:
        if target_id in ADMIN_IDS:
            await send_custom_msg(chat_id, f"عذراً، لا يمكنك حظر المطورين! {WARN_EMOJI}", msg_id)
        else:
            banned_users.add(target_id)
            await send_custom_msg(chat_id, f"✅ تم حظر {target_name} بنجاح.", msg_id)
    else:
        await send_custom_msg(chat_id, f"عذراً، لم أتمكن من العثور على هذا المستخدم في سجلاتي. {WARN_EMOJI}", msg_id)

async def ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return ConversationHandler.END
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name
        if target_id in ADMIN_IDS:
            await send_custom_msg(update.message.chat_id, f"عذراً، لا يمكنك حظر المطورين! {WARN_EMOJI}", update.message.message_id)
        else:
            banned_users.add(target_id)
            await send_custom_msg(update.message.chat_id, f"✅ تم حظر {target_name} بنجاح.", update.message.message_id)
        return ConversationHandler.END
    
    parts = update.message.text.split()
    if len(parts) > 1:
        await process_ban(update.message.chat_id, update.message.message_id, parts[1], context)
        return ConversationHandler.END

    await send_custom_msg(update.message.chat_id, "ارسل ايدي او يوزر الشخص لحظره:", update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_BAN

async def ban_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_ban(update.message.chat_id, update.message.message_id, update.message.text.strip(), context)
    return ConversationHandler.END

async def process_unban(chat_id, msg_id, target_input, context):
    target_id = None
    if target_input.startswith('@'):
        username = target_input.replace('@', '').lower()
        if username in user_mapping: target_id = user_mapping[username]
    elif target_input.isdigit(): target_id = int(target_input)
        
    if target_id and target_id in banned_users:
        banned_users.remove(target_id)
        await send_custom_msg(chat_id, f"✅ تم فك الحظر بنجاح.", msg_id)
    else:
        await send_custom_msg(chat_id, f"المستخدم غير محظور أو لم يتم العثور عليه. {WARN_EMOJI}", msg_id)

async def unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return ConversationHandler.END
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if target_id in banned_users:
            banned_users.remove(target_id)
            await send_custom_msg(update.message.chat_id, f"✅ تم فك الحظر بنجاح.", update.message.message_id)
        else:
            await send_custom_msg(update.message.chat_id, f"المستخدم غير محظور. {WARN_EMOJI}", update.message.message_id)
        return ConversationHandler.END
    
    parts = update.message.text.split()
    if len(parts) > 1:
        await process_unban(update.message.chat_id, update.message.message_id, parts[1], context)
        return ConversationHandler.END

    await send_custom_msg(update.message.chat_id, "ارسل ايدي او يوزر الشخص لفك الحظر عنه:", update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_UNBAN

async def unban_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_unban(update.message.chat_id, update.message.message_id, update.message.text.strip(), context)
    return ConversationHandler.END

# ==========================================
# API فحص المحفظة
# ==========================================
async def check_ton_wallet(address):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://tonapi.io/v2/accounts/{address}"
            async with session.get(url, timeout=5) as resp:
                if resp.status != 200: return False, 0, 0
                data = await resp.json()
                ton_balance = data.get('balance', 0) / 1e9 

            usdt_url = f"https://tonapi.io/v2/accounts/{address}/jettons"
            usdt_balance = 0
            async with session.get(usdt_url, timeout=5) as resp:
                if resp.status == 200:
                    j_data = await resp.json()
                    for b in j_data.get('balances', []):
                        if b['jetton']['symbol'] in ['USD₮', 'USDT']:
                            decimals = b['jetton']['decimals']
                            usdt_balance = float(b['balance']) / (10**decimals)
                            break
            return True, ton_balance, usdt_balance
    except Exception: return False, 0, 0

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_new_user(update.effective_user, context)
    if await is_user_banned(update, context): return ConversationHandler.END
    text = update.message.text
    user = update.message.from_user
    chat_id = update.message.chat_id
    safe_name = html.escape(user.first_name)
    
    add_bot_url = f"https://t.me/{context.bot.username}?startgroup=true&admin=change_info,delete_messages,restrict_members,invite_users,pin_messages,manage_chat"
    
    if 'link_wallet' in text or 'change_wallet' in text:
        if 'link_wallet' in text and user.id in user_wallets:
            msg = f"لديك محفضه مربوطه بالفعل\nلتغيير محفضتك اضغط على الزر ادناه {DOWN_EMOJI} :"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]]
            await send_custom_msg(chat_id, msg, extra_buttons=btn)
            return ConversationHandler.END
        else:
            msg = f"اهلا بك {safe_name} {CROWN_EMOJI}\n\nقم بارسال عنوان محفضتك \nاو الادرس الخاص بك لربط محفضتك {PLANE_EMOJI}"
            await send_custom_msg(chat_id, msg, extra_buttons=[CANCEL_BTN])
            return ASK_WALLET
    else:
        msg = (f"أهلاً بك في البوت يا {safe_name}! {HELLO_EMOJI}\n\n"
               f"هذا البوت يقدم خدمات الصرافة والتنبيهات الذكية وحفظ المعلومات.\n"
               f"اكتب <b>الاوامر</b> او <b>اوامر</b> لعرض جميع خدمات البوت.")
        btn = [[{"text": "اضافه البوت الى مجموعتي", "url": add_bot_url, "style": "primary"}]]
        await send_custom_msg(chat_id, msg, extra_buttons=btn)
        return ConversationHandler.END

async def receive_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    address = html.escape(update.message.text.strip())
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    msg_id = await send_custom_msg(chat_id, f"يتم البحث عن محفضتك... {SEARCH_EMOJI}")
    is_valid, _, _ = await check_ton_wallet(address)
    
    if is_valid:
        await asyncio.sleep(1.5)
        await edit_custom_msg(chat_id, msg_id, f"جاري ربط المحفضه بالبوت... {WAIT_EMOJI}")
        await asyncio.sleep(1.5)
        user_wallets[user_id] = address
        await edit_custom_msg(chat_id, msg_id, f"تم ربط محفضتك بنجاح  . {SUCCESS_EMOJI}")
    else:
        await asyncio.sleep(1.5)
        await edit_custom_msg(chat_id, msg_id, f"عنوان المحفضه خطا ! {FAIL_EMOJI}")
    return ConversationHandler.END

# ==========================================
# أنظمة الصرافة والأسعار
# ==========================================
def normalize_currency(curr_str):
    curr = curr_str.lower().strip()
    if curr in ['دولار', 'usdt', 'usd']: return 'USD'
    elif curr in ['ماستر', 'master']: return 'IQD'
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: return 'STARS'
    elif curr in ['جرام', 'غرام', 'كرام', 'قرام', 'gram']: return 'TON' 
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: return 'BTC'
    elif curr in ['اسيا', 'آسيا', 'asia']: return 'ASIA'
    elif curr in ['باث', 'bath']: return 'BATH'
    return None

def get_current_price(curr_code):
    if curr_code == 'USD': return 1.0
    elif curr_code == 'IQD': return last_known_iqd
    elif curr_code == 'STARS': return 0.015
    elif curr_code in crypto_prices: return crypto_prices[curr_code]
    return 0

def get_daily_trend_emoji(currency, current_price=None):
    if currency in ['BTC', 'TON', 'BATH']:
        change = crypto_24h_trend.get(currency, 0.0)
        if change > 0: return UP_EMOJI
        elif change < 0: return DOWN_EMOJI
        return ""
    elif currency == 'IQD':
        open_price = daily_iqd['open_price']
        if open_price == 0 or current_price == open_price: return ""
        if current_price > open_price: return UP_EMOJI
        elif current_price < open_price: return DOWN_EMOJI
        return ""
    return ""

async def fetch_mastercard_price(session):
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {"Content-Type": "application/json"}
        payload = {"fiat": "IQD", "page": 1, "rows": 1, "tradeType": "SELL", "asset": "USDT", "countries": [], "payTypes": [], "publisherType": None, "merchantCheck": False}
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    price_str = data['data'][0]['adv']['price']
                    price_float = float(price_str)
                    if price_float < 2000: price_float = price_float * 100
                    return int(price_float)
    except Exception: pass
    return None

async def update_prices_if_needed():
    global last_fetch_time, cached_msg, last_known_iqd, crypto_prices, crypto_24h_trend, daily_iqd
    current_time = time.time()
    
    if current_time - last_fetch_time < CACHE_TIME and cached_msg: return True
        
    try:
        async with aiohttp.ClientSession() as session:
            crypto_url = 'https://api.binance.com/api/v3/ticker/24hr?symbols=["BTCUSDT","GRAMUSDT"]'
            crypto_task = session.get(crypto_url, timeout=6)
            master_task = fetch_mastercard_price(session)
            
            response, fetched_iqd = await asyncio.gather(crypto_task, master_task, return_exceptions=True)
            
            if not isinstance(response, Exception) and response.status == 200:
                crypto_data = await response.json()
                for item in crypto_data:
                    symbol = item['symbol']
                    if symbol == 'BTCUSDT':
                        crypto_prices['BTC'] = float(item['lastPrice'])
                        crypto_24h_trend['BTC'] = float(item['priceChangePercent'])
                    elif symbol == 'GRAMUSDT':
                        crypto_prices['TON'] = float(item['lastPrice'])
                        crypto_24h_trend['TON'] = float(item['priceChangePercent'])

            try:
                bath_url = 'https://api.binance.com/api/v3/ticker/24hr?symbol=BATHUSDT'
                async with session.get(bath_url, timeout=3) as bath_resp:
                    if bath_resp.status == 200:
                        bath_data = await bath_resp.json()
                        crypto_prices['BATH'] = float(bath_data['lastPrice'])
                        crypto_24h_trend['BATH'] = float(bath_data['priceChangePercent'])
                    else: crypto_prices['BATH'] = 0.03
            except: crypto_prices['BATH'] = 0.03

            if isinstance(fetched_iqd, int) and fetched_iqd > 0: last_known_iqd = fetched_iqd
                
            today_str = datetime.now().strftime('%Y-%m-%d')
            if daily_iqd['date'] != today_str:
                daily_iqd['date'] = today_str
                daily_iqd['open_price'] = last_known_iqd

            btc_int = int(crypto_prices.get('BTC', 0))
            ton_val = crypto_prices.get('TON', 0)
            bath_val = crypto_prices.get('BATH', 0.03)
            
            btc_trend = get_daily_trend_emoji('BTC')
            ton_trend = get_daily_trend_emoji('TON')
            bath_trend = get_daily_trend_emoji('BATH')
            iqd_trend = get_daily_trend_emoji('IQD', last_known_iqd)
            asia_price_for_100_usd = int(last_known_iqd / 0.9)

            msg = (f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                   f'{GIFT_FLOOR_EMOJI} فلور الهدايا (تونيل): <b>{gift_floor["price"]}</b> {GRAM_EMOJI}\n'
                   f'{MRKT_TEXT_EMOJI} فلور الهدايا (مركت): <b>{mrkt_floor["price"]}</b> {GRAM_EMOJI}\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'{MASTER_EMOJI} الدولار (100$): <b>{last_known_iqd:,}</b> IQD {iqd_trend}\n'
                   f'{ASIA_EMOJI} اسيا (100$): <b>{asia_price_for_100_usd:,}</b> دينار\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc_int:,}</b> {btc_trend}\n'
                   f'{GRAM_EMOJI} GRAM: <b>${ton_val:,.2f}</b> {ton_trend}\n'
                   f'{BATH_EMOJI} BATH: <b>${bath_val:,.4f}</b> {bath_trend}\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية والمحلية</i>\n'
                   f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>')
            cached_msg = msg
            last_fetch_time = current_time
            return True
    except Exception: return False

def generate_conversion_msg(amount, currency_str):
    curr = currency_str.lower()
    show_usd, show_iqd = True, True

    if curr in ['دولار', 'usdt', 'usd']: base, name, usd_val, show_usd = 'USD', "دولار (USDT)", amount, False  
    elif curr in ['ماستر', 'master']:
        base, name = 'IQD', f"{MASTER_EMOJI} ماستر"
        actual_iqd = amount * 1000 if amount < 100000 else amount
        usd_val = actual_iqd / (last_known_iqd / 100)
        show_iqd = False  
    elif curr in ['اسيا', 'asia', 'آسيا']:
        base, name = 'ASIA', f"{ASIA_EMOJI} اسيا"
        actual_asia = amount * 1000 if amount < 100000 else amount
        value_in_master = actual_asia * 0.9
        usd_val = value_in_master / (last_known_iqd / 100)
    elif curr in ['باث', 'bath']: base, name, usd_val = 'BATH', f"{BATH_EMOJI} باث (BATH)", amount * crypto_prices.get('BATH', 0.03)
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: base, name, usd_val = 'STARS', '<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم', amount * 0.015 
    elif curr in ['جرام', 'غرام', 'كرام', 'قرام', 'gram']: base, name, usd_val = 'TON', "جرام (GRAM)", amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: base, name, usd_val = 'BTC', "بتكوين (BTC)", amount * crypto_prices.get('BTC', 0)
    else: return f"عذراً، العملة غير مدعومة. {WARN_EMOJI}"

    if usd_val == 0: return f"عذراً، لا يمكن حساب القيمة الآن. {WARN_EMOJI}"

    iqd_val = (usd_val * last_known_iqd) / 100
    asia_val = iqd_val / 0.9 
    ton_val = usd_val / crypto_prices['TON'] if crypto_prices.get('TON') else 0
    bath_val = usd_val / crypto_prices.get('BATH', 0.03)
    stars_val = usd_val / 0.015 
    btc_val = usd_val / crypto_prices['BTC'] if crypto_prices.get('BTC') else 0

    msg = f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <b>تصريف {amount:g} {name}:</b>\n\n'
    if show_usd: msg += f'{USDT_CASH} بالدولار: <b>${usd_val:,.3f}</b>\n'
    if show_iqd: msg += f'{MASTER_EMOJI} بالماستر: <b>{iqd_val:,.0f}</b> IQD\n'
    if base != 'ASIA': msg += f'{ASIA_EMOJI} بالاسيا: <b>{asia_val:,.0f}</b> دينار\n'
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    if base != 'TON' and ton_val > 0: msg += f'{GRAM_EMOJI} جرام: <b>{ton_val:,.2f}</b> GRAM\n'
    if base != 'BATH' and bath_val > 0: msg += f'{BATH_EMOJI} باث: <b>{bath_val:,.0f}</b> BATH\n'
    if base != 'STARS' and stars_val > 0: msg += f'<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم: <b>{stars_val:,.0f}</b> Stars\n'
    if base != 'STARS' and base != 'BTC' and btc_val > 0: msg += f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> بتكوين: <b>{btc_val:,.6f}</b> BTC\n'
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    msg += f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>'
    return msg

# ==========================================
# نظام التنبيهات
# ==========================================
async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    msg = f"{WHALE_BELL} <b>نظام التنبيهات الذكي</b>\n\nاكتب اسم العملة اللي تريد أراقبها (مثال: جرام، بتكوين، باث، ماستر...):"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_CURRENCY

async def alert_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    curr_input = html.escape(update.message.text.strip())
    
    if re.search(r'(^|\s)(تون|ton)(\s|$)', curr_input.lower()):
        msg = f"ياغبي التون صار اسمه جرام\nيله اكتب الامر بالجرام علمود ارد عليك {FOOL_EMOJI}"
        await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
        return ASK_CURRENCY

    curr_code = normalize_currency(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, f"عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_CURRENCY
    
    context.user_data['alert_curr'] = curr_code; context.user_data['alert_curr_name'] = curr_input
    await send_custom_msg(update.message.chat_id, f"{SUCCESS_EMOJI} تم اختيار: <b>{curr_input}</b>\n\nالآن ادخل السعر الذي تريد التنبيه عنده (أرقام فقط):", update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_PRICE

async def alert_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    price_input = update.message.text.strip()
    match = re.search(r'(\d+(?:\.\d+)?)', price_input)
    if not match:
        await send_custom_msg(update.message.chat_id, f"يرجى إدخال رقم صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_PRICE
        
    target_price = float(match.group(1))
    curr_code, curr_name = context.user_data['alert_curr'], context.user_data['alert_curr_name']
    safe_name = html.escape(update.message.from_user.first_name)
    
    await update_prices_if_needed()
    current_price = get_current_price(curr_code)
    
    if current_price == 0:
        await send_custom_msg(update.message.chat_id, f"عذراً، لا يمكن جلب السعر الحالي، حاول لاحقاً. {WARN_EMOJI}", update.message.message_id)
        return ConversationHandler.END
        
    if round(target_price, 4) == round(current_price, 4):
        await send_custom_msg(update.message.chat_id, f"الـ {curr_name} أصلاً واصل هذا السعر بالضبط! {WARN_EMOJI}\nالسعر الحالي هو: {current_price:g}", update.message.message_id)
        return ConversationHandler.END
        
    direction = 'up' if target_price > current_price else 'down'
    alerts_db.append({'user_id': update.message.from_user.id, 'name': safe_name, 'chat_id': update.message.chat_id, 'currency': curr_code, 'curr_name': curr_name, 'target': target_price, 'direction': direction, 'active': True})
    
    dir_txt = "صعود 📈" if direction == 'up' else "نزول 📉"
    msg = (f"{SUCCESS_EMOJI} <b>تم التفعيل!</b>\nسيتم تنبيهك عند {dir_txt} الـ {curr_name} إلى <code>{target_price:g}</code>\n"
           f"(علماً أن السعر الحالي هو: <b>{current_price:g}</b>)\n\nلإيقاف التنبيه ارسل /ايقاف")
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    global alerts_db
    user_id = update.message.from_user.id
    initial_len = len(alerts_db)
    alerts_db = [a for a in alerts_db if a['user_id'] != user_id]
    msg = f"تم إيقاف جميع تنبيهات الأسعار بنجاح. {SUCCESS_EMOJI}" if len(alerts_db) < initial_len else f"ليس لديك أي تنبيهات أسعار مفعلة. {WARN_EMOJI}"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return
    user_id = update.message.from_user.id
    user_alerts = [a for a in alerts_db if a['user_id'] == user_id and a['active']]
    if not user_alerts:
        await send_custom_msg(update.message.chat_id, f"لا توجد لديك أي تنبيهات مفعلة حالياً. {WARN_EMOJI}", update.message.message_id)
        return
    msg = f"{WHALE_BELL} <b>تنبيهاتك الحالية:</b>\n\n"
    for idx, a in enumerate(user_alerts, 1):
        dir_txt = "صعود " + UP_EMOJI if a['direction'] == 'up' else "نزول " + DOWN_EMOJI
        msg += f"{idx}. <b>{a['curr_name']}</b> - السعر المطلوب: <code>{a['target']:g}</code> ({dir_txt})\n"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)

async def toggle_whale_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    safe_name = html.escape(update.message.from_user.first_name)
    
    if user_id in whale_alert_users:
        del whale_alert_users[user_id]
        await send_custom_msg(chat_id, f"تم الغاء تفعيل تنبيهات الحيتان {SUCCESS_EMOJI}", update.message.message_id)
    else:
        whale_alert_users[user_id] = {"name": safe_name, "chat_id": chat_id}
        msg = (f"{SUCCESS_EMOJI} <b>تم تفعيل تنبيهات الحيتان بنجاح!</b>\n\n"
               "<b>الفائدة من هذا الوضع:</b>\n"
               "البوت سيقوم بمراقبة شبكة عملة الجرام (TON)، وعند حدوث عملية تحويل ضخمة جداً (أكثر من 8000 جرام)، "
               "سيصلك إشعار فوري. هذه الحركات الكبيرة تؤثر عادةً على السعر وتساعدك في اتخاذ قرارات الشراء أو البيع في الوقت المناسب.")
        await send_custom_msg(chat_id, msg, update.message.message_id)

async def check_whales_loop(app: Application):
    last_tx_hash = ""
    while True:
        await asyncio.sleep(20) 
        if not whale_alert_users: continue
        try:
            wallet = "EQBX63RAdgShnrJGptNINn2uUFIqEQ9_hD0z4E7h-gH-Zk5t" 
            url = f"https://tonapi.io/v2/accounts/{wallet}/events?limit=10"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        events = data.get('events', [])
                        if not events: continue
                        new_latest_hash = events[0].get('event_id')
                        if last_tx_hash == "":
                            last_tx_hash = new_latest_hash
                            continue
                        for event in events:
                            tx_hash = event.get('event_id')
                            if tx_hash == last_tx_hash: break 
                            for action in event.get('actions', []):
                                if action.get('type') == 'TonTransfer':
                                    ton_transfer_data = action.get('TonTransfer', {})
                                    amount = float(ton_transfer_data.get('amount', 0)) / 1e9
                                    if amount >= 8000:
                                        grouped_by_chat = {}
                                        for uid, udata in whale_alert_users.items():
                                            cid = udata['chat_id']
                                            if cid not in grouped_by_chat: grouped_by_chat[cid] = []
                                            grouped_by_chat[cid].append({'id': uid, 'name': udata['name']})
                                            
                                        for cid, users in grouped_by_chat.items():
                                            mentions = " ".join([f"<a href='tg://user?id={u['id']}'>{u['name']}</a>" for u in users])
                                            msg = (f"يا : {mentions} {WHALE_BELL}\n\n"
                                                   f"حصلت عملية تحويل بقيمه {amount:,.0f} جرام {WHALE_EMOJI}\n\n"
                                                   f"هل صعود {UP_EMOJI}؟ او نزول {DOWN_EMOJI}؟")
                                            await send_custom_msg(cid, msg)
                        last_tx_hash = new_latest_hash
        except Exception: pass 

async def check_alerts_loop(app: Application):
    global alerts_db 
    while True:
        await asyncio.sleep(3) 
        if not alerts_db: continue
        if not await update_prices_if_needed(): continue
        
        triggered_alerts = []
        for alert in alerts_db:
            if not alert['active']: continue
            curr_price = get_current_price(alert['currency'])
            if curr_price == 0: continue
            if (alert['direction'] == 'up' and curr_price >= alert['target']) or \
               (alert['direction'] == 'down' and curr_price <= alert['target']):
                triggered_alerts.append(alert)
                alert['active'] = False
        
        if triggered_alerts:
            grouped = {}
            for alert in triggered_alerts:
                chat_id, curr_code = alert['chat_id'], alert['currency']
                if chat_id not in grouped: grouped[chat_id] = {}
                if curr_code not in grouped[chat_id]: grouped[chat_id][curr_code] = []
                grouped[chat_id][curr_code].append(alert)
            for chat_id, currencies in grouped.items():
                for curr_code, alerts in currencies.items():
                    mentions = " ".join([f"<a href='tg://user?id={a['user_id']}'>{a['name']}</a>" for a in alerts])
                    msg = (f"{WARN_EMOJI} {mentions}\n\n🔥 <b>الحگ! الـ {alerts[0]['curr_name']} وصل للسعر المطلوب!</b>\n"
                           f"السعر الحالي: <b>{get_current_price(curr_code):g}</b>\n\nلإيقاف التنبيهات ارسل /ايقاف")
                    await send_custom_msg(chat_id, msg)
        alerts_db = [a for a in alerts_db if a['active']]

async def post_init(app: Application):
    asyncio.create_task(check_alerts_loop(app))
    asyncio.create_task(check_whales_loop(app)) 
    asyncio.create_task(tonnel_websocket_loop()) 
    asyncio.create_task(floor_updater_loop())
    asyncio.create_task(mrkt_updater_loop())

# ==========================================
# نظام بحث الهدايا الدقيق (تونيل + مركت)
# ==========================================
def resolve_gift_name_mrkt(search_term):
    if not search_term: return ""
    s = search_term.lower().replace("'", "").replace("’", "").replace("-", " ").strip()
    if s in ALIASES: return ALIASES[s]
    for known in KNOWN_GIFTS:
        k = known.lower().replace("'", "").replace("’", "").replace("-", " ")
        if s == k: return known
    search_words = s.split()
    for known in KNOWN_GIFTS:
        k = known.lower().replace("'", "").replace("’", "").replace("-", " ")
        if all(word in k for word in search_words): return known
    for known in KNOWN_GIFTS:
        k = known.lower().replace("'", "").replace("’", "").replace("-", " ")
        if s in k: return known
    return search_term.title()

async def gift_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    msg = f"{SEARCH_EMOJI} <b>بحث عن هدية</b>\n\nاختر السوق الذي تريد البحث فيه:"
    btn = [
        [{"text": "بحث في مركت", "callback_data": "search_mrkt", "style": "success", "icon_custom_emoji_id": MRKT_ICON_ID}],
        [{"text": "بحث في تونيل", "callback_data": "search_tonnel", "style": "danger", "icon_custom_emoji_id": TONNEL_ICON_ID}],
        [{"text": "الغاء", "callback_data": "cancel", "style": "primary", "icon_custom_emoji_id": "5440681540541502133"},
         {"text": "اخبار الهدايا", "url": "https://t.me/Guidance_nft", "style": "danger", "icon_custom_emoji_id": "5224257782013769471"}]
    ]
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=btn, skip_news=True)
    return ASK_MARKET_CHOICE

async def handle_market_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    msg_id = query.message.message_id
    data = query.data
    
    if data == "search_tonnel":
        await edit_custom_msg(chat_id, msg_id, f"{TONNEL_ICON_ID} أرسل اسم الهدية (أو رابطها) للبحث في <b>تونيل</b>:", extra_buttons=[CANCEL_BTN], skip_news=True)
        return ASK_GIFT_SEARCH_TONNEL
    elif data == "search_mrkt":
        await edit_custom_msg(chat_id, msg_id, f"{MRKT_TEXT_EMOJI} أرسل اسم الهدية (مثال: bunny muffin) للبحث في <b>مركت</b>:", extra_buttons=[CANCEL_BTN], skip_news=True)
        return ASK_GIFT_SEARCH_MRKT

async def perform_gift_search_tonnel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    raw_query = update.message.text.strip()
    search_query = raw_query.lower()
    chat_id = update.message.chat_id
    msg_id = update.message.message_id
    
    if 't.me/nft/' in search_query or 'fragment.com' in search_query:
        match = re.search(r'nft/([a-zA-Z0-9_]+)', search_query)
        if match: search_query = match.group(1).replace('-', ' ')
            
    search_query = re.sub(r'-\d+$', '', search_query).strip()
    clean_compare = search_query.replace(' ', '')
    
    msg_wait = await send_custom_msg(chat_id, f"جاري البحث في تونيل عن <b>{search_query}</b>... {SEARCH_EMOJI}", msg_id)
    
    found_price, found_name, found_gift_id, found_gift_num = None, search_query, None, None
    for gift_id, data in active_listings.items():
        listing_name_clean = data['name'].lower().replace(' ', '')
        if clean_compare in listing_name_clean:
            price_val = float(data.get('price', 0))
            if price_val > 0 and (found_price is None or price_val < found_price):
                found_price, found_name, found_gift_id, found_gift_num = price_val, data['name'], gift_id, data.get('num', '')
                
    if found_price is None:
        try:
            search_url = f"https://api.getgems.io/graphql"
            payload = {"query": "query Search($query: String!) { alphaSearch(query: $query) { collections { name stats { floorPrice } } } }", "variables": {"query": search_query}}
            headers = {"Content-Type": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.post(search_url, json=payload, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        collections = data.get("data", {}).get("alphaSearch", {}).get("collections", [])
                        for col in collections:
                            col_name = col.get("name", "").lower().replace(' ', '')
                            if clean_compare in col_name and col.get("stats", {}).get("floorPrice"):
                                price_nano = float(col["stats"]["floorPrice"])
                                current_price = price_nano / 1e9
                                if current_price > 0 and (found_price is None or current_price < found_price):
                                    found_price, found_name = current_price, col.get("name")
        except: pass
            
    if found_price is not None and found_price > 0:
        clean_url_name = found_name.lower().replace(' ', '')
        btn = []
        if found_gift_id:
            url_tonnel = f"https://t.me/tonnel_network_bot/gift?startapp={found_gift_id}"
            btn.append([{"text": "عرض في Tonnel", "url": url_tonnel, "style": "success", "icon_custom_emoji_id": TONNEL_ICON_ID}])
        url_telegram = f"https://t.me/nft/{clean_url_name}-{found_gift_num}" if found_gift_num else f"https://t.me/nft/{clean_url_name}"
        btn.append([{"text": "عرض في تيليجرام", "url": url_telegram, "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}])
            
        exact_price_text = format_exact_price(found_price)
        msg = f"{GIFT_FLOOR_EMOJI} نتيجة البحث في تونيل:\nالهدية: <b>{found_name}</b>\nأقل سعر: <b>{exact_price_text}</b> {GRAM_EMOJI}"
        await edit_custom_msg(chat_id, msg_wait, msg, extra_buttons=btn)
    else:
        await edit_custom_msg(chat_id, msg_wait, f"عذراً، لم أتمكن من العثور على الهدية في تونيل. {FAIL_EMOJI}")
    return ConversationHandler.END

async def perform_gift_search_mrkt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    raw_query = update.message.text.strip()
    chat_id = update.message.chat_id
    msg_id = update.message.message_id
    
    msg_wait = await send_custom_msg(chat_id, f"جاري البحث في مركت عن <b>{raw_query}</b>... {SEARCH_EMOJI}", msg_id)
    
    global mrkt_token
    if not mrkt_token: mrkt_token = await get_mrkt_auth_token()
    
    if not mrkt_token:
        await edit_custom_msg(chat_id, msg_wait, f"عذراً، يوجد مشكلة في الاتصال بـ MRKT حالياً. {WARN_EMOJI}")
        return ConversationHandler.END

    exact_name = resolve_gift_name_mrkt(raw_query)
    headers = {'Authorization': str(mrkt_token), 'Referer': 'https://cdn.tgmrkt.io/'}
    
    found_gift = None
    cursor = ""
    for _ in range(5): 
        json_data = {
            "collectionNames": [exact_name] if exact_name else [], "modelNames": [], "backdropNames": [], "symbolNames": [],
            "ordering": "Price", "lowToHigh": True, "count": 20, "cursor": cursor, "promotedFirst": False
        }
        try:
            async with AsyncSession(impersonate="chrome") as s:
                r = await s.post('https://api.tgmrkt.io/api/v1/gifts/saling', headers=headers, json=json_data)
                if r.status_code == 401:
                    mrkt_token = None
                    await edit_custom_msg(chat_id, msg_wait, f"انتهت صلاحية الاتصال بـ MRKT، حاول مرة أخرى. {WARN_EMOJI}")
                    return ConversationHandler.END
                
                if r.status_code == 200:
                    data = r.json()
                    gifts = data.get("gifts", [])
                    for g in gifts:
                        if isinstance(g, dict) and g.get("isOnSale") is not False:
                            returned_name = g.get("collectionName", "").lower().replace("'", "").replace("’", "")
                            target_name = exact_name.lower().replace("'", "").replace("’", "")
                            if target_name in returned_name:
                                found_gift = g
                                break
                    if found_gift: break
                    
                    next_cursor = data.get("cursor")
                    if not next_cursor or next_cursor == cursor: break
                    cursor = next_cursor
                else: break
        except: break

    if found_gift:
        price = None
        for key in ["salePrice", "salePriceWithoutFee", "floorPriceNanoTONsByCollection"]:
            val = found_gift.get(key)
            if isinstance(val, (int, float)) and val > 0:
                price = int(val)
                break
        
        if price:
            ton_price = price / 1_000_000_000
            gift_name = found_gift.get("title") or found_gift.get("collectionTitle") or found_gift.get("collectionName") or "Unknown"
            gift_id = found_gift.get("id")
            
            btn = []
            if gift_id:
                url_mrkt = f"https://t.me/mrkt/app?startapp={gift_id}"
                btn.append([{"text": "عرض في MRKT", "url": url_mrkt, "style": "success", "icon_custom_emoji_id": MRKT_ICON_ID}])
            
            clean_url_name = gift_name.lower().replace(' ', '')
            btn.append([{"text": "عرض في تيليجرام", "url": f"https://t.me/nft/{clean_url_name}", "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}])
                
            exact_price_text = format_exact_price(ton_price)
            msg = f"{MRKT_TEXT_EMOJI} نتيجة البحث في مركت:\nالهدية: <b>{gift_name}</b>\nأقل سعر: <b>{exact_price_text}</b> {GRAM_EMOJI}"
            await edit_custom_msg(chat_id, msg_wait, msg, extra_buttons=btn)
            return ConversationHandler.END

    await edit_custom_msg(chat_id, msg_wait, f"عذراً، لم أتمكن من العثور على الهدية في مركت. {FAIL_EMOJI}")
    return ConversationHandler.END

# --- معالجة الرسائل العامة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    original_text = update.message.text.strip()
    text = original_text.lower()
    chat_id, user_id, msg_id = update.message.chat_id, update.message.from_user.id, update.message.message_id
    
    await track_new_user(update.effective_user, context)
    if await is_user_banned(update, context): return

    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text.split() for word in forbidden): return

    if re.search(r'(^|\s)(تون|ton)(\s|$)', text):
        msg = f"ياغبي التون صار اسمه جرام\nيله اكتب الامر بالجرام علمود ارد عليك {FOOL_EMOJI}"
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    if text in ["الاوامر", "اوامر"]:
        msg = f"اهلا بك في قائمه اوامر البوت {CLIPBOARD_EMOJI}\n\n"
        msg += f'{NUM_EMOJIS[1]} <b>صرف [رقم] [عملة]</b>: لحساب قيمة العملات مباشرة (دولار، ماستر، جرام، بتكوين، اسيا، نجوم، باث) {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[2]} <b>نبهني</b>: لمراقبة سعر عملة معينة وتنبيهك عند وصولها للهدف {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[3]} <b>تنبيهاتي</b>: لعرض وإدارة تنبيهات الأسعار الخاصة بك {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[4]} <b>تفعيل التنبيهات</b>: لتفعيل/إلغاء وضع مراقبة حيتان GRAM وإرسال إشعار للتحويلات الضخمة {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[5]} <b>رصيدي</b>: لمعرفة رصيدك في المحفظة المربوطة {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[6]} <b>تغيير محفظتي</b>: لربط أو تغيير محفظة GRAM الخاصة بك {END_EMOJIS}\n'
        msg += f'<tg-emoji emoji-id="5411597774359653692">🔍</tg-emoji> <b>بحث هدية</b>: للبحث عن ارخص سعر لهدية معينة {END_EMOJIS}\n'
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    if text == "تفعيل التنبيهات":
        await toggle_whale_alerts(update, context)
        return

    if text in ["فلور الهدايا", "فلور", "هدايا"]:
        msg = f"{GIFT_FLOOR_EMOJI} فلور الهدايا (تونيل):\nالهدية: <b>{gift_floor['name']}</b>\nالسعر: <b>{gift_floor['price']}</b> {GRAM_EMOJI}\n\n"
        msg += f"{MRKT_TEXT_EMOJI} فلور الهدايا (مركت):\nالهدية: <b>{mrkt_floor['name']}</b>\nالسعر: <b>{mrkt_floor['price']}</b> {GRAM_EMOJI}"
        
        btn = []
        if gift_floor.get('url_tonnel'): btn.append([{"text": "عرض في Tonnel", "url": gift_floor["url_tonnel"], "style": "success", "icon_custom_emoji_id": TONNEL_ICON_ID}])
        if mrkt_floor.get('url_mrkt'): btn.append([{"text": "عرض في MRKT", "url": mrkt_floor["url_mrkt"], "style": "primary", "icon_custom_emoji_id": MRKT_ICON_ID}])
            
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        return

    if text in ["رصيدي", "/رصيدي", "رص", "/رص"]:
        if user_id not in user_wallets:
            msg = f"لم تقم بربط محفضتك بالبوت {WARN_EMOJI}"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]]
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        else:
            is_valid, ton_bal, usdt_bal = await check_ton_wallet(user_wallets[user_id])
            if is_valid:
                await send_custom_msg(chat_id, f"الان لديك :\nGRAM {GRAM_EMOJI}: {ton_bal:.2f}\nUSDT {USDT_CASH}: {usdt_bal:.2f}", reply_to_message_id=msg_id)
            else:
                await send_custom_msg(chat_id, f"عذراً، مشكلة في محفظتك المربوطة. {WARN_EMOJI}", reply_to_message_id=msg_id)
        return
        
    if text in ["رصيده", "/رصيده"]:
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            target_id = target_user.id
            target_name = html.escape(target_user.first_name)
            
            if target_id not in user_wallets:
                msg = f"المستخدم <b>{target_name}</b> لم يقم بربط محفظته بالبوت {WARN_EMOJI}"
                await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
            else:
                is_valid, ton_bal, usdt_bal = await check_ton_wallet(user_wallets[target_id])
                if is_valid:
                    await send_custom_msg(chat_id, f"الان رصيد {target_name} هو :\nGRAM {GRAM_EMOJI}: {ton_bal:.2f}\nUSDT {USDT_CASH}: {usdt_bal:.2f}", reply_to_message_id=msg_id)
                else:
                    await send_custom_msg(chat_id, f"عذراً، مشكلة في محفظة {target_name} المربوطة. {WARN_EMOJI}", reply_to_message_id=msg_id)
        else:
            await send_custom_msg(chat_id, f"يرجى الرد على رسالة الشخص لمعرفة رصيده {WARN_EMOJI}", reply_to_message_id=msg_id)
        return

    if text in ["تغيير محفظتي", "/تغيير محفظتي", "تغيير محفضتي", "/تغيير محفضتي"]:
        btn = [[{"text": "تغيير محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]]
        await send_custom_msg(chat_id, f"اضغط على الزر أدناه لتغيير محفظتك المربوطة {DOWN_EMOJI}:", reply_to_message_id=msg_id, extra_buttons=btn)
        return

    calc_match = re.match(r'^(?:صرف|سعر|حساب)?\s*(\d+(?:\.\d+)?)\s*(جرام|غرام|كرام|قرام|gram|دولار|usdt|usd|ماستر|master|بتكوين|بيتكوين|btc|bitcoin|اسيا|آسيا|asia|باث|bath|نجمه|نجمة|نجوم|star|stars|نج)\s*$', text)
    if calc_match:
        await update_prices_if_needed()
        reply = generate_conversion_msg(float(calc_match.group(1)), calc_match.group(2))
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)
        return

    exact_price_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "جرام", "غرام", "كرام", "قرام", "btc", "gram", "ماستر", "نجوم", "نجمة", "نج", "اسيا", "باث", "bath", "صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار", "ص", "صر"]
    if text in exact_price_keywords:
        await update_prices_if_needed()
        reply = cached_msg if cached_msg else f"عذراً، حاول ثواني.. {WAIT_EMOJI}"
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال بقوة 🔥"
def run_web(): web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)
    app = (Application.builder().token(TOKEN).request(t_request).post_init(post_init).build())
    
    cancel_handlers = [
        MessageHandler(filters.Regex(r'^(الغاء|/cancel)$'), cancel_action),
        CallbackQueryHandler(cancel_action, pattern="^cancel$")
    ]
    
    alert_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?نبهني$'), alert_start)],
        states={
            ASK_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), alert_currency)], 
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), alert_price)]
        }, fallbacks=cancel_handlers + [MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts)]
    )
    
    wallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), receive_wallet_address)]},
        fallbacks=cancel_handlers
    )
    
    search_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?بحث هدية$|/?بحث$'), gift_search_start)],
        states={
            ASK_MARKET_CHOICE: [CallbackQueryHandler(handle_market_choice, pattern="^search_")],
            ASK_GIFT_SEARCH_TONNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), perform_gift_search_tonnel)],
            ASK_GIFT_SEARCH_MRKT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), perform_gift_search_mrkt)]
        },
        fallbacks=cancel_handlers
    )
    
    ban_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ban", ban_start), MessageHandler(filters.Regex(r'^/?حظر$'), ban_start)],
        states={ASK_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), ban_receive)]},
        fallbacks=cancel_handlers
    )
    
    unban_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("unban", unban_start), MessageHandler(filters.Regex(r'^/?الغاء حظر$|/?الغاء الحظر$'), unban_start)],
        states={ASK_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), unban_receive)]},
        fallbacks=cancel_handlers
    )
    
    app.add_handler(alert_conv_handler)
    app.add_handler(wallet_conv_handler)
    app.add_handler(search_conv_handler)
    app.add_handler(ban_conv_handler)
    app.add_handler(unban_conv_handler)
    
    app.add_handler(CommandHandler("reset", reset_market_cmd))
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^reset_"))
    
    app.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts))
    app.add_handler(MessageHandler(filters.Regex(r'^/?تنبيهاتي$'), my_alerts)) 
    
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
