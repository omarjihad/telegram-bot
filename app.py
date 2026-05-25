import os
import time
import aiohttp
import logging
import threading
import asyncio
import re
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, ConversationHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# إعدادات اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = '8679057078:AAH27klAkXPLu9bWVr-_jhmg06gdYvefVps'

# --- نظام الإدارة والمستخدمين ---
ADMINS = {7126816492, 1955081272}
BANNED_USERS = set()
FORCE_SUB_CHANNEL = None 
total_users = set() 

# نظام الكاش والبيانات
CACHE_TIME = 5
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000
crypto_prices = {'BTC': 0, 'TON': 0, 'ETH': 0, 'SOL': 0}
alerts_db = []
user_wallets = {} 

# حالات المحادثة
ASK_CURRENCY, ASK_PRICE = range(2)
ASK_WALLET = 3 
WAIT_BROADCAST, WAIT_BAN, WAIT_UNBAN, WAIT_FORCE_SUB = range(4, 8)

# --- دوال الإشعارات والتحقق ---
async def notify_admins(context, text):
    for admin_id in ADMINS:
        try: await context.bot.send_message(chat_id=admin_id, text=text, parse_mode='HTML')
        except Exception: pass

async def check_new_user(user, context, is_calc=False):
    if user.id not in total_users:
        if is_calc: return 
        total_users.add(user.id)
        msg = (f"👤 <b>دخل شخص جديد!</b>\n"
               f"الاسم: {user.first_name}\n"
               f"اليوزر: @{user.username if user.username else 'لا يوجد'}\n"
               f"عدد المستخدمين الان: {len(total_users)}")
        await notify_admins(context, msg)

async def is_force_sub_ok(update, context, reply_to_id=None):
    global FORCE_SUB_CHANNEL
    if not FORCE_SUB_CHANNEL: return True
    user_id = update.message.from_user.id
    if user_id in ADMINS: return True
    
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
        if member.status in ['left', 'kicked']:
            msg = f"⚠️ <b>عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدام أوامره.</b>"
            btn = [[{"text": "📢 اشترك في القناة", "url": f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}", "style": "primary"}]]
            await send_custom_msg(update.message.chat_id, msg, reply_to_message_id=reply_to_id, extra_buttons=btn)
            return False
        return True
    except Exception: return True 

# --- دوال الإرسال السريعة والمضمونة ---
async def send_custom_msg(chat_id, text, reply_to_message_id=None, extra_buttons=None, bot_username=None, show_group_btn=False):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    inline_keyboard = []
    
    if extra_buttons: inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "💵 اخبار الفلوس", 
            "url": "https://t.me/Guidance_nft", 
            "style": "danger"
        }
    ])
    
    if show_group_btn and bot_username:
        inline_keyboard.append([
            {"text": "➕ اضافه البوت الى مجموعتي", "url": f"https://t.me/{bot_username}?startgroup=admin=post_messages+edit_messages+delete_messages+invite_users", "style": "primary"}
        ])

    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}}
    if reply_to_message_id: payload["reply_parameters"] = {"message_id": reply_to_message_id}
        
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", {}).get("message_id")
        except Exception: pass
    return None

async def edit_custom_msg(chat_id, message_id, text, extra_buttons=None):
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    inline_keyboard = []
    if extra_buttons: inline_keyboard.extend(extra_buttons)
        
    inline_keyboard.append([
        {
            "text": "💵 اخبار الفلوس", 
            "url": "https://t.me/Guidance_nft", 
            "style": "danger"
        }
    ])

    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}}
    async with aiohttp.ClientSession() as session:
        try: await session.post(url, json=payload, timeout=10)
        except Exception: pass

# --- لوحة تحكم الإدارة (Admin Panel) ---
def get_cancel_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("إلغاء ❌", callback_data='admin_cancel')]])

async def send_admin_panel(update: Update, edit_msg=False):
    keyboard = [
        [InlineKeyboardButton("📢 إذاعة", callback_data='admin_broadcast'), InlineKeyboardButton("🔔 اشتراك إجباري", callback_data='admin_forcesub')],
        [InlineKeyboardButton("🚫 حظر شخص", callback_data='admin_ban'), InlineKeyboardButton("✅ فك حظر", callback_data='admin_unban')],
        [InlineKeyboardButton("📊 إحصائيات", callback_data='admin_stats'), InlineKeyboardButton("❌ إغلاق", callback_data='admin_close')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👑 <b>لوحة تحكم المالكين</b>\nاختر الإجراء المطلوب من الأزرار أدناه:"
    
    if edit_msg: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMINS:
        await query.answer("⚠️ هذه الأزرار مخصصة للمالكين فقط!", show_alert=True)
        return ConversationHandler.END
        
    await query.answer()
    data = query.data

    if data == 'admin_cancel':
        await send_admin_panel(update, edit_msg=True)
        return ConversationHandler.END
    elif data == 'admin_broadcast':
        await query.edit_message_text("📢 أرسل الآن الرسالة التي تريد إذاعتها لجميع المستخدمين:", reply_markup=get_cancel_button())
        return WAIT_BROADCAST
    elif data == 'admin_ban':
        await query.edit_message_text("🚫 أرسل الآن آيدي (ID) الشخص الذي تريد حظره:", reply_markup=get_cancel_button())
        return WAIT_BAN
    elif data == 'admin_unban':
        await query.edit_message_text("✅ أرسل الآن آيدي (ID) الشخص لفك الحظر عنه:", reply_markup=get_cancel_button())
        return WAIT_UNBAN
    elif data == 'admin_forcesub':
        msg = ("🔔 <b>الاشتراك الإجباري</b>\n\n"
               "أولاً: أضف البوت كمشرف (Admin) في القناة أو المجموعة.\n"
               "ثانياً: أرسل معرف القناة (مثال: @YourChannel).\n\n"
               "<i>لإيقاف الاشتراك الإجباري أرسل كلمة: ايقاف</i>")
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_cancel_button())
        return WAIT_FORCE_SUB
    elif data == 'admin_stats':
        global FORCE_SUB_CHANNEL
        sub_status = FORCE_SUB_CHANNEL if FORCE_SUB_CHANNEL else "معطل"
        stats = f"📊 <b>إحصائيات البوت:</b>\n\n👥 عدد المستخدمين الكلي: <b>{len(total_users)}</b>\n🚫 المحظورين: <b>{len(BANNED_USERS)}</b>\n📢 الاشتراك الإجباري: <b>{sub_status}</b>\n💎 تنبيهات مفعلة: <b>{len([a for a in alerts_db if a['active']])}</b>"
        await query.edit_message_text(stats, parse_mode='HTML', reply_markup=get_cancel_button())
        return ConversationHandler.END
    elif data == 'admin_close':
        await query.edit_message_text("تم إغلاق لوحة التحكم.")
        return ConversationHandler.END

async def admin_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    await update.message.reply_text(f"⏳ جاري الإذاعة لـ {len(total_users)} مستخدم...")
    count = 0
    for uid in total_users.copy():
        try:
            await send_custom_msg(uid, f"📢 <b>رسالة إدارية:</b>\n\n{msg}")
            count += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await update.message.reply_text(f"✅ تمت الإذاعة بنجاح لـ {count} مستخدم.")
    return ConversationHandler.END

async def admin_do_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: target = int(update.message.text.strip())
    except ValueError: 
        await update.message.reply_text("آيدي غير صالح، تم الإلغاء.")
        return ConversationHandler.END
    BANNED_USERS.add(target)
    await update.message.reply_text(f"✅ تم حظر المستخدم {target} بنجاح.")
    return ConversationHandler.END

async def admin_do_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: target = int(update.message.text.strip())
    except ValueError: 
        await update.message.reply_text("آيدي غير صالح، تم الإلغاء.")
        return ConversationHandler.END
    if target in BANNED_USERS: BANNED_USERS.remove(target)
    await update.message.reply_text(f"✅ تم فك حظر المستخدم {target} بنجاح.")
    return ConversationHandler.END

async def admin_do_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FORCE_SUB_CHANNEL
    msg = update.message.text.strip()
    
    if msg == 'ايقاف':
        FORCE_SUB_CHANNEL = None
        await update.message.reply_text("✅ تم إيقاف الاشتراك الإجباري بنجاح.")
        return ConversationHandler.END
        
    if not msg.startswith('@') and not msg.startswith('-100'): msg = '@' + msg
        
    try:
        bot_member = await context.bot.get_chat_member(chat_id=msg, user_id=context.bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("⚠️ البوت ليس مشرفاً في هذه القناة! يرجى رفعه كأدمن أولاً ثم المحاولة مجدداً.")
            return ConversationHandler.END
            
        FORCE_SUB_CHANNEL = msg
        await update.message.reply_text(f"✅ تم تفعيل الاشتراك الإجباري للقناة: {FORCE_SUB_CHANNEL}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء التحقق. تأكد من المعرف وأن البوت مشرف.\nالخطأ: {e}")
        
    return ConversationHandler.END

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
    except Exception: return False, 0, 0

# --- نظام تحديث الأسعار (كاش + خلفية) ---
async def fetch_mastercard_price(session):
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {"Content-Type": "application/json"}
        payload = {"fiat": "IQD", "page": 1, "rows": 1, "tradeType": "BUY", "asset": "USDT", "countries": [], "payTypes": [], "publisherType": None, "merchantCheck": False}
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0: return str(int(float(data['data'][0]['adv']['price']) * 100))
    except Exception: pass
    return None

async def update_prices_if_needed():
    """تحديث الأسعار عند الطلب مع كاش لمدة CACHE_TIME ثانية"""
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

            if isinstance(master_price_str, str) and master_price_str.isdigit(): last_known_iqd = int(master_price_str)

            btc_int = int(crypto_prices['BTC']); ton_val = crypto_prices['TON']
            eth_int = int(crypto_prices['ETH']); sol_val = crypto_prices['SOL']

            cached_msg = (f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                   f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): \u2067<b>{last_known_iqd:,}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc_int:,}</b>\n'
                   f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: <b>${ton_val:,.2f}</b>\n'
                   f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: <b>${eth_int:,}</b>\n'
                   f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: <b>${sol_val:,.2f}</b>\n'
                   "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                   f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية والمحلية</i>\n'
                   f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>')
            last_fetch_time = current_time
            return True
    except Exception: return False

async def background_price_updater():
    """تحديث الأسعار في الخلفية كل 5 ثوانٍ"""
    global cached_msg, last_known_iqd, crypto_prices, last_fetch_time
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                crypto_url = 'https://api.binance.com/api/v3/ticker/price?symbols=["BTCUSDT","ETHUSDT","SOLUSDT","TONUSDT"]'
                crypto_task = session.get(crypto_url, timeout=10)
                master_task = fetch_mastercard_price(session)
                response, master_price_str = await asyncio.gather(crypto_task, master_task, return_exceptions=True)
                
                if not isinstance(response, Exception) and response.status == 200:
                    crypto_data = await response.json()
                    prices = {item['symbol']: float(item['price']) for item in crypto_data}
                    crypto_prices['BTC'] = prices.get('BTCUSDT', crypto_prices['BTC'])
                    crypto_prices['TON'] = prices.get('TONUSDT', crypto_prices['TON'])
                    crypto_prices['ETH'] = prices.get('ETHUSDT', crypto_prices['ETH'])
                    crypto_prices['SOL'] = prices.get('SOLUSDT', crypto_prices['SOL'])

                if isinstance(master_price_str, str) and master_price_str.isdigit(): last_known_iqd = int(master_price_str)

                btc_int = int(crypto_prices['BTC']); ton_val = crypto_prices['TON']
                eth_int = int(crypto_prices['ETH']); sol_val = crypto_prices['SOL']

                cached_msg = (f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                       f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): \u2067<b>{last_known_iqd:,}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
                       "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                       f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc_int:,}</b>\n'
                       f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: <b>${ton_val:,.2f}</b>\n'
                       f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: <b>${eth_int:,}</b>\n'
                       f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: <b>${sol_val:,.2f}</b>\n'
                       "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                       f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية والمحلية</i>\n'
                       f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>')
                last_fetch_time = time.time()
        except Exception: pass
        await asyncio.sleep(5)

def get_current_price(curr_code):
    if curr_code == 'USD': return 1.0
    elif curr_code == 'IQD': return last_known_iqd
    elif curr_code == 'STARS': return 0.015
    elif curr_code in crypto_prices: return crypto_prices[curr_code]
    return 0

def generate_conversion_msg(amount, currency_str):
    curr = currency_str.lower().strip()
    if curr in ['دولار', 'usdt', 'usd']: base = 'USD'; name = "دولار (USDT)"; usd_val = amount; show_usd = False  
    elif curr == 'ماستر': base = 'IQD'; name = "ماستر"; actual_iqd = amount * 1000 if amount < 100000 else amount; usd_val = actual_iqd / (last_known_iqd / 100); show_iqd = False  
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: base = 'STARS'; name = '<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم'; usd_val = amount * 0.015 
    elif curr in ['تون', 'ton']: base = 'TON'; name = "تون (TON)"; usd_val = amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: base = 'BTC'; name = "بتكوين (BTC)"; usd_val = amount * crypto_prices.get('BTC', 0)
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']: base = 'ETH'; name = "إيثيريوم (ETH)"; usd_val = amount * crypto_prices.get('ETH', 0)
    elif curr in ['سولانا', 'sol', 'solana']: base = 'SOL'; name = "سولانا (SOL)"; usd_val = amount * crypto_prices.get('SOL', 0)
    else: return "⚠️ عذراً، العملة غير مدعومة."

    if usd_val == 0: return "⚠️ عذراً، لا يمكن حساب القيمة الآن. يرجى المحاولة بعد ثانية."

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
def normalize_currency_msg(curr_str):
    curr = curr_str.lower().strip()
    if curr in ['دولار', 'usdt', 'usd']: return 'USD'
    elif curr == 'ماستر': return 'IQD'
    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']: return 'STARS'
    elif curr in ['تون', 'ton']: return 'TON'
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']: return 'BTC'
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']: return 'ETH'
    elif curr in ['سولانا', 'sol', 'solana']: return 'SOL'
    return None

async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_force_sub_ok(update, context, update.message.message_id): return ConversationHandler.END
    msg = "🔔 <b>نظام التنبيهات الذكي</b>\n\n👇 <b>الآن، اكتب اسم العملة اللي تريد أراقبها (مثال: تون، بتكوين، ماستر...):</b>"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)
    return ASK_CURRENCY

async def alert_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    curr_input = update.message.text.strip()
    # لو النص يحتوي على أرقام، حوله للحاسبة
    if re.search(r'\d', curr_input):
        await update.message.reply_text("💡 جارٍ تحويل الطلب إلى الحاسبة...")
        return await handle_message(update, context)

    if curr_input.startswith('/ايقاف') or curr_input == 'ايقاف': return await stop_alerts(update, context)
    curr_code = normalize_currency_msg(curr_input)
    if not curr_code:
        await send_custom_msg(update.message.chat_id, "⚠️ عذراً، العملة غير مدعومة. يرجى كتابة اسم عملة صحيح:", update.message.message_id)
        return ASK_CURRENCY
    context.user_data['alert_curr'] = curr_code
    context.user_data['alert_curr_name'] = curr_input
    await send_custom_msg(update.message.chat_id, f"✅ تم اختيار: <b>{curr_input}</b>\n\n✍️ الآن ادخل السعر للوصول إليه (أرقام فقط):", update.message.message_id)
    return ASK_PRICE

async def alert_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_input = update.message.text.strip()
    if price_input.startswith('/ايقاف') or price_input == 'ايقاف': return await stop_alerts(update, context)
    match = re.search(r'(\d+(?:\.\d+)?)', price_input)
    if not match:
        await send_custom_msg(update.message.chat_id, "⚠️ يرجى إدخال رقم صحيح:", update.message.message_id)
        return ASK_PRICE
        
    target_price = float(match.group(1)); curr_code = context.user_data['alert_curr']; curr_name = context.user_data['alert_curr_name']
    
    current_price = get_current_price(curr_code)
    if current_price == 0:
        await send_custom_msg(update.message.chat_id, "⚠️ لا يمكن جلب السعر الحالي. الرجاء المحاولة بعد قليل.", update.message.message_id)
        return ConversationHandler.END
        
    direction = 'up' if target_price > current_price else 'down'
    alerts_db.append({'user_id': update.message.from_user.id, 'name': update.message.from_user.first_name, 'chat_id': update.message.chat_id, 'currency': curr_code, 'curr_name': curr_name, 'target': target_price, 'direction': direction, 'active': True})
    
    dir_text = "صعود 📈" if direction == 'up' else "نزول 📉"
    await send_custom_msg(update.message.chat_id, f"✅ <b>تم التفعيل!</b>\nسيتم تنبيهك عند {dir_text} الـ {curr_name} إلى <code>{target_price:g}</code>", update.message.message_id)
    return ConversationHandler.END

async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global alerts_db
    user_id = update.message.from_user.id
    alerts_db = [a for a in alerts_db if a['user_id'] != user_id]
    await send_custom_msg(update.message.chat_id, "🛑 تم إيقاف جميع تنبيهاتك بنجاح.", update.message.message_id)
    return ConversationHandler.END

async def my_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_alerts = [a for a in alerts_db if a['user_id'] == user_id and a['active']]
    if not user_alerts:
        await send_custom_msg(update.message.chat_id, "🔕 لا توجد لديك أي تنبيهات مفعلة حالياً.", update.message.message_id)
        return
    msg = "🔔 <b>تنبيهاتك الحالية:</b>\n\n"
    for idx, a in enumerate(user_alerts, 1):
        dir_emoji = "📈" if a['direction'] == 'up' else "📉"
        msg += f"{idx}. <b>{a['curr_name']}</b> - السعر: <code>{a['target']:g}</code> {dir_emoji}\n"
    await send_custom_msg(update.message.chat_id, msg, update.message.message_id)

async def check_alerts_loop(app: Application):
    global alerts_db 
    while True:
        await asyncio.sleep(10) 
        if not alerts_db: continue
        
        triggered_alerts = []; new_db = []
        for alert in alerts_db:
            if not alert['active']: continue
            curr_price = get_current_price(alert['currency'])
            if curr_price == 0: new_db.append(alert); continue
            
            triggered = False
            if alert['direction'] == 'up' and curr_price >= alert['target']: triggered = True
            elif alert['direction'] == 'down' and curr_price <= alert['target']: triggered = True
                
            if triggered: triggered_alerts.append(alert)
            else: new_db.append(alert)
        
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
                    curr_name = alerts[0]['curr_name']; curr_val = get_current_price(curr_code)
                    msg = (f"🚨 {mentions}\n\n"
                           f"🔥 <b>الحگ! الـ {curr_name} وصل للسعر المطلوب!</b> <tg-emoji emoji-id=\"5215372534060428125\">🔔</tg-emoji>\n"
                           f"السعر الحالي: <b>{curr_val:g}</b>\n\n"
                           f"لإيقاف التنبيهات ارسل /ايقاف")
                    await send_custom_msg(chat_id, msg)
        alerts_db = new_db

async def post_init(app: Application):
    asyncio.create_task(background_price_updater())
    asyncio.create_task(check_alerts_loop(app))

# --- معالجة إضافة المجموعة والأوامر الرئيسية ---
async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            chat = update.message.chat
            link = f"@{chat.username}" if chat.username else "مجموعة خاصة"
            admin_msg = (f"🚀 <b>تم إضافة البوت لكروب جديد!</b>\n"
                         f"اسم الكروب: {chat.title}\n"
                         f"الرابط/المعرف: {link}")
            await notify_admins(context, admin_msg)
            await send_custom_msg(chat.id, "تم تشغيل البوت اكتب الاوامر او اوامر لعرض الشرح")

async def start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.message.from_user
    chat_id = update.message.chat_id
    
    if user.id in BANNED_USERS: return ConversationHandler.END
    if not await is_force_sub_ok(update, context, update.message.message_id): return ConversationHandler.END
    
    if text == '/start':
        await check_new_user(user, context)
        if update.message.chat.type == "private":
            msg = (f"أهلاً بك يا <b>{user.first_name}</b> في بوت الصرافة المتقدم 🤖💰\n\n"
                   "<b>الخدمات التي يقدمها البوت:</b>\n"
                   "• حساب أسعار العملات الرقمية والمحلية.\n"
                   "• ربط محفظة TON وعرض رصيدك بداخلها.\n"
                   "• نظام تنبيهات ذكي للأسعار يصلك كإشعار.\n\n"
                   "⚠️ <b>أرسل كلمة (الاوامر) او (اوامر) لعرض الشرح الكامل.</b>")
            await send_custom_msg(chat_id, msg, bot_username=context.bot.username, show_group_btn=True)
            if user.id in ADMINS: await send_admin_panel(update)
        else:
            await send_custom_msg(chat_id, "أهلاً بك! اكتب `اوامر` لعرض الشرح.", bot_username=context.bot.username, show_group_btn=True)
        return ConversationHandler.END

    await check_new_user(user, context)
    if 'link_wallet' in text:
        if user.id in user_wallets:
            msg = "لديك محفضه مربوطه بالفعل\nلتغيير محفضتك اضغط على الزر ادناه  :"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success", "icon_custom_emoji_id": "5409150983030728043"}]]
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

async def receive_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    msg_id = await send_custom_msg(chat_id, "يتم البحث عن محفضتك... <tg-emoji emoji-id=\"5411597774359653692\">🔍</tg-emoji>")
    is_valid, _, _ = await check_ton_wallet(address)
    
    if is_valid:
        await asyncio.sleep(1)
        await edit_custom_msg(chat_id, msg_id, "جاري ربط المحفضه بالبوت... <tg-emoji emoji-id=\"5215484787325676090\">⏳</tg-emoji>")
        await asyncio.sleep(1)
        user_wallets[user_id] = address
        await edit_custom_msg(chat_id, msg_id, "تم ربط محفضتك بنجاح  . <tg-emoji emoji-id=\"5215492745900077682\">✅</tg-emoji>")
    else:
        await asyncio.sleep(1)
        await edit_custom_msg(chat_id, msg_id, "عنوان المحفضه خطا ! <tg-emoji emoji-id=\"5215204871422093648\">❌</tg-emoji>")
        
    return ConversationHandler.END

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    text_lower = text.lower()
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    msg_id = update.message.message_id 

    # أوامر الانضمام والعرض الخاصة بالمالكين
    if text == "/join 91om20ar":
        ADMINS.add(user_id)
        await update.message.reply_text("✅ تم إضافتك لقائمة المالكين! ستتلقى الإشعارات من الآن.")
        return

    if text == "عرض الكود":
        if user_id in ADMINS:
            code_msg = "الكود الخاص بانضمام المالكين:\n\n<code>/join 91om20ar</code>"
            if update.message.chat.type == "private":
                await send_custom_msg(chat_id, code_msg)
            else:
                await send_custom_msg(chat_id, "تم ارسال الكود في الخاص لضمان السرية 🔒", reply_to_message_id=msg_id)
                try: await context.bot.send_message(chat_id=user_id, text=code_msg, parse_mode='HTML')
                except: pass
        else:
            await send_custom_msg(chat_id, "توكل لك هذا الامر مو للفاشلين مثلك\nالامر للمالك  : @M6M9N", reply_to_message_id=msg_id)
        return

    if user_id in BANNED_USERS: return
    
    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word == text_lower for word in forbidden): return

    # الأولوية 1: العمليات الحسابية (مثل 3 تون) - تحديث السعر أولاً
    calc_pattern = r'(?:صرف|سعر|حساب)?\s*(\d+(?:\.\d+)?)\s*(تون|ton|دولار|usdt|usd|ماستر|بتكوين|بيتكوين|btc|bitcoin|ايثيريوم|إيثيريوم|eth|ethereum|سولانا|sol|solana|نجمه|نجمة|نجوم|star|stars|نج)'
    calc_match = re.search(calc_pattern, text_lower)
    if calc_match:
        # تحديث فوري للأسعار إذا لزم الأمر (بدلاً من الانتظار حتى الخيط الخلفي)
        await update_prices_if_needed()
        await check_new_user(update.message.from_user, context, is_calc=True)
        amount = float(calc_match.group(1)); currency_str = calc_match.group(2)
        reply = generate_conversion_msg(amount, currency_str)
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)
        return

    # الأوامر الرئيسية
    if text_lower in ["اوامر", "/اوامر", "الاوامر"]:
        if not await is_force_sub_ok(update, context, msg_id): return 
        await check_new_user(update.message.from_user, context)
        msg = (
            "اهلا بك في قائمه اوامر البوت 📋\n\n"
            "<tg-emoji emoji-id=\"5411624647181504938\">1️⃣</tg-emoji> صرف [رقم] [عملة]: لحساب قيمة العملات بشكل مباشر <tg-emoji emoji-id=\"5210956306952758910\">✔️</tg-emoji><tg-emoji emoji-id=\"5958605483488055761\">✨</tg-emoji>\n\n"
            "<tg-emoji emoji-id=\"5411585799990830248\">2️⃣</tg-emoji> نبهني: لمراقبة سعر عملة معينة وتنبيهك عند وصولها للهدف <tg-emoji emoji-id=\"5210956306952758910\">✔️</tg-emoji><tg-emoji emoji-id=\"5958605483488055761\">✨</tg-emoji>\n\n"
            "<tg-emoji emoji-id=\"5409189019261103031\">3️⃣</tg-emoji> تنبيهاتي: لعرض وإدارة التنبيهات المفعلة الخاصة بك <tg-emoji emoji-id=\"5210956306952758910\">✔️</tg-emoji><tg-emoji emoji-id=\"5958605483488055761\">✨</tg-emoji>\n\n"
            "<tg-emoji emoji-id=\"5411500398861118321\">4️⃣</tg-emoji> رصيدي: لمعرفة رصيدك (TON و USDT) في المحفظة المربوطة <tg-emoji emoji-id=\"5210956306952758910\">✔️</tg-emoji><tg-emoji emoji-id=\"5958605483488055761\">✨</tg-emoji>\n\n"
            "<tg-emoji emoji-id=\"5409338071806146386\">5️⃣</tg-emoji> تغيير محفظتي: لربط أو تغيير محفظة TON الخاصة بك <tg-emoji emoji-id=\"5210956306952758910\">✔️</tg-emoji><tg-emoji emoji-id=\"5958605483488055761\">✨</tg-emoji>\n"
        )
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
        return

    if text_lower == "/help":
        if not await is_force_sub_ok(update, context, msg_id): return 
        await check_new_user(update.message.from_user, context)
        msg = (f"أهلاً بك يا <b>{update.message.from_user.first_name}</b> في بوت الصرافة 🤖\n\n"
               "البوت يقدم خدمات حساب أسعار العملات والمحافظ.\n"
               "⚠️ <b>أرسل كلمة (الاوامر) او (اوامر) لعرض الشرح الكامل.</b>")
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, bot_username=context.bot.username, show_group_btn=True)
        return

    if text_lower in ["رصيدي", "/رصيدي", "رص", "/رص"]:
        if not await is_force_sub_ok(update, context, msg_id): return 
        await check_new_user(update.message.from_user, context)
        if user_id not in user_wallets:
            msg = "لم تقم بربط محفضتك بالبوت <tg-emoji emoji-id=\"5213195952008997792\">⚠️</tg-emoji>"
            btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=link_wallet", "style": "success", "icon_custom_emoji_id": "5409150983030728043"}]]
            await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        else:
            address = user_wallets[user_id]
            is_valid, ton_bal, usdt_bal = await check_ton_wallet(address)
            if is_valid:
                msg = (f"الان لديك  :\n"
                       f"TON <tg-emoji emoji-id=\"5321330914851040564\">💎</tg-emoji>: {ton_bal:.2f}\n"
                       f"USDT <tg-emoji emoji-id=\"5213170203680060059\">💵</tg-emoji>: {usdt_bal:.2f}")
                await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id)
            else: await send_custom_msg(chat_id, "⚠️ عذراً، يبدو أن هناك مشكلة في محفظتك المربوطة. قم بتغييرها.", reply_to_message_id=msg_id)
        return
        
    if text_lower in ["تغيير محفظتي", "/تغيير محفظتي", "تغيير محفضتي", "/تغيير محفضتي"]:
        if not await is_force_sub_ok(update, context, msg_id): return 
        await check_new_user(update.message.from_user, context)
        msg = "اضغط على الزر أدناه لتغيير محفظتك المربوطة:"
        btn = [[{"text": "ربط محفضتي", "url": f"https://t.me/{context.bot.username}?start=change_wallet", "style": "success", "icon_custom_emoji_id": "5409150983030728043"}]]
        await send_custom_msg(chat_id, msg, reply_to_message_id=msg_id, extra_buttons=btn)
        return

    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol", "ماستر", "نجوم", "نجمة", "نج"]
    is_allowed = False
    if text_lower in ["ص", "صر", "صرف", "تون", "دولار", "ماستر", "نجوم", "نجمة", "نج"]: is_allowed = True
    elif any(phrase in text_lower for phrase in ["صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار"]): is_allowed = True
    elif any(word == text_lower for word in allowed_keywords): is_allowed = True

    if is_allowed:
        await update_prices_if_needed()  # تحديث فوري قبل عرض النشرة
        reply = cached_msg if cached_msg else "⚠️ عذراً، جاري تحديث الأسعار، حاول بعد ثواني.."
        await send_custom_msg(chat_id, reply, reply_to_message_id=msg_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Ultra Fast Bot Active 🔥"
def run_web():
    port = int(os.environ.get("PORT", 8000))
    web_app.run(host="0.0.0.0", port=port)

def main():
    threading.Thread(target=run_web, daemon=True).start()
    time.sleep(8)

    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)
    app = Application.builder().token(TOKEN).request(t_request).post_init(post_init).build()
    
    admin_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback_handler, pattern='^admin_')],
        states={
            WAIT_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_broadcast)],
            WAIT_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_ban)],
            WAIT_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_unban)],
            WAIT_FORCE_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_do_force_sub)]
        },
        fallbacks=[CallbackQueryHandler(admin_callback_handler, pattern='^admin_cancel')],
        per_chat=True,
        per_user=True
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
        entry_points=[CommandHandler("start", start_flow)],
        states={ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet_address)]},
        fallbacks=[],
        map_to_parent=None
    )
    
    app.add_handler(admin_conv_handler)
    app.add_handler(alert_conv_handler)
    app.add_handler(wallet_conv_handler)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members)) 
    app.add_handler(MessageHandler(filters.Regex(r'^/?ايقاف$'), stop_alerts))
    app.add_handler(MessageHandler(filters.Regex(r'^/?تنبيهاتي$'), my_alerts)) 
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, handle_message)) 
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل بسرعه فائقة ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
