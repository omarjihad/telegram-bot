import os, base64
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import time, aiohttp, logging, threading, asyncio, re, html, json, websockets
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request, send_from_directory
from urllib.parse import unquote
from telegram import Update
from telegram.ext import Application, MessageHandler, ConversationHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, ChatMemberHandler
from telegram.request import HTTPXRequest
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw.types import InputBotAppShortName, InputUser
from curl_cffi.requests import AsyncSession

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.ERROR) 
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

TOKEN = os.environ.get("BOT_TOKEN", "8679057078:AAE-k1jPdS77wPbDsz43aMlKeZqYZynipt8")
PYRO_API_ID = int(os.environ.get("PYRO_API_ID", 12345678)) 
PYRO_API_HASH = os.environ.get("PYRO_API_HASH", "PUT_YOUR_API_HASH_HERE")
RAW_SESSION = os.environ.get("SESSION_NAME", "mrkt_session")

ADMIN_IDS = [7126816492, 1955081272]
DB_FILE = "tonnel_db.json"
HISTORY_FILE = "price_history.json"
TONAPI_KEY = os.environ.get("TONAPI_KEY", "")
# يقبل الاسم المختصر (SrF) او الرابط كامل (https://t.me/bot/SrF) وياخذ الاسم من اخره
MINIAPP_SHORT_NAME = os.environ.get("MINIAPP_SHORT_NAME", "").replace(" ", "").rstrip("/").split("/")[-1].split("?")[0]
IRAQ_TZ = timezone(timedelta(hours=3))

NEWS_URL = "https://t.me/Guidance_nft"
NEWS_BTN = {"text": "اخبار الهدايا", "url": NEWS_URL, "style": "danger", "icon_custom_emoji_id": "5224257782013769471"}

if len(RAW_SESSION) > 50:
    pyro_client = PyroClient(name="mrkt_memory", api_id=PYRO_API_ID, api_hash=PYRO_API_HASH, session_string=RAW_SESSION, in_memory=True, no_updates=True)
else:
    pyro_client = PyroClient(name=RAW_SESSION, api_id=PYRO_API_ID, api_hash=PYRO_API_HASH, no_updates=True)

CACHE_TIME = 2
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000
crypto_prices = {'BTC': 0, 'TON': 0, 'BATH': 0.03} 
crypto_24h_trend = {'BTC': 0.0, 'TON': 0.0, 'BATH': 0.0} 
daily_iqd = {'date': '', 'open_price': 0} 

alerts_db = []
gift_alert_users = {} 
notified_mrkt_gifts = set() 
user_wallets = {} 
bot_users = set() 
whale_alert_users = {} 
banned_users = set() 
user_mapping = {} 

mrkt_http = None

ASK_WALLET = 3 
ASK_MARKET_CHOICE = 4
ASK_GIFT_SEARCH_TONNEL = 5
ASK_GIFT_SEARCH_MRKT = 6
ASK_BAN = 7
ASK_UNBAN = 8
ASK_ALERT_TYPE, ASK_CURRENCY_NAME, ASK_CURRENCY_PRICE = 20, 21, 22
ASK_CALC_CURRENCY, ASK_CALC_PRICE, ASK_CALC_AMOUNT = 30, 31, 32

WS_URL = 'wss://gifts.coffin.meme/api/marketplace/ws'
active_listings = {}
last_event_id = ""
seen_events = set()
needs_db_save = False

gift_floor = {"price": "0", "url_tonnel": "https://t.me/tonnel_network_bot", "url_telegram": "https://t.me/nft", "name": "جاري التحديث..."}
mrkt_token = None
mrkt_floor = {"price": "0", "url_mrkt": "https://t.me/mrkt", "url_telegram": "https://t.me/nft", "name": "جاري التحديث..."}

GIFT_FLOOR_EMOJI = '<tg-emoji emoji-id="5255980157058975232">🎁</tg-emoji>'
MRKT_TEXT_EMOJI = '<tg-emoji emoji-id="6041916763719866213">🛒</tg-emoji>'
MRKT_ICON_ID = "6041916763719866213"
TONNEL_ICON_ID = "5210956306952758910"
TONNEL_TEXT_EMOJI = '<tg-emoji emoji-id="5210956306952758910">💎</tg-emoji>'
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
    return f"{float(price):.2f}".rstrip('0').rstrip('.')

def format_large_amount(amt):
    if amt == int(amt): return f"{int(amt):,}"
    return f"{amt:,.2f}"

async def trigger_gift_alert(gift_name, floor, drop_price, gift_id, market, gift_num):
    if not gift_alert_users: return
    clean_url_name = gift_name.lower().replace(' ', '').replace('’', '').replace("'", "")
    url_telegram = f"https://t.me/nft/{clean_url_name}-{gift_num}" if gift_num else f"https://t.me/nft/{clean_url_name}"
    btn = []
    url_market = f"https://t.me/mrkt/app?startapp={gift_id}"
    btn.append([{"text": "شراء من MRKT", "url": url_market, "style": "success", "icon_custom_emoji_id": MRKT_ICON_ID}])
    btn.append([{"text": "عرض في تيليجرام", "url": url_telegram, "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}])
    grouped_by_chat = {}
    for uid, udata in gift_alert_users.items():
        cid = udata['chat_id']
        if cid not in grouped_by_chat: grouped_by_chat[cid] = []
        grouped_by_chat[cid].append({'id': uid, 'name': udata['name']})
    for cid, users in grouped_by_chat.items():
        mentions = " ".join([f"<a href='tg://user?id={u['id']}'>{u['name']}</a>" for u in users])
        msg = (f"يا : {mentions} {WHALE_BELL}\n\n"
               f"🔥 <b>صيد هدايا جديد! (خصم 6% أو أكثر)</b> 🔥\n\n"
               f"🎁 الهدية: <b>{gift_name}</b>\n"
               f"📉 السعر المعروض: <b>{format_exact_price(drop_price)}</b> {GRAM_EMOJI}\n"
               f"📊 الفلور الحالي: <b>{format_exact_price(floor)}</b> {GRAM_EMOJI}\n"
               f"🛒 السوق: <b>{market}</b>")
        await send_custom_msg(cid, msg, extra_buttons=btn)

def extract_ton_price_mrkt(gift):
    for k in ("salePrice", "salePriceWithoutFee"):
        v = gift.get(k)
        if isinstance(v, (int, float)) and v > 0: return v / 1_000_000_000
    return None

def get_mrkt_payload(collections=None, cursor="", ordering="Price"):
    return {
        "collectionNames": collections or [], "modelNames": [], "backdropNames": [], "symbolNames": [],
        "ordering": ordering, "lowToHigh": True, "maxPrice": None, "minPrice": None,
        "mintable": None, "number": None, "count": 20, "cursor": cursor, "query": None, "promotedFirst": False,
    }

def make_mrkt_headers(token):
    return {"Authorization": str(token), "Referer": "https://cdn.tgmrkt.io/", "Origin": "https://cdn.tgmrkt.io", "Accept": "application/json", "Content-Type": "application/json"}

async def get_mrkt_auth_token():
    global pyro_client, mrkt_http
    try:
        if not pyro_client.is_connected: await pyro_client.connect()
        try:
            peer = await pyro_client.resolve_peer('mrkt')
            bot = InputUser(user_id=peer.user_id, access_hash=peer.access_hash)
            bot_app = InputBotAppShortName(bot_id=bot, short_name="app")
        except Exception: return None
        web_view = await pyro_client.invoke(RequestAppWebView(peer=peer, app=bot_app, platform="android", write_allowed=True))
        init_data = unquote(web_view.url.split('tgWebAppData=', 1)[1].split('&tgWebAppVersion', 1)[0])
        r = await mrkt_http.post("https://api.tgmrkt.io/api/v1/auth", json={"data": init_data}, headers={"Referer": "https://cdn.tgmrkt.io/"})
        if r.status_code == 200:
            token = r.json().get('token')
            if token: return token
    except Exception: pass
    return None

async def mrkt_updater_loop():
    global mrkt_token, mrkt_floor, mrkt_http, active_listings, notified_mrkt_gifts
    while True:
        try:
            if not mrkt_token: mrkt_token = await get_mrkt_auth_token()
            if mrkt_token and mrkt_http:
                headers = make_mrkt_headers(mrkt_token)
                r = await mrkt_http.post('https://api.tgmrkt.io/api/v1/gifts/saling', headers=headers, json=get_mrkt_payload([], cursor="", ordering="Price"))
                if r.status_code in [401, 403]:
                    mrkt_token = None 
                    await asyncio.sleep(10)
                    continue
                if r.status_code == 200:
                    gifts = r.json().get('gifts', [])
                    if gifts:
                        cheapest = gifts[0]
                        ton_price = extract_ton_price_mrkt(cheapest)
                        if ton_price:
                            mrkt_floor['price'] = format_exact_price(ton_price)
                            mrkt_floor['name'] = cheapest.get("title") or cheapest.get("collectionName") or "Unknown"
                            gift_id = cheapest.get("id")
                            mrkt_floor['url_mrkt'] = f"https://t.me/mrkt/app?startapp={gift_id}"
                            gift_num = cheapest.get("number")
                            clean_url_name = mrkt_floor['name'].lower().replace(' ', '').replace('’', '').replace("'", "")
                            mrkt_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}-{gift_num}" if gift_num else f"https://t.me/nft/{clean_url_name}"

                if gift_alert_users:
                    json_recent = get_mrkt_payload([], cursor="", ordering=None)
                    r_rec = await mrkt_http.post('https://api.tgmrkt.io/api/v1/gifts/saling', headers=headers, json=json_recent)
                    if r_rec.status_code == 200:
                        recent_gifts = r_rec.json().get('gifts', [])
                        for g in recent_gifts:
                            g_id = g.get("id")
                            if not g_id or g_id in notified_mrkt_gifts: continue
                            ton_price = extract_ton_price_mrkt(g)
                            if ton_price:
                                gift_name = g.get("title") or g.get("collectionName") or "Unknown"
                                clean_target_name = gift_name.lower().replace(' ', '').replace('’', '').replace("'", "")
                                known_prices = [d['price'] for d in active_listings.values() if d['name'].lower().replace(' ', '').replace('’', '').replace("'", "") == clean_target_name and d['price'] > 0]
                                current_floor = min(known_prices) if known_prices else 0
                                if current_floor > 0 and ton_price <= (current_floor * 0.94):
                                    notified_mrkt_gifts.add(g_id)
                                    if len(notified_mrkt_gifts) > 5000: notified_mrkt_gifts.clear()
                                    asyncio.create_task(trigger_gift_alert(gift_name, current_floor, ton_price, g_id, "MRKT", g.get("number")))
        except Exception: pass
        await asyncio.sleep(15)

def build_keyboard(extra_buttons=None):
    inline_keyboard = []
    for btn_group in extra_buttons or []:
        if isinstance(btn_group, list): inline_keyboard.append(btn_group)
        else: inline_keyboard.append([btn_group])
    if not any(b.get("url") == NEWS_URL for row in inline_keyboard for b in row):
        inline_keyboard.append([NEWS_BTN])
    return {"inline_keyboard": inline_keyboard}

async def tg_api(method, payload=None, form=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    try:
        async with aiohttp.ClientSession() as session:
            if form is not None: req = session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30))
            else: req = session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
            async with req as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"): logging.warning(f"{method} failed: {data.get('description')}")
                return data
    except Exception as e:
        logging.warning(f"{method} error: {e}")
    return {"ok": False}

async def send_custom_msg(chat_id, text, reply_to_message_id=None, extra_buttons=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": build_keyboard(extra_buttons), "disable_web_page_preview": True}
    if reply_to_message_id: payload["reply_parameters"] = {"message_id": reply_to_message_id, "allow_sending_without_reply": True}
    data = await tg_api("sendMessage", payload)
    if not data.get("ok") and extra_buttons and data.get("error_code") == 400:
        # اذا رفض تيليجرام احد الازرار نرسل الرسالة بزر الاخبار فقط حتى ما تضيع
        payload["reply_markup"] = build_keyboard()
        data = await tg_api("sendMessage", payload)
    if data.get("ok"): return data.get("result", {}).get("message_id")
    return None

async def edit_custom_msg(chat_id, message_id, text, extra_buttons=None):
    if not message_id: return await send_custom_msg(chat_id, text, extra_buttons=extra_buttons)
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML", "reply_markup": build_keyboard(extra_buttons), "disable_web_page_preview": True}
    data = await tg_api("editMessageText", payload)
    if not data.get("ok") and extra_buttons and data.get("error_code") == 400 and "not modified" not in str(data.get("description", "")):
        payload["reply_markup"] = build_keyboard()
        await tg_api("editMessageText", payload)
    return message_id

async def send_photo_msg(chat_id, photo_bytes, caption, reply_to_message_id=None, extra_buttons=None):
    def make_form(buttons):
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("caption", caption)
        form.add_field("parse_mode", "HTML")
        form.add_field("reply_markup", json.dumps(build_keyboard(buttons)))
        if reply_to_message_id: form.add_field("reply_parameters", json.dumps({"message_id": reply_to_message_id, "allow_sending_without_reply": True}))
        form.add_field("photo", photo_bytes, filename="chart.png", content_type="image/png")
        return form
    data = await tg_api("sendPhoto", form=make_form(extra_buttons))
    if not data.get("ok") and extra_buttons and data.get("error_code") == 400:
        data = await tg_api("sendPhoto", form=make_form(None))
    return data.get("ok", False)

async def edit_photo_msg(chat_id, message_id, photo_bytes, caption, extra_buttons=None):
    form = aiohttp.FormData()
    form.add_field("chat_id", str(chat_id))
    form.add_field("message_id", str(message_id))
    form.add_field("media", json.dumps({"type": "photo", "media": "attach://chart", "caption": caption, "parse_mode": "HTML"}))
    form.add_field("reply_markup", json.dumps(build_keyboard(extra_buttons)))
    form.add_field("chart", photo_bytes, filename="chart.png", content_type="image/png")
    data = await tg_api("editMessageMedia", form=form)
    return data.get("ok", False)

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
                        clean_url_name = lowest_data['name'].lower().replace(' ', '').replace('’', '').replace("'", "")
                        gift_num = lowest_data.get('num', '')
                        gift_floor['url_tonnel'] = f"https://t.me/tonnel_network_bot/gift?startapp={lowest_gift_id}"
                        if gift_num: gift_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}-{gift_num}"
                        else: gift_floor['url_telegram'] = f"https://t.me/nft/{clean_url_name}"
                except Exception: pass
            else:
                gift_floor['price'] = "0"
                gift_floor['name'] = "لا توجد هدايا معروضة"
            save_market_db()

async def process_event(event, is_live=False):
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
                        # المعرف القديم ما صالح: نبدي من جديد مرة وحدة بس حتى ما تصير حلقة لا نهائية
                        if not last_event_id: break
                        last_event_id = ""
                        await asyncio.sleep(1)
                        continue
                    if resp.status == 200:
                        data = await resp.json()
                        events = data.get('events', [])
                        if not events: break
                        for ev in events: await process_event(ev, is_live=False)
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
                        await process_event(event, is_live=True)
                    except json.JSONDecodeError: pass
        except Exception: 
            await asyncio.sleep(2)

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

async def reset_market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    msg = "اختر السوق الذي تريد عمل تفريغ (Reset) له:"
    btn = [
        [{"text": "مركت (MRKT)", "callback_data": "reset_mrkt", "style": "primary", "icon_custom_emoji_id": MRKT_ICON_ID}],
        [{"text": "تونيل (Tonnel)", "callback_data": "reset_tonnel", "style": "success", "icon_custom_emoji_id": TONNEL_ICON_ID}],
        [{"text": "تفريغ الاثنين", "callback_data": "reset_both", "style": "danger"}],
        CANCEL_BTN
    ]
    await send_custom_msg(update.message.chat_id, msg, extra_buttons=btn)

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
    await edit_custom_msg(chat_id, msg_id, "✅ تم تفريغ السوق وجلب البيانات الجديدة بنجاح.")

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
        elif msg.reply_to_message and msg.reply_to_message.from_user and context.bot.id == msg.reply_to_message.from_user.id: trigger_warning = True
        elif context.bot.username and context.bot.username.lower() in text: trigger_warning = True
        else:
            if any(kw in text for kw in ["الاوامر", "اوامر", "فلور الهدايا", "فلور", "هدايا", "رصيدي", "تغيير محفظتي", "تفعيل التنبيهات", "بحث", "صرف", "سعر", "نبهني", "تحويل", "حاسبه", "حاسبة", "احسب", "مؤشر", "شارت"]): trigger_warning = True

        if trigger_warning:
            warning_msg = 'دروح عمو روح خل واحد من المطورين يفك الحظر منك عود تعال <tg-emoji emoji-id="5872697861166075790">🚫</tg-emoji>'
            btn = [[{"text": "الروسي", "url": "https://t.me/M6M9N", "style": "success", "icon_custom_emoji_id": "5372930329822659547"}], [{"text": "ساسكي", "url": "https://t.me/O1916", "style": "danger", "icon_custom_emoji_id": "5258021357446268553"}]]
            btn.append([dict(NEWS_BTN, style="primary")])
            await send_custom_msg(msg.chat_id, warning_msg, msg.message_id, extra_buttons=btn)
        return True 
    return False

async def process_ban(chat_id, msg_id, target_input, context):
    target_id, target_name = None, html.escape(target_input)
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
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
        target_name = html.escape(update.message.reply_to_message.from_user.first_name)
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
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
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

TON_ADDRESS_RE = re.compile(r'(?<![A-Za-z0-9_-])([EUk0][Qf][A-Za-z0-9_-]{46})(?![A-Za-z0-9_-])')
wallet_cache = {}

def tonapi_headers():
    return {"Authorization": f"Bearer {TONAPI_KEY}"} if TONAPI_KEY else {}

async def tonapi_get(session, path, params=None, retries=3):
    # tonapi بدون مفتاح يسمح طلب بالثانية تقريباً، فنعيد المحاولة اذا رجع 429
    for attempt in range(retries):
        try:
            async with session.get(f"https://tonapi.io{path}", params=params, headers=tonapi_headers(), timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200: return await resp.json()
                if resp.status == 429:
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                return None
        except Exception:
            await asyncio.sleep(0.5)
    return None

def crc16_xmodem(data):
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc

def is_valid_ton_address(addr):
    # نتأكد من الـ checksum حتى ما نرد على اي نص عشوائي طوله 48
    if not addr or not TON_ADDRESS_RE.fullmatch(addr): return False
    try:
        raw = base64.urlsafe_b64decode(addr.replace('+', '-').replace('/', '_'))
        return len(raw) == 36 and crc16_xmodem(raw[:34]) == int.from_bytes(raw[34:], 'big')
    except Exception: return False

def find_ton_address(text):
    for m in TON_ADDRESS_RE.finditer(text or ""):
        if is_valid_ton_address(m.group(1)): return m.group(1)
    return None

def short_addr(addr):
    return f"{addr[:4]}…{addr[-4:]}" if addr and len(addr) > 10 else (addr or "")

def account_label(acc):
    if not isinstance(acc, dict): return ""
    return acc.get("name") or short_addr(acc.get("address", ""))

def parse_transfer_action(action, account_raw, jetton_prices):
    # يحول عملية تحويل من tonapi لشكل بسيط، او None اذا مو تحويل
    a_type = action.get("type")
    if a_type == "TonTransfer":
        d = action.get("TonTransfer", {})
        amount = int(d.get("amount", 0)) / 1e9
        symbol, usd_price = "GRAM", crypto_prices.get('TON', 0)
    elif a_type == "JettonTransfer":
        d = action.get("JettonTransfer", {})
        jetton = d.get("jettons") or d.get("jetton") or {}
        decimals = int(jetton.get("decimals", 9) or 9)
        try: amount = int(d.get("amount", 0)) / (10 ** decimals)
        except Exception: return None
        symbol = jetton.get("symbol") or "JETTON"
        usd_price = 1.0 if symbol in ("USD₮", "USDT") else jetton_prices.get(jetton.get("address"), 0)
    else:
        return None
    sender, recipient = d.get("sender") or {}, d.get("recipient") or {}
    outgoing = sender.get("address") == account_raw
    return {
        "type": a_type, "amount": amount, "symbol": symbol, "usd": amount * usd_price if usd_price else 0,
        "direction": "out" if outgoing else "in",
        "counterparty": recipient if outgoing else sender,
        "comment": d.get("comment") or "",
    }

async def fetch_wallet_summary(address):
    cached = wallet_cache.get(address)
    if cached and time.time() - cached[0] < 30: return cached[1]
    async with aiohttp.ClientSession() as session:
        account = await tonapi_get(session, f"/v2/accounts/{address}")
        if not account: return None
        jettons = await tonapi_get(session, f"/v2/accounts/{address}/jettons", {"currencies": "usd"}) or {}
        nfts = await tonapi_get(session, f"/v2/accounts/{address}/nfts", {"limit": 1000, "indirect_ownership": "false"}) or {}
        events = await tonapi_get(session, f"/v2/accounts/{address}/events", {"limit": 20}) or {}
        if not crypto_prices.get('TON'):
            rate = await fetch_tonapi_ton_rate(session)
            if rate: crypto_prices['TON'] = rate

    ton_price = crypto_prices.get('TON', 0)
    balance_ton = int(account.get("balance", 0)) / 1e9
    usdt, jetton_list, jetton_prices, jettons_usd = 0.0, [], {}, 0.0
    for b in jettons.get("balances", []):
        j = b.get("jetton", {})
        try: amount = int(b.get("balance", 0)) / (10 ** int(j.get("decimals", 9) or 9))
        except Exception: continue
        if amount <= 0 or j.get("verification") == "blacklist": continue
        price = float(((b.get("price") or {}).get("prices") or {}).get("USD", 0) or 0)
        jetton_prices[j.get("address")] = price
        if j.get("symbol") in ("USD₮", "USDT"):
            usdt = amount
            continue
        jettons_usd += amount * price
        jetton_list.append({"symbol": j.get("symbol", "?"), "name": j.get("name", ""), "amount": amount, "usd": amount * price, "image": j.get("image", "")})
    jetton_list.sort(key=lambda x: x["usd"], reverse=True)

    account_raw = account.get("address", "")
    last_transfer = None
    for ev in events.get("events", []):
        if ev.get("is_scam"): continue
        for action in ev.get("actions", []):
            parsed = parse_transfer_action(action, account_raw, jetton_prices)
            if parsed:
                parsed["timestamp"] = ev.get("timestamp", 0)
                last_transfer = parsed
                break
        if last_transfer: break

    nft_items = nfts.get("nft_items", [])
    summary = {
        "address": address, "raw": account_raw, "name": account.get("name") or "",
        "status": account.get("status", ""), "interfaces": account.get("interfaces") or [],
        "is_wallet": account.get("is_wallet", False), "last_activity": account.get("last_activity", 0),
        "balance_ton": balance_ton, "ton_price": ton_price, "balance_usd": balance_ton * ton_price,
        "usdt": usdt, "jettons": jetton_list, "jettons_usd": jettons_usd,
        "nft_count": len(nft_items), "nft_more": len(nft_items) >= 1000,
        "last_transfer": last_transfer,
    }
    summary["total_usd"] = summary["balance_usd"] + usdt + jettons_usd
    wallet_cache[address] = (time.time(), summary)
    if len(wallet_cache) > 500: wallet_cache.clear()
    return summary

def format_time_ago(ts):
    if not ts: return "غير معروف"
    diff = max(0, int(time.time() - ts))
    if diff < 60: ago = "الآن"
    elif diff < 3600: ago = f"منذ {diff // 60} دقيقة"
    elif diff < 86400: ago = f"منذ {diff // 3600} ساعة"
    else: ago = f"منذ {diff // 86400} يوم"
    return f"{datetime.fromtimestamp(ts, IRAQ_TZ).strftime('%Y-%m-%d %H:%M')} ({ago})"

def get_webapp_base():
    url = os.environ.get("WEBAPP_URL", "")
    if not url and os.environ.get("SPACE_HOST"): url = f"https://{os.environ['SPACE_HOST']}"
    if not url and os.environ.get("KOYEB_PUBLIC_DOMAIN"): url = f"https://{os.environ['KOYEB_PUBLIC_DOMAIN']}"
    if not url: url = os.environ.get("RENDER_EXTERNAL_URL", "")
    url = url.strip()
    if url.endswith("/app"): url = url[:-4]
    return url.rstrip('/') if url.startswith("https://") else ""

def wallet_activity_button(address, chat_type, bot_username):
    # web_app يشتغل بس بالخاص، بالكروبات نستخدم رابط الميني اب المباشر او رابط الصفحة
    base = get_webapp_base()
    btn = {"text": "عرض أنشطته", "style": "success", "icon_custom_emoji_id": "5231200819986047254"}
    if base and chat_type == "private":
        btn["web_app"] = {"url": f"{base}/app?address={address}"}
    elif MINIAPP_SHORT_NAME and bot_username:
        btn["url"] = f"https://t.me/{bot_username}/{MINIAPP_SHORT_NAME}?startapp={address}"
    elif base:
        btn["url"] = f"{base}/app?address={address}"
    else:
        btn["url"] = f"https://tonviewer.com/{address}"
    return btn

def build_wallet_message(s):
    lines = [f"{SEARCH_EMOJI} <b>معلومات المحفظة</b>", f"<code>{s['address']}</code>"]
    if s["name"]: lines.append(f"🏷 الاسم: <b>{html.escape(s['name'])}</b>")
    lines.append("")
    lines.append(f"{GRAM_EMOJI} الرصيد: <b>{s['balance_ton']:,.2f}</b> GRAM" + (f" (≈ ${s['balance_usd']:,.2f})" if s['ton_price'] else ""))
    lines.append(f"{USDT_CASH} USDT: <b>{s['usdt']:,.2f}</b>")
    if s["jettons"]:
        lines.append(f"🪙 عملات أخرى: <b>{len(s['jettons'])}</b>" + (f" (≈ ${s['jettons_usd']:,.2f})" if s['jettons_usd'] >= 0.01 else ""))
    nft_txt = f"{s['nft_count']:,}+" if s["nft_more"] else f"{s['nft_count']:,}"
    lines.append(f"{GIFT_FLOOR_EMOJI} المقتنيات (NFT): <b>{nft_txt}</b>")
    if s["total_usd"] >= 0.01: lines.append(f"💰 القيمة الكلية: <b>${s['total_usd']:,.2f}</b>")
    lines.append("╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼")
    t = s["last_transfer"]
    if t:
        is_out = t["direction"] == "out"
        dir_txt = f"إرسال {DOWN_EMOJI}" if is_out else f"استلام {UP_EMOJI}"
        amount_txt = f"{t['amount']:,.4f}".rstrip('0').rstrip('.') if t['amount'] < 1 else f"{t['amount']:,.2f}"
        lines.append(f"📤 آخر تحويل: <b>{dir_txt}</b>")
        lines.append(f"💸 القيمة: <b>{amount_txt} {html.escape(t['symbol'])}</b>" + (f" (≈ ${t['usd']:,.2f})" if t['usd'] >= 0.01 else ""))
        other = account_label(t["counterparty"])
        if other: lines.append(f"👤 {'إلى' if is_out else 'من'}: <code>{html.escape(other)}</code>")
        lines.append(f"🕒 الوقت: {format_time_ago(t['timestamp'])}")
    else:
        lines.append("📤 آخر تحويل: لا توجد تحويلات")
    lines.append("╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼")
    status = "نشطة ✅" if s["status"] == "active" else ("غير مفعلة" if s["status"] in ("uninit", "nonexist") else html.escape(s["status"] or "-"))
    lines.append(f"📌 الحالة: {status}")
    if s["last_activity"]: lines.append(f"⏱ آخر نشاط: {format_time_ago(s['last_activity'])}")
    return "\n".join(lines)

async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE, address):
    chat_id, msg_id = update.message.chat_id, update.message.message_id
    wait_id = await send_custom_msg(chat_id, f"جاري فحص المحفظة... {SEARCH_EMOJI}", msg_id)
    summary = await fetch_wallet_summary(address)
    if not summary:
        await edit_custom_msg(chat_id, wait_id, f"عذراً، ما كدرت أجيب معلومات هذا العنوان حالياً. {WARN_EMOJI}")
        return
    btn = [[wallet_activity_button(address, update.message.chat.type, context.bot.username)],
           [{"text": "Tonviewer", "url": f"https://tonviewer.com/{address}", "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}]]
    await edit_custom_msg(chat_id, wait_id, build_wallet_message(summary), extra_buttons=btn)

async def fetch_wallet_events(address, before_lt=None):
    params = {"limit": 25}
    if before_lt: params["before_lt"] = before_lt
    async with aiohttp.ClientSession() as session:
        account = await tonapi_get(session, f"/v2/accounts/{address}")
        data = await tonapi_get(session, f"/v2/accounts/{address}/events", params)
    if data is None: return None
    account_raw = (account or {}).get("address", "")
    events = []
    for ev in data.get("events", []):
        actions = []
        for action in ev.get("actions", []):
            preview = action.get("simple_preview") or {}
            item = {"type": action.get("type", ""), "status": action.get("status", ""),
                    "title": preview.get("name", ""), "description": preview.get("description", ""), "value": preview.get("value", "")}
            transfer = parse_transfer_action(action, account_raw, {})
            if transfer:
                cp = transfer["counterparty"] or {}
                item.update({"direction": transfer["direction"], "amount": transfer["amount"], "symbol": transfer["symbol"],
                             "usd": transfer["usd"], "comment": transfer["comment"],
                             "counterparty": cp.get("address", ""), "counterparty_name": cp.get("name", "")})
            elif action.get("type") == "NftItemTransfer":
                d = action.get("NftItemTransfer", {})
                item["direction"] = "out" if (d.get("sender") or {}).get("address") == account_raw else "in"
            actions.append(item)
        events.append({"id": ev.get("event_id"), "ts": ev.get("timestamp", 0), "lt": ev.get("lt"),
                       "scam": ev.get("is_scam", False), "in_progress": ev.get("in_progress", False), "actions": actions})
    return {"events": events, "next_from": data.get("next_from") or 0}

def pick_nft_image(item):
    previews = item.get("previews") or []
    for res in ("500x500", "100x100", "1500x1500"):
        for p in previews:
            if p.get("resolution") == res and str(p.get("url", "")).startswith("https://"): return p["url"]
    img = (item.get("metadata") or {}).get("image", "")
    return img if str(img).startswith("https://") else ""

async def fetch_wallet_nfts(address, offset=0):
    async with aiohttp.ClientSession() as session:
        data = await tonapi_get(session, f"/v2/accounts/{address}/nfts", {"limit": 48, "offset": offset, "indirect_ownership": "false"})
    if data is None: return None
    items = []
    for it in data.get("nft_items", []):
        meta = it.get("metadata") or {}
        items.append({"address": it.get("address", ""), "name": meta.get("name") or "NFT",
                      "collection": (it.get("collection") or {}).get("name", ""), "image": pick_nft_image(it),
                      "verified": it.get("trust") == "whitelist" or bool(it.get("approved_by"))})
    return {"items": items, "has_more": len(items) >= 48}

async def check_ton_wallet(address):
    if not address or not re.fullmatch(r'[A-Za-z0-9_:.\-]{3,100}', address): return False, 0, 0
    try:
        async with aiohttp.ClientSession() as session:
            data = await tonapi_get(session, f"/v2/accounts/{address}")
            if not data: return False, 0, 0
            ton_balance = int(data.get('balance', 0)) / 1e9
            usdt_balance = 0
            j_data = await tonapi_get(session, f"/v2/accounts/{address}/jettons") or {}
            for b in j_data.get('balances', []):
                if b.get('jetton', {}).get('symbol') in ['USD₮', 'USDT']:
                    usdt_balance = float(b['balance']) / (10 ** int(b['jetton'].get('decimals', 6)))
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

GRAM_WORDS = ['جرام', 'غرام', 'كرام', 'قرام', 'gram', 'تون', 'ton']

def normalize_currency(curr_str):
    curr = curr_str.lower().strip()
    if curr in ['دولار', 'usdt', 'usd', '$']: return 'USD'
    elif curr in ['ماستر', 'master']: return 'IQD'
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: return 'STARS'
    elif curr in GRAM_WORDS: return 'TON' 
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

BINANCE_HOSTS = ["https://api.binance.com", "https://data-api.binance.vision"]
BINANCE_SYMBOLS = {'TON': ["GRAMUSDT", "TONUSDT"], 'BTC': ["BTCUSDT"], 'BATH': ["BATHUSDT"]}

async def fetch_binance_ticker(session, symbols, timeout=5):
    # يرجع (السعر, نسبة التغير 24 ساعة) من اول رمز واول سيرفر يشتغل
    for symbol in symbols:
        for host in BINANCE_HOSTS:
            try:
                async with session.get(f"{host}/api/v3/ticker/24hr", params={"symbol": symbol}, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        d = await resp.json()
                        price = float(d['lastPrice'])
                        if price > 0: return price, float(d['priceChangePercent'])
                    elif resp.status == 400: break
            except Exception: continue
    return None

async def fetch_tonapi_ton_rate(session):
    data = await tonapi_get(session, "/v2/rates", {"tokens": "ton", "currencies": "usd"}, retries=1)
    try: return float(data["rates"]["TON"]["prices"]["USD"])
    except Exception: return None

def load_price_history():
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict): return data
    except Exception: pass
    return {}

price_history = load_price_history()

def record_price_history(code, value, min_gap=300):
    # نحفظ نقطة كل 5 دقايق على الاقل ونخلي اخر 30 يوم بس
    now = time.time()
    points = price_history.setdefault(code, [])
    if points and now - points[-1][0] < min_gap: return
    points.append([int(now), value])
    cutoff = now - 31 * 86400
    while points and points[0][0] < cutoff: points.pop(0)
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: json.dump(price_history, f)
    except Exception: pass

async def fetch_mastercard_price(session):
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {"Content-Type": "application/json"}
        payload = {"fiat": "IQD", "page": 1, "rows": 5, "tradeType": "SELL", "asset": "USDT", "countries": [], "payTypes": ["ZainCash"], "publisherType": None, "merchantCheck": False}
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data'):
                    for ad in data['data']:
                        price_float = float(ad['adv']['price'])
                        if 1400 <= price_float <= 1650:
                            return int(price_float * 100)
    except Exception: pass
    return None

async def update_prices_if_needed():
    global last_fetch_time, cached_msg, last_known_iqd, crypto_prices, crypto_24h_trend, daily_iqd
    current_time = time.time()
    if current_time - last_fetch_time < CACHE_TIME and cached_msg: return True
    try:
        async with aiohttp.ClientSession() as session:
            btc_t, ton_t, bath_t, fetched_iqd = await asyncio.gather(
                fetch_binance_ticker(session, BINANCE_SYMBOLS['BTC']),
                fetch_binance_ticker(session, BINANCE_SYMBOLS['TON']),
                fetch_binance_ticker(session, BINANCE_SYMBOLS['BATH'], timeout=3),
                fetch_mastercard_price(session), return_exceptions=True)
            for code, ticker in (('BTC', btc_t), ('TON', ton_t), ('BATH', bath_t)):
                if isinstance(ticker, tuple):
                    crypto_prices[code], crypto_24h_trend[code] = ticker
            if not crypto_prices.get('TON'):
                ton_rate = await fetch_tonapi_ton_rate(session)
                if ton_rate: crypto_prices['TON'] = ton_rate
            if not crypto_prices.get('BATH'): crypto_prices['BATH'] = 0.03

            if isinstance(fetched_iqd, int) and fetched_iqd > 0:
                last_known_iqd = fetched_iqd
                record_price_history('IQD', last_known_iqd)
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
    if curr in ['دولار', 'usdt', 'usd', '$']: base, name, usd_val, show_usd = 'USD', "دولار (USDT)", amount, False  
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
    elif curr in GRAM_WORDS: base, name, usd_val = 'TON', "جرام (GRAM)", amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: base, name, usd_val = 'BTC', "بتكوين (BTC)", amount * crypto_prices.get('BTC', 0)
    else: return f"عذراً، العملة غير مدعومة. {WARN_EMOJI}"

    if usd_val == 0: return f"عذراً، لا يمكن حساب القيمة الآن. {WARN_EMOJI}"

    iqd_val = (usd_val * last_known_iqd) / 100
    asia_val = iqd_val / 0.9 
    ton_val = usd_val / crypto_prices['TON'] if crypto_prices.get('TON') else 0
    bath_val = usd_val / crypto_prices.get('BATH', 0.03)
    stars_val = usd_val / 0.015 
    btc_val = usd_val / crypto_prices['BTC'] if crypto_prices.get('BTC') else 0

    msg = f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <b>تصريف {format_large_amount(amount)} {name}:</b>\n\n'
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

CHART_TIMEFRAMES = {
    "1d": {"interval": "30m", "limit": 48, "seconds": 86400, "ar": "24 ساعة", "en": "24H"},
    "7d": {"interval": "4h", "limit": 42, "seconds": 7 * 86400, "ar": "7 أيام", "en": "7D"},
    "30d": {"interval": "1d", "limit": 30, "seconds": 30 * 86400, "ar": "30 يوم", "en": "30D"},
}
CHART_ASSETS = {
    'TON': {"en": "GRAM / USDT", "ar": "الجرام", "emoji": GRAM_EMOJI},
    'BTC': {"en": "BTC / USDT", "ar": "البتكوين", "emoji": '<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji>'},
    'BATH': {"en": "BATH / USDT", "ar": "الباث", "emoji": BATH_EMOJI},
    'IQD': {"en": "MASTER  ·  100 USD / IQD", "ar": "الماستر (100$)", "emoji": MASTER_EMOJI},
    'ASIA': {"en": "ASIA  ·  100 USD / IQD", "ar": "اسيا (100$)", "emoji": ASIA_EMOJI},
}
CHART_TRIGGER_RE = re.compile(r'^/?(?:ال)?(?:مؤشر|موشر|شارت|چارت|جارت|chart)(?:\s+(?:ال)?(.+))?$')
CHART_WORDS = {w: 'TON' for w in GRAM_WORDS + ['الجرام', 'التون']}
CHART_WORDS.update({w: 'BTC' for w in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin', 'البتكوين']})
CHART_WORDS.update({w: 'BATH' for w in ['باث', 'bath']})
chart_cache = {}
chart_lock = threading.Lock()

async def fetch_binance_klines(session, symbols, interval, limit):
    for symbol in symbols:
        for host in BINANCE_HOSTS:
            try:
                async with session.get(f"{host}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        rows = await resp.json()
                        candles = [(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]
                        if len(candles) >= 2: return candles
                    elif resp.status == 400: break
            except Exception: continue
    return None

async def get_chart_series(code, tf):
    frame = CHART_TIMEFRAMES[tf]
    if code in BINANCE_SYMBOLS:
        async with aiohttp.ClientSession() as session:
            candles = await fetch_binance_klines(session, BINANCE_SYMBOLS[code], frame["interval"], frame["limit"])
            if candles: return {"kind": "candle", "data": candles}
            if code == 'TON':
                # بديل اذا بايننس ما اشتغل: شارت tonapi
                end = int(time.time())
                data = await tonapi_get(session, "/v2/rates/chart", {"token": "ton", "currency": "usd", "start_date": end - frame["seconds"], "end_date": end, "points_count": 96})
                points = sorted((int(p[0]), float(p[1])) for p in (data or {}).get("points", []) if len(p) >= 2)
                if len(points) >= 2: return {"kind": "line", "data": points}
        return None
    if code in ('IQD', 'ASIA'):
        cutoff = time.time() - frame["seconds"]
        points = [(int(t), float(v)) for t, v in price_history.get('IQD', []) if t >= cutoff]
        if len(points) < 2 or points[-1][0] - points[0][0] < 3600: return None
        if code == 'ASIA': points = [(t, v / 0.9) for t, v in points]
        return {"kind": "line", "data": points}
    return None

def format_chart_price(code, value):
    if code in ('IQD', 'ASIA'): return f"{value:,.0f}"
    if code == 'BTC': return f"{value:,.0f}"
    if value >= 1: return f"{value:,.3f}"
    return f"{value:,.5f}"

def render_chart_png(code, tf, series, watermark=""):
    import io
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import FuncFormatter, MaxNLocator

    bg, panel, grid, text, muted = "#0b0f17", "#111827", "#1f2937", "#f3f4f6", "#9ca3af"
    up_c, down_c = "#22c55e", "#ef4444"
    data = series["data"]
    times = [d[0] for d in data]
    if series["kind"] == "candle":
        first, last = data[0][1], data[-1][4]
        high, low = max(d[2] for d in data), min(d[3] for d in data)
    else:
        first, last = data[0][1], data[-1][1]
        high, low = max(d[1] for d in data), min(d[1] for d in data)
    change = ((last - first) / first * 100) if first else 0
    main_c = up_c if change >= 0 else down_c

    fig = Figure(figsize=(10, 5.6), dpi=110, facecolor=bg)
    ax = fig.add_axes([0.04, 0.12, 0.84, 0.62], facecolor=panel)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.grid(True, color=grid, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=muted, labelsize=9, length=0)
    ax.yaxis.tick_right()
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: format_chart_price(code, v)))

    xs = list(range(len(data)))
    if series["kind"] == "candle":
        for x, (_, o, h, l, c) in zip(xs, data):
            col = up_c if c >= o else down_c
            ax.vlines(x, l, h, color=col, linewidth=1.1, zorder=2)
            body_low, body_h = min(o, c), max(abs(c - o), (high - low) * 0.002)
            ax.add_patch(Rectangle((x - 0.32, body_low), 0.64, body_h, facecolor=col, edgecolor=col, zorder=3))
        ax.set_xlim(-1, len(data) + 0.5)
    else:
        ys = [d[1] for d in data]
        ax.plot(xs, ys, color=main_c, linewidth=2.2, zorder=3)
        ax.fill_between(xs, ys, min(ys) - (high - low) * 0.08, color=main_c, alpha=0.12, zorder=2)
        ax.set_xlim(-0.5, len(data) - 0.5)
    pad = (high - low) * 0.12 or abs(last) * 0.01 or 1
    ax.set_ylim(low - pad, high + pad)

    # خط السعر الحالي مع علامة
    ax.axhline(last, color=main_c, linestyle=(0, (4, 4)), linewidth=1, alpha=0.8, zorder=1)
    ax.annotate(format_chart_price(code, last), xy=(1, last), xycoords=("axes fraction", "data"), xytext=(4, 0), textcoords="offset points",
                va="center", ha="left", fontsize=9, fontweight="bold", color="white",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=main_c, edgecolor="none"), annotation_clip=False, zorder=5)

    fmt = "%H:%M" if tf == "1d" else "%d/%m"
    step = max(1, len(data) // 6)
    ticks = xs[::step]
    ax.set_xticks(ticks)
    ax.set_xticklabels([datetime.fromtimestamp(times[i], IRAQ_TZ).strftime(fmt) for i in ticks])

    asset, frame = CHART_ASSETS[code], CHART_TIMEFRAMES[tf]
    prefix = "" if code in ('IQD', 'ASIA') else "$"
    arrow = "▲" if change >= 0 else "▼"
    fig.text(0.04, 0.9, asset["en"], color=muted, fontsize=13, fontweight="bold")
    price_txt = fig.text(0.04, 0.8, f"{prefix}{format_chart_price(code, last)}", color=text, fontsize=26, fontweight="bold")
    # نحط نسبة التغير بعد السعر مباشرة مهما كان طوله
    price_end = price_txt.get_window_extent(FigureCanvasAgg(fig).get_renderer()).x1 / fig.bbox.width
    fig.text(price_end + 0.025, 0.815, f" {arrow} {change:+.2f}% ", color="white", fontsize=12, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.35", facecolor=main_c, edgecolor="none"))
    fig.text(0.88, 0.9, frame["en"], color=text, fontsize=13, fontweight="bold", ha="right",
             bbox=dict(boxstyle="round,pad=0.35", facecolor=grid, edgecolor="none"))
    fig.text(0.88, 0.81, f"H  {prefix}{format_chart_price(code, high)}", color=up_c, fontsize=10, ha="right")
    fig.text(0.88, 0.765, f"L  {prefix}{format_chart_price(code, low)}", color=down_c, fontsize=10, ha="right")
    if watermark:
        fig.text(0.46, 0.43, watermark, color="white", alpha=0.05, fontsize=34, fontweight="bold", ha="center", va="center")
    fig.text(0.04, 0.035, datetime.now(IRAQ_TZ).strftime("Updated %Y-%m-%d %H:%M (Baghdad)"), color=muted, fontsize=8)

    buf = io.BytesIO()
    with chart_lock:
        fig.savefig(buf, format="png", facecolor=bg)
    return buf.getvalue(), {"last": last, "high": high, "low": low, "change": change}

def build_chart_caption(code, tf, stats):
    asset, frame = CHART_ASSETS[code], CHART_TIMEFRAMES[tf]
    unit = " IQD" if code in ('IQD', 'ASIA') else ""
    prefix = "" if code in ('IQD', 'ASIA') else "$"
    trend = UP_EMOJI if stats["change"] > 0 else (DOWN_EMOJI if stats["change"] < 0 else "")
    state = "صعود" if stats["change"] > 0 else ("نزول" if stats["change"] < 0 else "ثابت")
    return (f"{asset['emoji']} <b>مؤشر {asset['ar']}</b> — {frame['ar']}\n\n"
            f"💵 السعر الحالي: <b>{prefix}{format_chart_price(code, stats['last'])}{unit}</b>\n"
            f"📊 الحركة: <b>{state} {stats['change']:+.2f}%</b> {trend}\n"
            f"🔺 أعلى: <b>{prefix}{format_chart_price(code, stats['high'])}</b>   🔻 أدنى: <b>{prefix}{format_chart_price(code, stats['low'])}</b>\n\n"
            f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>')

def chart_buttons(code, tf):
    row = [{"text": CHART_TIMEFRAMES[k]["ar"], "callback_data": f"chart|{code}|{k}", "style": "success" if k == tf else "primary"} for k in CHART_TIMEFRAMES]
    return [row]

async def make_chart(code, tf, watermark=""):
    cached = chart_cache.get((code, tf))
    if cached and time.time() - cached[0] < 60: return cached[1], cached[2]
    series = await get_chart_series(code, tf)
    if not series: return None, None
    png, stats = await asyncio.to_thread(render_chart_png, code, tf, series, watermark)
    caption = build_chart_caption(code, tf, stats)
    chart_cache[(code, tf)] = (time.time(), png, caption)
    return png, caption

async def send_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, code, tf="1d"):
    chat_id, msg_id = update.message.chat_id, update.message.message_id
    try:
        png, caption = await make_chart(code, tf, f"@{context.bot.username}" if context.bot.username else "")
    except Exception as e:
        logging.warning(f"chart error {code}: {e}")
        png, caption = None, None
    if png and await send_photo_msg(chat_id, png, caption, msg_id, extra_buttons=chart_buttons(code, tf)):
        return
    # اذا المؤشر ما متوفر نرجع رسالة السعر العادية حتى المستخدم ياخذ جواب دائماً
    await update_prices_if_needed()
    await send_custom_msg(chat_id, cached_msg if cached_msg else f"عذراً، حاول ثواني.. {WAIT_EMOJI}", msg_id)

async def chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id in banned_users:
        await query.answer("انت محظور من البوت 🚫", show_alert=True)
        return
    try: _, code, tf = query.data.split("|")
    except ValueError:
        await query.answer()
        return
    if code not in CHART_ASSETS or tf not in CHART_TIMEFRAMES:
        await query.answer()
        return
    await query.answer(f"جاري تحميل مؤشر {CHART_TIMEFRAMES[tf]['ar']}... ⏳")
    try:
        png, caption = await make_chart(code, tf, f"@{context.bot.username}" if context.bot.username else "")
    except Exception as e:
        logging.warning(f"chart error {code}: {e}")
        png = None
    if not png:
        await query.answer("المؤشر غير متوفر حالياً، حاول بعد شوية", show_alert=True)
        return
    await edit_photo_msg(query.message.chat.id, query.message.message_id, png, caption, extra_buttons=chart_buttons(code, tf))

def detect_chart_request(text):
    if text in CHART_WORDS: return CHART_WORDS[text]
    m = CHART_TRIGGER_RE.match(text)
    if m:
        target = (m.group(1) or "").strip()
        code = CHART_WORDS.get(target) or CHART_WORDS.get("ال" + target) or normalize_currency(target)
        return code if code in CHART_ASSETS else 'TON'
    return None

async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    msg = f"{WHALE_BELL} <b>نظام التنبيهات الذكي</b>\n\nاختر نوع التنبيه الذي تريده:"
    btn = [
        [{"text": "نبهني عملات (الأسعار)", "callback_data": "alert_currency_start", "style": "primary", "icon_custom_emoji_id": "5292058354791756351"}],
        [{"text": "نبهني هدايا (صيد الرخيص)", "callback_data": "alert_gifts_toggle", "style": "success", "icon_custom_emoji_id": "5255980157058975232"}],
        CANCEL_BTN
    ]
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=btn)
    return ASK_ALERT_TYPE

async def alert_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "alert_currency_start":
        await edit_custom_msg(query.message.chat.id, query.message.message_id, "اكتب اسم العملة اللي تريد أراقبها (مثال: جرام، بتكوين، باث، ماستر...):", extra_buttons=[CANCEL_BTN])
        return ASK_CURRENCY_NAME
    elif data == "alert_gifts_toggle":
        user_id = query.from_user.id
        if user_id in gift_alert_users:
            msg = f"أنت مفعل تنبيهات صيد الهدايا بالفعل! 🎯\nهل تريد إيقافها؟"
            btn = [[{"text": "إيقاف صيد الهدايا", "callback_data": "stop_gift_alerts", "style": "danger", "icon_custom_emoji_id": "5215204871422093648"}], CANCEL_BTN]
            await edit_custom_msg(query.message.chat.id, query.message.message_id, msg, extra_buttons=btn)
            return ASK_ALERT_TYPE
        else:
            gift_alert_users[user_id] = {"name": html.escape(query.from_user.first_name), "chat_id": query.message.chat.id}
            await edit_custom_msg(query.message.chat.id, query.message.message_id, f"✅ <b>تم تسجيلك في صيد الهدايا!</b>\n\nسيقوم البوت بمراقبة سوق (مركت) وإشعارك فور نزول هدية أرخص من الفلور بنسبة 6% أو أكثر.")
        return ConversationHandler.END
    elif data == "stop_gift_alerts":
        user_id = query.from_user.id
        if user_id in gift_alert_users: del gift_alert_users[user_id]
        await edit_custom_msg(query.message.chat.id, query.message.message_id, f"تم إلغاء تفعيل تنبيهات صيد الهدايا بنجاح {SUCCESS_EMOJI}")
        return ConversationHandler.END

async def alert_currency_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    curr_input = html.escape(update.message.text.strip())
    curr_code = normalize_currency(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, f"عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_CURRENCY_NAME
    context.user_data['alert_curr'] = curr_code
    context.user_data['alert_curr_name'] = curr_input
    await send_custom_msg(update.message.chat_id, f"{SUCCESS_EMOJI} تم اختيار: <b>{curr_input}</b>\n\nالآن ادخل السعر الذي تريد التنبيه عنده (أرقام فقط):", update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_CURRENCY_PRICE

async def alert_currency_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    price_input = update.message.text.strip()
    match = re.search(r'(\d+(?:\.\d+)?)', price_input)
    if not match:
        await send_custom_msg(update.message.chat_id, f"يرجى إدخال رقم صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_CURRENCY_PRICE
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
    global alerts_db, gift_alert_users
    user_id = update.message.from_user.id
    initial_len = len(alerts_db)
    alerts_db = [a for a in alerts_db if a['user_id'] != user_id]
    removed_sniper = False
    if user_id in gift_alert_users:
        del gift_alert_users[user_id]
        removed_sniper = True
    if len(alerts_db) < initial_len or removed_sniper:
        msg = f"تم إيقاف جميع تنبيهات الأسعار وصيد الهدايا بنجاح. {SUCCESS_EMOJI}"
    else:
        msg = f"ليس لديك أي تنبيهات مفعلة. {WARN_EMOJI}"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return
    user_id = update.message.from_user.id
    user_alerts = [a for a in alerts_db if a['user_id'] == user_id and a['active']]
    is_gift_sniper = user_id in gift_alert_users
    if not user_alerts and not is_gift_sniper:
        await send_custom_msg(update.message.chat_id, f"لا توجد لديك أي تنبيهات مفعلة حالياً. {WARN_EMOJI}", update.message.message_id)
        return
    msg = f"{WHALE_BELL} <b>تنبيهاتك الحالية:</b>\n\n"
    if is_gift_sniper:
        msg += f"🎯 <b>صيد الهدايا:</b> مفعل (يراقب نزول الأسعار في مركت)\n\n"
    if user_alerts:
        msg += f"📊 <b>العملات:</b>\n"
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
               "البوت سيقوم بمراقبة شبكة عملة الجرام (TON)، وعند حدوث عملية تحويل ضخمة جداً (أكثر من 8000 جرام)، سيصلك إشعار فوري.")
        await send_custom_msg(chat_id, msg, update.message.message_id)

async def check_whales_loop(app: Application):
    last_tx_hash = ""
    wallet = "EQBX63RAdgShnrJGptNINn2uUFIqEQ9_hD0z4E7h-gH-Zk5t"
    while True:
        await asyncio.sleep(20)
        if not whale_alert_users: continue
        try:
            async with aiohttp.ClientSession() as session:
                data = await tonapi_get(session, f"/v2/accounts/{wallet}/events", {"limit": 10})
            events = (data or {}).get('events', [])
            if not events: continue
            new_latest_hash = events[0].get('event_id')
            if last_tx_hash == "":
                last_tx_hash = new_latest_hash
                continue
            for event in events:
                if event.get('event_id') == last_tx_hash: break
                for action in event.get('actions', []):
                    if action.get('type') != 'TonTransfer': continue
                    amount = float(action.get('TonTransfer', {}).get('amount', 0)) / 1e9
                    if amount < 8000: continue
                    grouped_by_chat = {}
                    for uid, udata in list(whale_alert_users.items()):
                        grouped_by_chat.setdefault(udata['chat_id'], []).append({'id': uid, 'name': udata['name']})
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

async def calc_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    msg = f"<tg-emoji emoji-id='5231200819986047254'>📊</tg-emoji> <b>حاسبة الأرباح والخسائر الذكية</b>\n\nأرسل اسم العملة التي اشتريتها (مثال: جرام، بتكوين، باث، ماستر...):"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_CALC_CURRENCY

async def calc_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    curr_input = html.escape(update.message.text.strip())
    curr_code = normalize_currency(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, f"عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_CALC_CURRENCY
    context.user_data['calc_curr'] = curr_code
    context.user_data['calc_curr_name'] = curr_input
    msg = f"{SUCCESS_EMOJI} تم اختيار: <b>{curr_input}</b>\n\nالآن أرسل <b>سعر الشراء</b> (السعر الذي اشتريت به القطعة الواحدة):"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=[CANCEL_BTN])
    return ASK_CALC_PRICE

async def calc_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if await is_user_banned(update, context): return ConversationHandler.END
        price_input = update.message.text.strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*(الف|مليون|بليون|مليار|ترليون|كوادرليون)?', price_input)
        if not match:
            await send_custom_msg(update.message.chat_id, f"يرجى إدخال رقم صحيح: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
            return ASK_CALC_PRICE
        purchase_price = float(match.group(1))
        if match.group(2):
            multiplier_map = {'الف': 1e3, 'مليون': 1e6, 'بليون': 1e9, 'مليار': 1e9, 'ترليون': 1e12, 'كوادرليون': 1e15}
            purchase_price *= multiplier_map[match.group(2)]
        context.user_data['calc_price'] = purchase_price
        msg = f"{SUCCESS_EMOJI} سعر الشراء: <b>{format_large_amount(purchase_price)}</b>\n\nأخيراً، أرسل <b>الكمية</b> (كم قطعة اشتريت؟):"
        await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=[CANCEL_BTN])
        return ASK_CALC_AMOUNT
    except: return ASK_CALC_PRICE

async def calc_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if await is_user_banned(update, context): return ConversationHandler.END
        curr_code = context.user_data.get('calc_curr')
        curr_name = context.user_data.get('calc_curr_name', 'العملة')
        purchase_price = context.user_data.get('calc_price')
        if not curr_code or purchase_price is None:
            await send_custom_msg(update.message.chat_id, "⚠️ انتهت الجلسة أو حدث خطأ، يرجى إعادة المحاولة من جديد بكتابة 'حاسبه'", update.message.message_id)
            return ConversationHandler.END
        amount_input = update.message.text.strip()
        match = re.search(r'(\d+(?:\.\d+)?)\s*(الف|مليون|بليون|مليار|ترليون|كوادرليون)?', amount_input)
        if not match:
            await send_custom_msg(update.message.chat_id, f"يرجى إدخال كمية صحيحة أرقام فقط: {WARN_EMOJI}", update.message.message_id, extra_buttons=[CANCEL_BTN])
            return ASK_CALC_AMOUNT
        amount = float(match.group(1))
        if match.group(2):
            multiplier_map = {'الف': 1e3, 'مليون': 1e6, 'بليون': 1e9, 'مليار': 1e9, 'ترليون': 1e12, 'كوادرليون': 1e15}
            amount *= multiplier_map[match.group(2)]
        await update_prices_if_needed()
        current_price = get_current_price(curr_code)
        if current_price == 0:
            await send_custom_msg(update.message.chat_id, f"عذراً، لا يمكن جلب السعر الحالي للعملة الآن، حاول لاحقاً. {WARN_EMOJI}", update.message.message_id)
            return ConversationHandler.END
        total_invested = purchase_price * amount
        current_total = current_price * amount
        profit_loss = current_total - total_invested
        profit_loss_percent = (abs(profit_loss) / total_invested) * 100 if total_invested > 0 else 0
        if profit_loss > 0:
            status_emoji, status_text, sign = UP_EMOJI, "ربح", "+"
        elif profit_loss < 0:
            status_emoji, status_text, sign = DOWN_EMOJI, "خسارة", "-"
        else:
            status_emoji, status_text, sign = "➖", "رأس برأس (لا ربح ولا خسارة)", ""
        msg = (f"<tg-emoji emoji-id='5231200819986047254'>📊</tg-emoji> <b>نتيجة الحاسبة لعملة {curr_name}</b>\n\n"
               f"📦 الكمية: <b>{format_large_amount(amount)}</b>\n"
               f"💰 سعر الشراء: <b>{format_large_amount(purchase_price)}</b>\n"
               f"⚡ السعر الحالي: <b>{format_large_amount(current_price)}</b>\n"
               f"╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
               f"💳 إجمالي الشراء: <b>{format_large_amount(total_invested)}</b>\n"
               f"🏦 القيمة الحالية: <b>{format_large_amount(current_total)}</b>\n"
               f"╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
               f"النتيجة: <b>{status_text}</b> {status_emoji}\n"
               f"الصافي: <b>{sign}{format_large_amount(abs(profit_loss))}</b> ({sign}{profit_loss_percent:.2f}%)\n\n"
               f"Dev : <tg-emoji emoji-id='4949843327810798325'>👨‍💻</tg-emoji> | <b>الروسي</b>")
        await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
        return ConversationHandler.END
    except:
        await send_custom_msg(update.message.chat_id, "⚠️ حدث خطأ أثناء الحساب، يرجى المحاولة لاحقاً.", update.message.message_id)
        return ConversationHandler.END

async def post_init(app: Application):
    global mrkt_http
    mrkt_http = AsyncSession(impersonate="chrome")
    asyncio.create_task(check_alerts_loop(app))
    asyncio.create_task(check_whales_loop(app)) 
    asyncio.create_task(tonnel_websocket_loop()) 
    asyncio.create_task(floor_updater_loop())
    asyncio.create_task(mrkt_updater_loop())
    asyncio.create_task(price_history_loop())

async def price_history_loop():
    # يجمع سعر الماستر كل 5 دقايق حتى يشتغل مؤشر الماستر واسيا
    while True:
        try: await update_prices_if_needed()
        except Exception: pass
        await asyncio.sleep(300)

def resolve_gift_name_mrkt(search_term):
    if not search_term: return ""
    s = search_term.lower().replace("'", "").replace("’", "").replace("-", " ").strip()
    if s in ALIASES: return ALIASES[s]
    search_words = s.split()
    for known in KNOWN_GIFTS:
        k = known.lower().replace("'", "").replace("’", "").replace("-", " ")
        if s == k: return known
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
    btn = [[{"text": "بحث في مركت", "callback_data": "search_mrkt", "style": "success", "icon_custom_emoji_id": MRKT_ICON_ID}],
           [{"text": "بحث في تونيل", "callback_data": "search_tonnel", "style": "danger", "icon_custom_emoji_id": TONNEL_ICON_ID}],
           [{"text": "الغاء", "callback_data": "cancel", "style": "primary", "icon_custom_emoji_id": "5440681540541502133"},
            {"text": "اخبار الهدايا", "url": "https://t.me/Guidance_nft", "style": "danger", "icon_custom_emoji_id": "5224257782013769471"}]]
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id, extra_buttons=btn)
    return ASK_MARKET_CHOICE

async def handle_market_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "search_tonnel":
        await edit_custom_msg(query.message.chat.id, query.message.message_id, f"{TONNEL_TEXT_EMOJI} أرسل اسم الهدية للبحث في <b>تونيل</b>:", extra_buttons=[CANCEL_BTN])
        return ASK_GIFT_SEARCH_TONNEL
    elif query.data == "search_mrkt":
        await edit_custom_msg(query.message.chat.id, query.message.message_id, f"{MRKT_TEXT_EMOJI} أرسل اسم الهدية للبحث في <b>مركت</b>:", extra_buttons=[CANCEL_BTN])
        return ASK_GIFT_SEARCH_MRKT

async def perform_gift_search_tonnel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    search_query = update.message.text.strip().lower()
    if 't.me/nft/' in search_query or 'fragment.com' in search_query:
        match = re.search(r'nft/([a-zA-Z0-9_]+)', search_query)
        if match: search_query = match.group(1).replace('-', ' ')
    search_query = re.sub(r'-\d+$', '', search_query).strip()
    clean_compare = search_query.replace(' ', '')
    msg_wait = await send_custom_msg(update.message.chat_id, f"جاري البحث في تونيل عن <b>{html.escape(search_query)}</b>... {SEARCH_EMOJI}", update.message.message_id)
    
    found_price, found_name, found_gift_id, found_gift_num = None, search_query, None, None
    for gift_id, data in active_listings.items():
        if clean_compare in data['name'].lower().replace(' ', ''):
            if data['price'] > 0 and (found_price is None or data['price'] < found_price):
                found_price, found_name, found_gift_id, found_gift_num = data['price'], data['name'], gift_id, data.get('num', '')
    if found_price is None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.getgems.io/graphql", json={"query": "query Search($query: String!) { alphaSearch(query: $query) { collections { name stats { floorPrice } } } }", "variables": {"query": search_query}}, headers={"Content-Type": "application/json"}, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for col in data.get("data", {}).get("alphaSearch", {}).get("collections", []):
                            if clean_compare in col.get("name", "").lower().replace(' ', '') and col.get("stats", {}).get("floorPrice"):
                                current_price = float(col["stats"]["floorPrice"]) / 1e9
                                if current_price > 0 and (found_price is None or current_price < found_price):
                                    found_price, found_name = current_price, col.get("name")
        except: pass
    if found_price:
        clean_url_name = found_name.lower().replace(' ', '').replace('’', '').replace("'", "")
        btn = []
        if found_gift_id: btn.append([{"text": "عرض في Tonnel", "url": f"https://t.me/tonnel_network_bot/gift?startapp={found_gift_id}", "style": "success", "icon_custom_emoji_id": TONNEL_ICON_ID}])
        btn.append([{"text": "عرض في تيليجرام", "url": f"https://t.me/nft/{clean_url_name}-{found_gift_num}" if found_gift_num else f"https://t.me/nft/{clean_url_name}", "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}])
        await edit_custom_msg(update.message.chat_id, msg_wait, f"{GIFT_FLOOR_EMOJI} نتيجة البحث في تونيل:\nالهدية: <b>{html.escape(str(found_name))}</b>\nأقل سعر: <b>{format_exact_price(found_price)}</b> {GRAM_EMOJI}", extra_buttons=btn)
    else:
        await edit_custom_msg(update.message.chat_id, msg_wait, f"عذراً، لم أتمكن من العثور على الهدية في تونيل. {FAIL_EMOJI}")
    return ConversationHandler.END

async def perform_gift_search_mrkt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_user_banned(update, context): return ConversationHandler.END
    raw_query = update.message.text.strip()
    msg_wait = await send_custom_msg(update.message.chat_id, f"جاري البحث في مركت عن <b>{html.escape(raw_query)}</b>... {SEARCH_EMOJI}", update.message.message_id)
    global mrkt_token, mrkt_http
    if not mrkt_token: mrkt_token = await get_mrkt_auth_token()
    if not mrkt_token or not mrkt_http:
        await edit_custom_msg(update.message.chat_id, msg_wait, f"عذراً، يوجد مشكلة في الاتصال بـ MRKT حالياً. {WARN_EMOJI}")
        return ConversationHandler.END
    exact_name = resolve_gift_name_mrkt(raw_query)
    collections_list = list(set([exact_name, exact_name.replace("’", "'"), exact_name.replace("'", "’")])) if exact_name else []
    found_gift = None
    cursor = ""
    for _ in range(5): 
        try:
            r = await mrkt_http.post('https://api.tgmrkt.io/api/v1/gifts/saling', headers=make_mrkt_headers(mrkt_token), json=get_mrkt_payload(collections_list, cursor, "Price"))
            if r.status_code in [401, 403]:
                mrkt_token = None
                await edit_custom_msg(update.message.chat_id, msg_wait, f"انتهت صلاحية الاتصال بـ MRKT، حاول مرة أخرى. {WARN_EMOJI}")
                return ConversationHandler.END
            if r.status_code == 200:
                data = r.json()
                for g in data.get("gifts", []):
                    if isinstance(g, dict) and g.get("isOnSale") is not False:
                        if exact_name.lower().replace("'", "").replace("’", "") in g.get("collectionName", "").lower().replace("'", "").replace("’", ""):
                            found_gift = g
                            break
                if found_gift: break
                next_cursor = data.get("cursor")
                if not next_cursor or next_cursor == cursor: break
                cursor = next_cursor
            else: break
        except: break
    if found_gift:
        ton_price = extract_ton_price_mrkt(found_gift)
        if ton_price:
            gift_name = found_gift.get("collectionName") or found_gift.get("title") or "Unknown"
            btn = [[{"text": "عرض في MRKT", "url": f"https://t.me/mrkt/app?startapp={found_gift.get('id')}", "style": "success", "icon_custom_emoji_id": MRKT_ICON_ID}]] if found_gift.get("id") else []
            gift_num = found_gift.get("number")
            clean_url_name = gift_name.lower().replace(' ', '').replace('’', '').replace("'", "")
            btn.append([{"text": "عرض في تيليجرام", "url": f"https://t.me/nft/{clean_url_name}-{gift_num}" if gift_num else f"https://t.me/nft/{clean_url_name}", "style": "primary", "icon_custom_emoji_id": "5411597774359653692"}])
            await edit_custom_msg(update.message.chat_id, msg_wait, f"{MRKT_TEXT_EMOJI} نتيجة البحث في مركت:\nالهدية: <b>{html.escape(str(gift_name))}</b>\nأقل سعر: <b>{format_exact_price(ton_price)}</b> {GRAM_EMOJI}", extra_buttons=btn)
            return ConversationHandler.END
    await edit_custom_msg(update.message.chat_id, msg_wait, f"عذراً، لم أتمكن من العثور على الهدية في مركت. {FAIL_EMOJI}")
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip().lower()
    chat_id, user_id, msg_id = update.message.chat_id, update.message.from_user.id, update.message.message_id
    await track_new_user(update.effective_user, context)
    if await is_user_banned(update, context): return
    address = find_ton_address(update.message.text)
    if address:
        await handle_wallet_address(update, context, address)
        return
    if any(word in text.split() for word in ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]): return
    chart_code = detect_chart_request(text.lstrip('/'))
    if chart_code:
        await send_chart(update, context, chart_code)
        return
    if text in ["الاوامر", "اوامر"]:
        msg = f"اهلا بك في قائمه اوامر البوت {CLIPBOARD_EMOJI}\n\n"
        msg += f'{NUM_EMOJIS[1]} <b>صرف [رقم] [عملة]</b>: لحساب قيمة العملات مباشرة (دولار، ماستر، جرام، بتكوين، اسيا، نجوم، باث) {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[2]} <b>نبهني</b>: لمراقبة سعر عملة معينة أو صيد الهدايا الرخيصة {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[3]} <b>تنبيهاتي</b>: لعرض وإدارة تنبيهات الأسعار الخاصة بك {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[4]} <b>تفعيل التنبيهات</b>: لتفعيل/إلغاء وضع مراقبة حيتان GRAM وإرسال إشعار للتحويلات الضخمة {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[5]} <b>رصيدي</b>: لمعرفة رصيدك في المحفظة المربوطة {END_EMOJIS}\n\n'
        msg += f'{NUM_EMOJIS[6]} <b>تغيير محفظتي</b>: لربط أو تغيير محفظة GRAM الخاصة بك {END_EMOJIS}\n'
        msg += f'<tg-emoji emoji-id="5411597774359653692">🔍</tg-emoji> <b>بحث هدية</b>: للبحث عن ارخص سعر لهدية معينة {END_EMOJIS}\n'
        msg += f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <b>حاسبه</b>: لحساب أرباحك وخسائرك في العملات {END_EMOJIS}\n'
        msg += f'📱 <b>تحويل</b>: للتعرف على طريقة تحويل رصيد اسياسيل بسهولة {END_EMOJIS}\n'
        msg += f'{UP_EMOJI} <b>مؤشر</b>: صورة مؤشر صعود ونزول الجرام (او اكتب: جرام، بتكوين، ماستر، اسيا) {END_EMOJIS}\n'
        msg += f'{SEARCH_EMOJI} <b>ارسل اي عنوان محفظة</b>: يطلعلك رصيدها وآخر تحويل وعدد المقتنيات وأنشطتها {END_EMOJIS}\n'
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return
    if text == "تفعيل التنبيهات":
        await toggle_whale_alerts(update, context)
        return
    if text == "تحويل":
        msg = ("📱 <b>طريقة تحويل الرصيد (آسياسيل)</b>\n\nللحصول على كود التحويل جاهز للنسخ، فقط ارسل المبلغ متبوعاً برقم الهاتف (أو العكس).\n\n"
               "<b>مثال:</b>\n<code>07748121641 5000</code>\nأو\n<code>5000 07748121641</code>\n\n<i>ملاحظة: الحد الأدنى 1,000 دينار والحد الأقصى 10,000 دينار.</i>")
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    transfer_match = re.match(r'^(\d+)\s+(\d+)$', text)
    if transfer_match:
        num1, num2 = transfer_match.group(1), transfer_match.group(2)
        amount, phone = None, None
        if int(num1) <= 50000 and len(num2) >= 8: amount, phone = int(num1), num2
        elif int(num2) <= 50000 and len(num1) >= 8: amount, phone = int(num2), num1
        if amount is not None and phone is not None:
            if len(phone) < 10 or len(phone) > 11:
                await send_custom_msg(chat_id, f"❌ <b>خطأ:</b> الرقم غلط! يجب أن يكون رقم الهاتف 10 أو 11 رقماً.", reply_to_message_id=msg_id)
                return
            if amount > 10000:
                await send_custom_msg(chat_id, f"❌ <b>خطأ:</b> الحد الأقصى للتحويل في آسياسيل هو 10,000 دينار فقط.", reply_to_message_id=msg_id)
                return
            if amount < 1000:
                await send_custom_msg(chat_id, f"❌ <b>خطأ:</b> أقل مبلغ للتحويل في آسياسيل هو 1,000 دينار.", reply_to_message_id=msg_id)
                return
            msg = (f"📲 <b>كود التحويل من خدمة آسياسيل (اضغط للنسخ)</b>\n\n<code>*123*{amount}*{phone}*1#</code>\n\n"
                   f"💵 <b>المبلغ:</b> {amount:,}\n📞 <b>المستلم:</b> {phone}\n\n{WARN_EMOJI} <i>ملاحظة مهمة جداً: أُخلي مسؤوليتي من أي خطأ في الرقم أو الكود، عليك التأكد بنفسك قبل الاتصال.</i>")
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
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
            await send_custom_msg(chat_id, f"لم تقم بربط محفضتك بالبوت {WARN_EMOJI}", reply_to_message_id=msg_id, extra_buttons=[[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]])
        else:
            is_valid, ton_bal, usdt_bal = await check_ton_wallet(user_wallets[user_id])
            if is_valid: await send_custom_msg(chat_id, f"الان لديك :\nGRAM {GRAM_EMOJI}: {ton_bal:.2f}\nUSDT {USDT_CASH}: {usdt_bal:.2f}", reply_to_message_id=msg_id)
            else: await send_custom_msg(chat_id, f"عذراً، مشكلة في محفظتك المربوطة. {WARN_EMOJI}", reply_to_message_id=msg_id)
        return
        
    if text in ["رصيده", "/رصيده"]:
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            target_id, target_name = update.message.reply_to_message.from_user.id, html.escape(update.message.reply_to_message.from_user.first_name)
            if target_id not in user_wallets: await send_custom_msg(chat_id, f"المستخدم <b>{target_name}</b> لم يقم بربط محفظته بالبوت {WARN_EMOJI}", reply_to_message_id=msg_id)
            else:
                is_valid, ton_bal, usdt_bal = await check_ton_wallet(user_wallets[target_id])
                if is_valid: await send_custom_msg(chat_id, f"الان رصيد {target_name} هو :\nGRAM {GRAM_EMOJI}: {ton_bal:.2f}\nUSDT {USDT_CASH}: {usdt_bal:.2f}", reply_to_message_id=msg_id)
                else: await send_custom_msg(chat_id, f"عذراً، مشكلة في محفظة {target_name} المربوطة. {WARN_EMOJI}", reply_to_message_id=msg_id)
        else: await send_custom_msg(chat_id, f"يرجى الرد على رسالة الشخص لمعرفة رصيده {WARN_EMOJI}", reply_to_message_id=msg_id)
        return

    if text in ["تغيير محفظتي", "/تغيير محفظتي", "تغيير محفضتي", "/تغيير محفضتي"]:
        await send_custom_msg(chat_id, f"اضغط على الزر أدناه لتغيير محفظتك المربوطة {DOWN_EMOJI}:", reply_to_message_id=msg_id, extra_buttons=[[{"text": "تغيير محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]])
        return

    calc_match = re.match(r'^(?:صرف|سعر|حساب)?\s*(?:(\d+(?:\.\d+)?)\s*)?(الف|مليون|بليون|مليار|ترليون|كوادرليون)?\s*(جرام|غرام|كرام|قرام|gram|تون|ton|دولار|usdt|usd|\$|ماستر|master|بتكوين|بيتكوين|btc|bitcoin|اسيا|آسيا|asia|باث|bath|نجمه|نجمة|نجوم|star|stars|نج)(?:\s|$)', text)
    if calc_match and (calc_match.group(1) or calc_match.group(2)):
        amount_str = calc_match.group(1)
        amount = float(amount_str) if amount_str else 1.0
        if calc_match.group(2): amount *= {'الف': 1e3, 'مليون': 1e6, 'بليون': 1e9, 'مليار': 1e9, 'ترليون': 1e12, 'كوادرليون': 1e15}[calc_match.group(2)]
        await update_prices_if_needed()
        await send_custom_msg(chat_id, generate_conversion_msg(amount, calc_match.group(3)), reply_to_message_id=msg_id)
        return

    if text in ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "جرام", "غرام", "كرام", "قرام", "btc", "gram", "ماستر", "الماستر", "master", "نجوم", "نجمة", "نج", "اسيا", "آسيا", "asia", "باث", "bath", "صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار", "ص", "صر"]:
        await update_prices_if_needed()
        await send_custom_msg(chat_id, cached_msg if cached_msg else f"عذراً، حاول ثواني.. {WAIT_EMOJI}", reply_to_message_id=msg_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")

@web_app.route('/')
def home(): return "البوت شغال بقوة 🔥"

@web_app.route('/app')
def wallet_app(): return send_from_directory(WEBAPP_DIR, "wallet.html")

def api_response(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    return resp

@web_app.route('/api/wallet/<address>')
def api_wallet(address):
    if not is_valid_ton_address(address): return api_response({"error": "invalid_address"}, 400)
    try: data = asyncio.run(fetch_wallet_summary(address))
    except Exception: data = None
    return api_response(data) if data else api_response({"error": "unavailable"}, 502)

@web_app.route('/api/wallet/<address>/events')
def api_wallet_events(address):
    if not is_valid_ton_address(address): return api_response({"error": "invalid_address"}, 400)
    before_lt = request.args.get("before_lt", "")
    try: data = asyncio.run(fetch_wallet_events(address, int(before_lt) if before_lt.isdigit() else None))
    except Exception: data = None
    return api_response(data) if data is not None else api_response({"error": "unavailable"}, 502)

@web_app.route('/api/wallet/<address>/nfts')
def api_wallet_nfts(address):
    if not is_valid_ton_address(address): return api_response({"error": "invalid_address"}, 400)
    offset = request.args.get("offset", "0")
    try: data = asyncio.run(fetch_wallet_nfts(address, min(int(offset), 100000) if offset.isdigit() else 0))
    except Exception: data = None
    return api_response(data) if data is not None else api_response({"error": "unavailable"}, 502)
def run_web(): web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)
    app = (Application.builder().token(TOKEN).request(t_request).post_init(post_init).build())
    
    cancel_handlers = [MessageHandler(filters.Regex(r'^(الغاء|/cancel)$'), cancel_action), CallbackQueryHandler(cancel_action, pattern="^cancel$")]
    
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?نبهني$'), alert_start)],
        states={
            ASK_ALERT_TYPE: [CallbackQueryHandler(alert_type_callback, pattern="^(alert_currency_start|alert_gifts_toggle|stop_gift_alerts)$")],
            ASK_CURRENCY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), alert_currency_name)],
            ASK_CURRENCY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), alert_currency_price)]
        },
        fallbacks=cancel_handlers + [MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts)],
        per_chat=True, per_user=True, per_message=False
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), receive_wallet_address)]},
        fallbacks=cancel_handlers, per_chat=True, per_user=True, per_message=False
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?بحث هدية$|/?بحث$'), gift_search_start)],
        states={
            ASK_MARKET_CHOICE: [CallbackQueryHandler(handle_market_choice, pattern="^search_")],
            ASK_GIFT_SEARCH_TONNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), perform_gift_search_tonnel)],
            ASK_GIFT_SEARCH_MRKT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), perform_gift_search_mrkt)]
        },
        fallbacks=cancel_handlers, per_chat=True, per_user=True, per_message=False
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("ban", ban_start), MessageHandler(filters.Regex(r'^/?حظر$'), ban_start)],
        states={ASK_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), ban_receive)]},
        fallbacks=cancel_handlers, per_chat=True, per_user=True, per_message=False
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("unban", unban_start), MessageHandler(filters.Regex(r'^/?الغاء حظر$|/?الغاء الحظر$'), unban_start)],
        states={ASK_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), unban_receive)]},
        fallbacks=cancel_handlers, per_chat=True, per_user=True, per_message=False
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?(حاسبه|حاسبة|احسب)$'), calc_start)],
        states={
            ASK_CALC_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), calc_currency)],
            ASK_CALC_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), calc_price)],
            ASK_CALC_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^(الغاء|/cancel)$'), calc_amount)]
        },
        fallbacks=cancel_handlers, per_chat=True, per_user=True, per_message=False
    ))
    
    app.add_handler(CommandHandler("reset", reset_market_cmd))
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^reset_"))
    app.add_handler(CallbackQueryHandler(chart_callback, pattern=r"^chart\|"))
    app.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts))
    app.add_handler(MessageHandler(filters.Regex(r'^/?تنبيهاتي$'), my_alerts)) 
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10, allowed_updates=["message", "callback_query", "my_chat_member"])

if __name__ == "__main__":
    main()
