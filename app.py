import os
import time
import aiohttp
import logging
import threading
import asyncio
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, ConversationHandler, CommandHandler, filters, ContextTypes, ChatMemberHandler
from telegram.request import HTTPXRequest

# إعدادات اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = '8679057078:AAH27klAkXPLu9bWVr-_jhmg06gdYvefVps'
ADMIN_ID = 7126816492 # آيدي حسابك ليوصلك الاشعارات

# نظام الكاش والبيانات
CACHE_TIME = 5
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000
crypto_prices = {'BTC': 0, 'TON': 0, 'ETH': 0, 'SOL': 0}

# قواعد البيانات (في الذاكرة)
alerts_db = []
user_wallets = {} # {user_id: wallet_address}
bot_users = set() # تتبع المستخدمين الجدد
user_info_db = {} # {user_id: {"ادرسي": "...", "رقمي": "..."}}

# حالات المحادثة
ASK_CURRENCY, ASK_PRICE = range(2)
ASK_WALLET = 3 
ASK_INFO = 4 # حالة سؤال معلومات المستخدم

# --- نظام اشعارات وتتبع المستخدمين ---
async def track_new_user(user, context: ContextTypes.DEFAULT_TYPE):
    if user.id not in bot_users:
        bot_users.add(user.id)
        username = f"@{user.username}" if user.username else str(user.id)
        msg = f"🟢 دخل شخص جديد\nعدد المستخدمين الان: {len(bot_users)}\nيوزر الشخص: {username}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        except Exception as e:
            print(f"Error sending admin notification: {e}")

async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result.new_chat_member.status in ["member", "administrator"] and result.old_chat_member.status not in ["member", "administrator"]:
        chat = result.chat
        
        # رسالة الترحيب داخل الكروب
        msg = "تم تشغيل البوت اكتب الاوامر او اوامر لعرض الشرح"
        try:
            await send_custom_msg(chat.id, msg)
        except: pass
        
        # اشعار للادمن
        admin_msg = f"🔔 تم إضافة البوت إلى مجموعة جديدة!\nالاسم: {chat.title}\nالآيدي: {chat.id}"
        if chat.username:
            admin_msg += f"\nالرابط: https://t.me/{chat.username}"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
        except: pass

# --- دالة الإرسال الشاملة ---
async def send_custom_msg(chat_id, text, reply_to_message_id=None, extra_buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    inline_keyboard = []
    
    if extra_buttons:
        inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "(5224257782013769471) اخبار الفلوس (5224257782013769471)", 
            "url": "https://t.me/Guidance_nft", 
            "style": "danger"
        }
    ])

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    }
    
    if reply_to_message_id:
        payload["reply_parameters"] = {"message_id": reply_to_message_id}
        
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", {}).get("message_id")
        except Exception as e:
            print(f"Error sending message: {e}")
    return None

async def edit_custom_msg(chat_id, message_id, text, extra_buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    inline_keyboard = []
    
    if extra_buttons:
        inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "(5224257782013769471) اخبار الفلوس (5224257782013769471)", 
            "url": "https://t.me/Guidance_nft", 
            "style": "danger"
        }
    ])

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error editing message: {e}")

# --- API فحص المحفظة ---
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
    except Exception as e:
        return False, 0, 0

# --- الأوامر الأساسية والمحفظة ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_new_user(update.effective_user, context)
    text = update.message.text
    user = update.message.from_user
    chat_id = update.message.chat_id
    
    if 'link_wallet' in text:
        if user.id in user_wallets:
            msg = "لديك محفضه مربوطه بالفعل\nلتغيير محفضتك اضغط على الزر ادناه  :"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]]
            await send_custom_msg(chat_id, msg, extra_buttons=btn)
            return ConversationHandler.END
        else:
            msg = f"اهلا بك {user.first_name} <tg-emoji emoji-id=\"6048861163196783957\">👑</tg-emoji>\n\nقم بارسال عنوان محفضتك \nاو الادرس الخاص بك لربط محفضتك <tg-emoji emoji-id=\"5319250406923051255\">✈️</tg-emoji>"
            await send_custom_msg(chat_id, msg)
            return ASK_WALLET
            
    elif 'change_wallet' in text:
        msg = f"اهلا بك {user.first_name} <tg-emoji emoji-id=\"6048861163196783957\">👑</tg-emoji>\n\nقم بارسال عنوان محفضتك \nاو الادرس الخاص بك لربط محفضتك <tg-emoji emoji-id=\"5319250406923051255\">✈️</tg-emoji>"
        await send_custom_msg(chat_id, msg)
        return ASK_WALLET
        
    else:
        # Start العادي
        msg = (f"أهلاً بك في البوت يا {user.first_name}! <tg-emoji emoji-id=\"5800769433974611462\">👋</tg-emoji>\n\n"
               f"هذا البوت يقدم خدمات الصرافة والتنبيهات الذكية وحفظ المعلومات.\n"
               f"اكتب <b>الاوامر</b> او <b>اوامر</b> لعرض جميع خدمات البوت.")
        btn = [[{
            "text": "اضافه البوت الى مجموعتي", 
            "url": f"https://t.me/{context.bot.username}?startgroup=true", 
            "style": "primary"
        }]]
        await send_custom_msg(chat_id, msg, extra_buttons=btn)
        return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_new_user(update.effective_user, context)
    chat_id = update.effective_chat.id
    msg = (f"مرحباً بك في المساعدة! <tg-emoji emoji-id=\"5800769433974611462\">ℹ️</tg-emoji>\n\n"
           f"هذا البوت يوفر أدوات صرافة متقدمة، تنبيهات، حفظ معلومات شخصية ومحفظة.\n\n"
           f"ارسل بالكروب <b>الاوامر</b> أو <b>اوامر</b> لعرض الشرح والقائمة كاملة.")
    btn = [[{
        "text": "اضافه البوت الى مجموعتي", 
        "url": f"https://t.me/{context.bot.username}?startgroup=true", 
        "style": "primary"
    }]]
    await send_custom_msg(chat_id, msg, extra_buttons=btn)

async def receive_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    msg_id = await send_custom_msg(chat_id, "يتم البحث عن محفضتك... <tg-emoji emoji-id=\"5411597774359653692\">🔍</tg-emoji>")
    is_valid, _, _ = await check_ton_wallet(address)
    
    if is_valid:
        await asyncio.sleep(1.5)
        await edit_custom_msg(chat_id, msg_id, "جاري ربط المحفضه بالبوت... <tg-emoji emoji-id=\"5215484787325676090\">⏳</tg-emoji>")
        await asyncio.sleep(1.5)
        user_wallets[user_id] = address
        await edit_custom_msg(chat_id, msg_id, "تم ربط محفضتك بنجاح  . <tg-emoji emoji-id=\"5215492745900077682\">✅</tg-emoji>")
    else:
        await asyncio.sleep(1.5)
        await edit_custom_msg(chat_id, msg_id, "عنوان المحفضه خطا ! <tg-emoji emoji-id=\"5215204871422093648\">❌</tg-emoji>")
    return ConversationHandler.END

# --- نظام معلوماتي ---
async def add_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_new_user(update.effective_user, context)
    msg = ("ارسل معلوماتك بهذا الشكل:\n\n"
           "ادرسي: XYXY\n"
           "رقمي: 077\n"
           "رقمي²: 078\n"
           "باينس: xyxy\n\n"
           "ملاحضه: لايجب عليك الإلتزام بالاسماء يمكنك وضع اسماء خاصه")
    await send_custom_msg(update.message.chat_id, msg)
    return ASK_INFO

async def save_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if user_id not in user_info_db:
        user_info_db[user_id] = {}
        
    lines = text.split('\n')
    for line in lines:
        if ':' in line or ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip()
                user_info_db[user_id][key] = val
                
    msg = "تم الحفض\nارسل معلوماتي او احد الاشياء التي اضفتها لعرض المعلومات"
    await send_custom_msg(update.message.chat_id, msg)
    return ConversationHandler.END

# --- أنظمة الصرافة والأسعار الأساسية ---
def normalize_currency(curr_str):
    curr = curr_str.lower().strip()
    if curr in ['دولار', 'usdt', 'usd']: return 'USD'
    elif curr == 'ماستر': return 'IQD'
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: return 'STARS'
    elif curr in ['تون', 'ton']: return 'TON'
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: return 'BTC'
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']: return 'ETH'
    elif curr in ['سولانا', 'sol', 'solana']: return 'SOL'
    return None

def get_current_price(curr_code):
    if curr_code == 'USD': return 1.0
    elif curr_code == 'IQD': return last_known_iqd
    elif curr_code == 'STARS': return 0.015
    elif curr_code in crypto_prices: return crypto_prices[curr_code]
    return 0

async def fetch_mastercard_price(session):
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {"Content-Type": "application/json"}
        payload = {"fiat": "IQD", "page": 1, "rows": 1, "tradeType": "BUY", "asset": "USDT", "countries": [], "payTypes": [], "publisherType": None, "merchantCheck": False}
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    price = data['data'][0]['adv']['price']
                    return str(int(float(price) * 100))
    except Exception: pass
    return None

async def update_prices_if_needed():
    global last_fetch_time, cached_msg, last_known_iqd, crypto_prices
    current_time = time.time()
    
    if current_time - last_fetch_time < CACHE_TIME and cached_msg:
        return True
        
    try:
        async with aiohttp.ClientSession() as session:
            crypto_url = 'https://api.binance.com/api/v3/ticker/price?symbols=["BTCUSDT","ETHUSDT","SOLUSDT","TONUSDT"]'
            crypto_task = session.get(crypto_url, timeout=10)
            master_task = fetch_mastercard_price(session)
            
            response, master_price_str = await asyncio.gather(crypto_task, master_task, return_exceptions=True)
            
            if not isinstance(response, Exception) and response.status == 200:
                crypto_data = await response.json()
                prices = {item['symbol']: float(item['price']) for item in crypto_data}
                crypto_prices['BTC'] = prices.get('BTCUSDT', 0)
                crypto_prices['TON'] = prices.get('TONUSDT', 0)
                crypto_prices['ETH'] = prices.get('ETHUSDT', 0)
                crypto_prices['SOL'] = prices.get('SOLUSDT', 0)

            if isinstance(master_price_str, str) and master_price_str.isdigit():
                last_known_iqd = int(master_price_str)

            btc_int, eth_int = int(crypto_prices['BTC']), int(crypto_prices['ETH'])
            ton_val, sol_val = crypto_prices['TON'], crypto_prices['SOL']

            msg = (f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                   f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): \u2067<b>{last_known_iqd:,}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc_int:,}</b>\n'
                   f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: <b>${ton_val:,.2f}</b>\n'
                   f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: <b>${eth_int:,}</b>\n'
                   f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: <b>${sol_val:,.2f}</b>\n'
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
    elif curr == 'ماستر':
        base, name = 'IQD', "ماستر"
        actual_iqd = amount * 1000 if amount < 100000 else amount
        usd_val = actual_iqd / (last_known_iqd / 100)
        show_iqd = False  
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']:
        base, name, usd_val = 'STARS', '<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم', amount * 0.015 
    elif curr in ['تون', 'ton']: base, name, usd_val = 'TON', "تون (TON)", amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: base, name, usd_val = 'BTC', "بتكوين (BTC)", amount * crypto_prices.get('BTC', 0)
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']: base, name, usd_val = 'ETH', "إيثيريوم (ETH)", amount * crypto_prices.get('ETH', 0)
    elif curr in ['سولانا', 'sol', 'solana']: base, name, usd_val = 'SOL', "سولانا (SOL)", amount * crypto_prices.get('SOL', 0)
    else: return "⚠️ عذراً، العملة غير مدعومة."

    if usd_val == 0: return "⚠️ عذراً، لا يمكن حساب القيمة الآن."

    iqd_val = (usd_val * last_known_iqd) / 100
    ton_val = usd_val / crypto_prices['TON'] if crypto_prices.get('TON') else 0
    stars_val = usd_val / 0.015 
    btc_val = usd_val / crypto_prices['BTC'] if crypto_prices.get('BTC') else 0
    eth_val = usd_val / crypto_prices['ETH'] if crypto_prices.get('ETH') else 0
    sol_val = usd_val / crypto_prices['SOL'] if crypto_prices.get('SOL') else 0

    msg = f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <b>تصريف {amount:g} {name}:</b>\n\n'
    if show_usd: msg += f'💵 بالدولار: \u2067<b>${usd_val:,.3f}</b>\u2069\n'
    if show_iqd: msg += f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> بالعراقي: \u2067<b>{iqd_val:,.0f}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    if base != 'TON' and ton_val > 0: msg += f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> تون: <b>{ton_val:,.2f}</b> TON\n'
    if base != 'STARS' and stars_val > 0: msg += f'<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم: <b>{stars_val:,.0f}</b> Stars\n'
    if base != 'STARS':
        if base != 'BTC' and btc_val > 0: msg += f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> بتكوين: <b>{btc_val:,.6f}</b> BTC\n'
        if base != 'ETH' and eth_val > 0: msg += f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> إيثيريوم: <b>{eth_val:,.5f}</b> ETH\n'
        if base != 'SOL' and sol_val > 0: msg += f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> سولانا: <b>{sol_val:,.2f}</b> SOL\n'
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    msg += f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>'
    return msg

# --- نظام التنبيهات ---
async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🔔 <b>نظام التنبيهات الذكي</b>\n\nاكتب اسم العملة اللي تريد أراقبها (مثال: تون، بتكوين، ماستر...):"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ASK_CURRENCY

async def alert_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curr_input = update.message.text.strip()
    if curr_input.startswith('/ايقاف') or curr_input == 'ايقاف': return await stop_alerts(update, context)
    curr_code = normalize_currency(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, "⚠️ عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح:", update.message.message_id)
        return ASK_CURRENCY
    
    context.user_data['alert_curr'] = curr_code; context.user_data['alert_curr_name'] = curr_input
    await send_custom_msg(update.message.chat_id, f"✅ تم اختيار: <b>{curr_input}</b>\n\n✍️ الآن ادخل السعر الذي تريد التنبيه عنده (أرقام فقط):", update.message.message_id)
    return ASK_PRICE

async def alert_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_input = update.message.text.strip()
    if price_input.startswith('/ايقاف') or price_input == 'ايقاف': return await stop_alerts(update, context)
    match = re.search(r'(\d+(?:\.\d+)?)', price_input)
    if not match:
        await send_custom_msg(update.message.chat_id, "⚠️ يرجى إدخال رقم صحيح:", update.message.message_id)
        return ASK_PRICE
        
    target_price = float(match.group(1))
    curr_code, curr_name = context.user_data['alert_curr'], context.user_data['alert_curr_name']
    
    await update_prices_if_needed()
    current_price = get_current_price(curr_code)
    
    if current_price == 0:
        await send_custom_msg(update.message.chat_id, "⚠️ عذراً، لا يمكن جلب السعر الحالي، حاول لاحقاً.", update.message.message_id)
        return ConversationHandler.END
    if target_price == current_price:
        await send_custom_msg(update.message.chat_id, f"⚠️ الـ {curr_name} أصلاً واصل هذا السعر بالضبط! 😅", update.message.message_id)
        return ConversationHandler.END
        
    direction = 'up' if target_price > current_price else 'down'
    alerts_db.append({'user_id': update.message.from_user.id, 'name': update.message.from_user.first_name, 'chat_id': update.message.chat_id, 'currency': curr_code, 'curr_name': curr_name, 'target': target_price, 'direction': direction, 'active': True})
    
    dir_text = "صعود 📈" if direction == 'up' else "نزول 📉"
    msg = (f"✅ <b>تم التفعيل!</b>\nسيتم تنبيهك عند {dir_text} الـ {curr_name} إلى <code>{target_price:g}</code>\n\nلإيقاف التنبيه ارسل /ايقاف")
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global alerts_db
    user_id = update.message.from_user.id
    initial_len = len(alerts_db)
    alerts_db = [a for a in alerts_db if a['user_id'] != user_id]
    msg = "🛑 تم إيقاف جميع تنبيهاتك بنجاح." if len(alerts_db) < initial_len else "⚠️ ليس لديك أي تنبيهات مفعلة."
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_alerts = [a for a in alerts_db if a['user_id'] == user_id and a['active']]
    if not user_alerts:
        await send_custom_msg(update.message.chat_id, "🔕 لا توجد لديك أي تنبيهات مفعلة حالياً.", update.message.message_id)
        return
    msg = "🔔 <b>تنبيهاتك الحالية:</b>\n\n"
    for idx, a in enumerate(user_alerts, 1):
        dir_emoji = "📈 (صعود)" if a['direction'] == 'up' else "📉 (نزول)"
        msg += f"{idx}. <b>{a['curr_name']}</b> - السعر المطلوب: <code>{a['target']:g}</code> {dir_emoji}\n"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)

async def check_alerts_loop(app: Application):
    global alerts_db 
    while True:
        await asyncio.sleep(10) 
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
                    msg = (f"🚨 {mentions}\n\n🔥 <b>الحگ! الـ {alerts[0]['curr_name']} وصل للسعر المطلوب!</b> <tg-emoji emoji-id=\"5215372534060428125\">🔔</tg-emoji>\n"
                           f"السعر الحالي: <b>{get_current_price(curr_code):g}</b>\n\nلإيقاف التنبيهات ارسل /ايقاف")
                    await send_custom_msg(chat_id, msg)
        alerts_db = [a for a in alerts_db if a['active']]

async def post_init(app: Application):
    asyncio.create_task(check_alerts_loop(app))

# --- معالجة الرسائل العامة الشاملة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    original_text = update.message.text.strip()
    text = original_text.lower()
    chat_id, user_id, msg_id = update.message.chat_id, update.message.from_user.id, update.message.message_id
    
    await track_new_user(update.effective_user, context)

    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text for word in forbidden): return

    # الأوامر والقائمة
    if text in ["الاوامر", "اوامر"]:
        end_emojis = '<tg-emoji emoji-id="5210956306952758910">✔️</tg-emoji> <tg-emoji emoji-id="5958605483488055761">✅</tg-emoji>'
        msg = f"اهلا بك في قائمه اوامر البوت <tg-emoji emoji-id=\"5800769433974611462\">📋</tg-emoji>\n\n"
        msg += f"<tg-emoji emoji-id=\"5408894951440279259\">1️⃣</tg-emoji> <b>/start</b> - لتشغيل البوت وعرض القائمة. {end_emojis}\n"
        msg += f"<tg-emoji emoji-id=\"5411585799990830248\">2️⃣</tg-emoji> <b>/help</b> - لعرض رسالة المساعدة. {end_emojis}\n"
        msg += f"<tg-emoji emoji-id=\"5409189019261103031\">3️⃣</tg-emoji> <b>نبهني</b> - لتعيين تنبيه لسعر عملة. {end_emojis}\n"
        msg += f"<tg-emoji emoji-id=\"5411500398861118321\">4️⃣</tg-emoji> <b>رصيدي</b> - لعرض رصيد محفظتك المربوطة. {end_emojis}\n"
        msg += f"<tg-emoji emoji-id=\"5409338071806146386\">5️⃣</tg-emoji> <b>اضافة معلومات</b> - لحفظ معلوماتك الشخصية. {end_emojis}\n"
        msg += f"<tg-emoji emoji-id=\"5409194048667807708\">6️⃣</tg-emoji> <b>صرف</b> - لمعرفة سعر الصرف المباشر. {end_emojis}\n"
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    # ميزة معلوماتي وبحث المفاتيح المخصصة
    if text in ["معلوماتي", "/معلوماتي"]:
        if user_id not in user_info_db or not user_info_db[user_id]:
            msg = "لم تقم باضافه اي معلومات <tg-emoji emoji-id=\"5800769433974611462\">⚠️</tg-emoji>\nلأضافه معلومات عن نفسك اكتب اضافة معلومات"
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        else:
            msg = "معلوماتك المحفوظة:\n\n"
            for k, v in user_info_db[user_id].items():
                msg += f"<b>{k}</b>: <code>{v}</code>\n"
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    # استدعاء مفتاح معين من معلومات المستخدم
    if user_id in user_info_db and original_text in user_info_db[user_id]:
        val = user_info_db[user_id][original_text]
        await send_custom_msg(chat_id, f"<b>{original_text}</b>: <code>{val}</code>", reply_to_message_id=msg_id)
        return

    # رصيدي
    if text in ["رصيدي", "/رصيدي", "رص", "/رص"]:
        if user_id not in user_wallets:
            msg = "لم تقم بربط محفضتك بالبوت <tg-emoji emoji-id=\"5213195952008997792\">⚠️</tg-emoji>"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=link_wallet", "style": "success"}]]
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        else:
            is_valid, ton_bal, usdt_bal = await check_ton_wallet(user_wallets[user_id])
            if is_valid:
                await send_custom_msg(chat_id, f"الان لديك  :\nTON <tg-emoji emoji-id=\"5321330914851040564\">💎</tg-emoji>: {ton_bal:.2f}\nUSDT <tg-emoji emoji-id=\"5213170203680060059\">💵</tg-emoji>: {usdt_bal:.2f}", reply_to_message_id=msg_id)
            else:
                await send_custom_msg(chat_id, "⚠️ عذراً، مشكلة في محفظتك المربوطة.", reply_to_message_id=msg_id)
        return
        
    # تغيير محفظتي
    if text in ["تغيير محفظتي", "/تغيير محفظتي", "تغيير محفضتي", "/تغيير محفضتي"]:
        btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success"}]]
        await send_custom_msg(chat_id, "اضغط على الزر أدناه لتغيير محفظتك المربوطة:", reply_to_message_id=msg_id, extra_buttons=btn)
        return

    # الصرافة الحاسبة
    calc_match = re.search(r'(?:صرف|سعر|حساب)?\s*(\d+(?:\.\d+)?)\s*(تون|ton|دولار|usdt|usd|ماستر|بتكوين|بيتكوين|btc|bitcoin|ايثيريوم|إيثيريوم|eth|ethereum|سولانا|sol|solana|نجمه|نجمة|نجوم|star|stars|نج)', text)
    if calc_match:
        await update_prices_if_needed()
        reply = generate_conversion_msg(float(calc_match.group(1)), calc_match.group(2))
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)
        return

    # جلب الأسعار
    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol", "ماستر", "نجوم", "نجمة", "نج"]
    if any(phrase in text for phrase in ["صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار"]) or text in ["ص", "صر", "صرف", "تون", "دولار", "ماستر", "نجوم", "نجمة", "نج"] or any(word == text for word in allowed_keywords):
        await update_prices_if_needed()
        reply = cached_msg if cached_msg else "⚠️ عذراً، حاول ثواني.."
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

# --- سيرفر الويب الأساسي ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال بقوة 🔥"
def run_web():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    time.sleep(8)

    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)

    app = (Application.builder()
           .token(TOKEN)
           .request(t_request)
           .post_init(post_init) 
           .build())
    
    alert_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?نبهني$'), alert_start)],
        states={ASK_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_currency)], ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price)]},
        fallbacks=[MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts)],
        per_chat=True, per_user=True
    )
    
    info_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^(اضافة معلومات|اضافه معلومات|اضافه|اضافة)$'), add_info_start)],
        states={ASK_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_user_info)]},
        fallbacks=[], per_chat=True, per_user=True
    )
    
    wallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet_address)]},
        fallbacks=[]
    )
    
    app.add_handler(alert_conv_handler)
    app.add_handler(info_conv_handler)
    app.add_handler(wallet_conv_handler)
    
    app.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("help", help_command))
    
    app.add_handler(MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts))
    app.add_handler(MessageHandler(filters.Regex(r'^/?تنبيهاتي$'), my_alerts)) 
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
