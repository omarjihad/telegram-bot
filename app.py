import os
import time
import aiohttp
import logging
import threading
import asyncio
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, ConversationHandler, CommandHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# إعدادات اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = '8679057078:AAH27klAkXPLu9bWVr-_jhmg06gdYvefVps'

# نظام الكاش والبيانات
CACHE_TIME = 5
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000
crypto_prices = {'BTC': 0, 'TON': 0, 'ETH': 0, 'SOL': 0}

# قواعد البيانات (في الذاكرة)
alerts_db = []
user_wallets = {} # تخزين محافظ المستخدمين {user_id: wallet_address}

# حالات المحادثة
ASK_CURRENCY, ASK_PRICE = range(2)
ASK_WALLET = 3 # حالة سؤال المحفظة

# --- دالة الإرسال الشاملة (ترجع ID الرسالة حتى نكدر نعدلها بعدين) ---
async def send_custom_msg(chat_id, text, reply_to_message_id=None, extra_buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    inline_keyboard = []
    
    if extra_buttons:
        inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "اخبار الفلوس", 
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
                    # إرجاع آي دي الرسالة اللي اندزت
                    return data.get("result", {}).get("message_id")
        except Exception as e:
            print(f"Error sending custom colored message: {e}")
    return None

# --- دالة تعديل الرسالة (لمنع السبام في الربط) ---
async def edit_custom_msg(chat_id, message_id, text, extra_buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    inline_keyboard = []
    
    if extra_buttons:
        inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "سوالف المشاهير", 
            "url": "https://t.me/+tYh0Y_qvfkpkYzli", 
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
                if resp.status != 200:
                    return False, 0, 0
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
        print(f"Wallet check error: {e}")
        return False, 0, 0

# --- نظام ربط ومراقبة المحفظة ---
async def start_wallet_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.message.from_user
    chat_id = update.message.chat_id
    
    if 'link_wallet' in text:
        if user.id in user_wallets:
            msg = "لديك محفضه مربوطه بالفعل\nلتغيير محفضتك اضغط على الزر ادناه  :"
            btn = [[{
                "text": "ربط محفضتي", 
                "url": f"https://t.me/{context.bot.username}?start=change_wallet", 
                "style": "success",
                "icon_custom_emoji_id": "5409150983030728043"
            }]]
            await send_custom_msg(chat_id, msg, extra_buttons=btn)
            return ConversationHandler.END
        else:
            msg = (f"اهلا بك {user.first_name} <tg-emoji emoji-id=\"6048861163196783957\">👑</tg-emoji>\n\n"
                   f"قم بارسال عنوان محفضتك \nاو الادرس الخاص بك لربط محفضتك <tg-emoji emoji-id=\"5319250406923051255\">✈️</tg-emoji>")
            await send_custom_msg(chat_id, msg)
            return ASK_WALLET
            
    elif 'change_wallet' in text:
        msg = (f"اهلا بك {user.first_name} <tg-emoji emoji-id=\"6048861163196783957\">👑</tg-emoji>\n\n"
               f"قم بارسال عنوان محفضتك \nاو الادرس الخاص بك لربط محفضتك <tg-emoji emoji-id=\"5319250406923051255\">✈️</tg-emoji>")
        await send_custom_msg(chat_id, msg)
        return ASK_WALLET
        
    else:
        await send_custom_msg(chat_id, "أهلاً بك في بوت الصرافة والتنبيهات! استمتع بخدماتنا.")
        return ConversationHandler.END

async def receive_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    # 1. إرسال الرسالة الأولى وتخزين الـ ID مالتها
    msg_id = await send_custom_msg(chat_id, "يتم البحث عن محفضتك... <tg-emoji emoji-id=\"5411597774359653692\">🔍</tg-emoji>")
    
    is_valid, _, _ = await check_ton_wallet(address)
    
    if is_valid:
        await asyncio.sleep(1.5)
        # 2. تعديل نفس الرسالة (لمنع السبام)
        await edit_custom_msg(chat_id, msg_id, "جاري ربط المحفضه بالبوت... <tg-emoji emoji-id=\"5215484787325676090\">⏳</tg-emoji>")
        await asyncio.sleep(1.5)
        
        user_wallets[user_id] = address
        # 3. تعديل نفس الرسالة للنجاح
        await edit_custom_msg(chat_id, msg_id, "تم ربط محفضتك بنجاح  . <tg-emoji emoji-id=\"5215492745900077682\">✅</tg-emoji>")
    else:
        await asyncio.sleep(1.5)
        # تعديل نفس الرسالة للفشل
        await edit_custom_msg(chat_id, msg_id, "عنوان المحفضه خطا ! <tg-emoji emoji-id=\"5215204871422093648\">❌</tg-emoji>")
        
    return ConversationHandler.END


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
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        payload = {"fiat": "IQD", "page": 1, "rows": 1, "tradeType": "BUY", "asset": "USDT", "countries": [], "payTypes": [], "publisherType": None, "merchantCheck": False}
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    price = data['data'][0]['adv']['price']
                    return str(int(float(price) * 100))
    except Exception:
        pass
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

            btc_int = int(crypto_prices['BTC'])
            ton_val = crypto_prices['TON']
            eth_int = int(crypto_prices['ETH'])
            sol_val = crypto_prices['SOL']

            msg = (
                f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): \u2067<b>{last_known_iqd:,}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
                "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc_int:,}</b>\n'
                f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: <b>${ton_val:,.2f}</b>\n'
                f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: <b>${eth_int:,}</b>\n'
                f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: <b>${sol_val:,.2f}</b>\n'
                "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية والمحلية</i>\n'
                f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>'
            )
            
            cached_msg = msg
            last_fetch_time = current_time
            return True
    except Exception:
        return False

def generate_conversion_msg(amount, currency_str):
    curr = currency_str.lower()
    show_usd = True; show_iqd = True

    if curr in ['دولار', 'usdt', 'usd']:
        base = 'USD'; name = "دولار (USDT)"
        usd_val = amount; show_usd = False  
    elif curr == 'ماستر':
        base = 'IQD'; name = "ماستر"
        actual_iqd = amount * 1000 if amount < 100000 else amount
        usd_val = actual_iqd / (last_known_iqd / 100)
        show_iqd = False  
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']:
        base = 'STARS'
        name = '<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم'
        usd_val = amount * 0.015 
    elif curr in ['تون', 'ton']:
        base = 'TON'; name = "تون (TON)"
        usd_val = amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']:
        base = 'BTC'; name = "بتكوين (BTC)"
        usd_val = amount * crypto_prices.get('BTC', 0)
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']:
        base = 'ETH'; name = "إيثيريوم (ETH)"
        usd_val = amount * crypto_prices.get('ETH', 0)
    elif curr in ['سولانا', 'sol', 'solana']:
        base = 'SOL'; name = "سولانا (SOL)"
        usd_val = amount * crypto_prices.get('SOL', 0)
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

async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🔔 <b>نظام التنبيهات الذكي</b>\n\n"
    msg += "هذا الأمر يخلي البوت يراقب أسعار العملات بدالك، ومن يوصل السعر للرقم اللي تريده راح يسويلك منشن وينبهك فوراً!\n\n"
    msg += "👇 <b>الآن، اكتب اسم العملة اللي تريد أراقبها (مثال: تون، بتكوين، ماستر...):</b>"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ASK_CURRENCY

async def alert_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curr_input = update.message.text.strip()
    if curr_input.startswith('/ايقاف') or curr_input == 'ايقاف': 
        return await stop_alerts(update, context)
        
    curr_code = normalize_currency(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, "⚠️ عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح (مثال: تون):", update.message.message_id)
        return ASK_CURRENCY
    
    context.user_data['alert_curr'] = curr_code
    context.user_data['alert_curr_name'] = curr_input
    
    msg = (f"✅ تم اختيار: <b>{curr_input}</b>\n\n"
           f"✍️ الآن ادخل السعر الذي تريد التنبيه عند وصول <b>{curr_input}</b> إليه (أرقام فقط):")
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ASK_PRICE

async def alert_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_input = update.message.text.strip()
    if price_input.startswith('/ايقاف') or price_input == 'ايقاف': 
        return await stop_alerts(update, context)

    match = re.search(r'(\d+(?:\.\d+)?)', price_input)
    if not match:
        await send_custom_msg(update.message.chat_id, "⚠️ يرجى إدخال رقم صحيح:", update.message.message_id)
        return ASK_PRICE
        
    target_price = float(match.group(1))
    curr_code = context.user_data['alert_curr']
    curr_name = context.user_data['alert_curr_name']
    
    await update_prices_if_needed()
    current_price = get_current_price(curr_code)
    
    if current_price == 0:
        await send_custom_msg(update.message.chat_id, "⚠️ عذراً، لا يمكن جلب السعر الحالي، حاول لاحقاً.", update.message.message_id)
        return ConversationHandler.END
        
    if target_price == current_price:
        await send_custom_msg(update.message.chat_id, f"⚠️ الـ {curr_name} أصلاً واصل هذا السعر بالضبط! (السعر الحالي: {current_price:g}) 😅", update.message.message_id)
        return ConversationHandler.END
        
    direction = 'up' if target_price > current_price else 'down'
    user = update.message.from_user
    
    alerts_db.append({
        'user_id': user.id,
        'name': user.first_name,
        'chat_id': update.message.chat_id,
        'currency': curr_code,
        'curr_name': curr_name,
        'target': target_price,
        'direction': direction,
        'active': True
    })
    
    dir_text = "صعود 📈" if direction == 'up' else "نزول 📉"
    
    msg = (f"✅ <b>تم التفعيل!</b>\n"
           f"سيتم تنبيهك عند {dir_text} الـ {curr_name} إلى <code>{target_price:g}</code>\n\n"
           f"لإيقاف التنبيه ارسل /ايقاف\n"
           f"لمعرفة تنبيهاتك الحالية ارسل /تنبيهاتي")
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ConversationHandler.END

async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global alerts_db
    user_id = update.message.from_user.id
    initial_len = len(alerts_db)
    alerts_db = [a for a in alerts_db if a['user_id'] != user_id]
    
    if len(alerts_db) < initial_len:
        await send_custom_msg(update.message.chat_id, "🛑 تم إيقاف جميع تنبيهاتك بنجاح.", update.message.message_id)
    else:
        await send_custom_msg(update.message.chat_id, "⚠️ ليس لديك أي تنبيهات مفعلة.", update.message.message_id)
    return ConversationHandler.END

async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_alerts = [a for a in alerts_db if a['user_id'] == user_id and a['active']]
    
    if not user_alerts:
        await send_custom_msg(update.message.chat_id, "🔕 لا توجد لديك أي تنبيهات مفعلة حالياً.\n\nلتفعيل تنبيه جديد ارسل: /نبهني", update.message.message_id)
        return
        
    msg = "🔔 <b>تنبيهاتك الحالية:</b>\n\n"
    for idx, a in enumerate(user_alerts, 1):
        dir_emoji = "📈 (صعود)" if a['direction'] == 'up' else "📉 (نزول)"
        msg += f"{idx}. <b>{a['curr_name']}</b> - السعر المطلوب: <code>{a['target']:g}</code> {dir_emoji}\n"
        
    msg += "\nلإيقاف جميع تنبيهاتك ارسل: /ايقاف"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)

async def check_alerts_loop(app: Application):
    global alerts_db 
    while True:
        await asyncio.sleep(10) 
        if not alerts_db:
            continue
            
        success = await update_prices_if_needed()
        if not success: continue
        
        triggered_alerts = []
        for alert in alerts_db:
            if not alert['active']: continue
            
            curr_price = get_current_price(alert['currency'])
            if curr_price == 0: continue
            
            triggered = False
            if alert['direction'] == 'up' and curr_price >= alert['target']: triggered = True
            elif alert['direction'] == 'down' and curr_price <= alert['target']: triggered = True
                
            if triggered:
                triggered_alerts.append(alert)
                alert['active'] = False
        
        if triggered_alerts:
            grouped = {}
            for alert in triggered_alerts:
                chat_id = alert['chat_id']
                if chat_id not in grouped: grouped[chat_id] = {}
                curr_code = alert['currency']
                if curr_code not in grouped[chat_id]: grouped[chat_id][curr_code] = []
                grouped[chat_id][curr_code].append(alert)
            
            for chat_id, currencies in grouped.items():
                for curr_code, alerts in currencies.items():
                    mentions = " ".join([f"<a href='tg://user?id={a['user_id']}'>{a['name']}</a>" for a in alerts])
                    curr_name = alerts[0]['curr_name']
                    curr_val = get_current_price(curr_code)
                    
                    msg = f"🚨 {mentions}\n\n"
                    msg += f"🔥 <b>الحگ! الـ {curr_name} وصل للسعر المطلوب!</b> <tg-emoji emoji-id=\"5215372534060428125\">🔔</tg-emoji>\n"
                    msg += f"السعر الحالي: <b>{curr_val:g}</b>\n\n"
                    msg += f"لإيقاف التنبيهات ارسل /ايقاف"
                    
                    await send_custom_msg(chat_id, msg)
                        
        alerts_db = [a for a in alerts_db if a['active']]

async def post_init(app: Application):
    asyncio.create_task(check_alerts_loop(app))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip().lower()
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    msg_id = update.message.message_id # نحفظ الآي دي لرسالة المستخدم
    
    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text for word in forbidden): return

    # --- ميزة: رصيدي ---
    if text in ["رصيدي", "/رصيدي", "رص", "/رص"]:
        if user_id not in user_wallets:
            msg = "لم تقم بربط محفضتك بالبوت <tg-emoji emoji-id=\"5213195952008997792\">⚠️</tg-emoji>"
            btn = [[{
                "text": "ربط محفضتي", 
                "url": f"https://t.me/{context.bot.username}?start=link_wallet", 
                "style": "success",
                "icon_custom_emoji_id": "5409150983030728043"
            }]]
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        else:
            address = user_wallets[user_id]
            is_valid, ton_bal, usdt_bal = await check_ton_wallet(address)
            
            if is_valid:
                msg = (f"الان لديك  :\n"
                       f"TON <tg-emoji emoji-id=\"5321330914851040564\">💎</tg-emoji>: {ton_bal:.2f}\n"
                       f"USDT <tg-emoji emoji-id=\"5213170203680060059\">💵</tg-emoji>: {usdt_bal:.2f}")
                await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
            else:
                await send_custom_msg(chat_id, "⚠️ عذراً، يبدو أن هناك مشكلة في محفظتك المربوطة. قم بتغييرها.", reply_to_message_id=msg_id)
        return
        
    # --- ميزة: تغيير محفظتي (الرد المباشر) ---
    if text in ["تغيير محفظتي", "/تغيير محفظتي", "تغيير محفضتي", "/تغيير محفضتي"]:
        msg = "اضغط على الزر أدناه لتغيير محفظتك المربوطة:"
        btn = [[{
            "text": "ربط محفضتي", 
            "url": f"https://t.me/{context.bot.username}?start=change_wallet", 
            "style": "success",
            "icon_custom_emoji_id": "5409150983030728043"
        }]]
        # هنا ضفنا الـ reply_to_message_id حتى يرد على رسالة المستخدم
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        return

    calc_pattern = r'(?:صرف|سعر|حساب)?\s*(\d+(?:\.\d+)?)\s*(تون|ton|دولار|usdt|usd|ماستر|بتكوين|بيتكوين|btc|bitcoin|ايثيريوم|إيثيريوم|eth|ethereum|سولانا|sol|solana|نجمه|نجمة|نجوم|star|stars|نج)'
    calc_match = re.search(calc_pattern, text)
    if calc_match:
        amount = float(calc_match.group(1)); currency_str = calc_match.group(2)
        await update_prices_if_needed()
        reply = generate_conversion_msg(amount, currency_str)
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)
        return

    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol", "ماستر", "نجوم", "نجمة", "نج"]
    is_allowed = False
    if text in ["ص", "صر", "صرف", "تون", "دولار", "ماستر", "نجوم", "نجمة", "نج"]: is_allowed = True
    elif any(phrase in text for phrase in ["صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار"]): is_allowed = True
    elif any(word == text for word in allowed_keywords): is_allowed = True

    if is_allowed:
        await update_prices_if_needed()
        reply = cached_msg if cached_msg else "⚠️ عذراً، حاول ثواني.."
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال مع حاسبة الصرافة، التنبيهات، ومراقبة المحفظة 🔥"
def run_web():
    port = int(os.environ.get("PORT", 8000))
    web_app.run(host="0.0.0.0", port=port)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    time.sleep(8)

    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)

    app = (
        Application.builder()
        .token(TOKEN)
        .request(t_request)
        .post_init(post_init) 
        .build()
    )
    
    alert_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^/?نبهني$'), alert_start)],
        states={
            ASK_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_currency)],
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price)]
        },
        fallbacks=[MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts)],
        per_chat=True,
        per_user=True
    )
    
    wallet_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_wallet_flow)
        ],
        states={
            ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet_address)]
        },
        fallbacks=[],
        map_to_parent=None
    )
    
    app.add_handler(alert_conv_handler)
    app.add_handler(wallet_conv_handler)
    app.add_handler(MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts))
    app.add_handler(MessageHandler(filters.Regex(r'^/?تنبيهاتي$'), my_alerts)) 
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
