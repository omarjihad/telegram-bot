import os
import time
import aiohttp
import logging
import threading
import asyncio
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# إعدادات اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# التوكن مالتك
TOKEN = '8679057078:AAH27klAkXPLu9bWVr-_jhmg06gdYvefVps'

# نظام الكاش (5 ثواني)
CACHE_TIME = 5
last_fetch_time = 0
cached_msg = ""
last_known_iqd = 153000

# متغيرات جلوبال لحفظ أسعار العملات
crypto_prices = {'BTC': 0, 'TON': 0, 'ETH': 0, 'SOL': 0}

async def fetch_mastercard_price(session):
    """سحب السعر الرقمي (الماستر) من منصة Binance P2P"""
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        payload = {
            "fiat": "IQD", "page": 1, "rows": 1, "tradeType": "BUY",
            "asset": "USDT", "countries": [], "payTypes": [],
            "publisherType": None, "merchantCheck": False
        }
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    price = data['data'][0]['adv']['price']
                    return str(int(float(price) * 100))
    except Exception as e:
        print(f"⚠️ خطأ بسحب السعر الرقمي: {e}")
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
    except Exception as e:
        print(f"⚠️ خطأ بجلب الأسعار: {e}")
        return False

def generate_conversion_msg(amount, currency_str):
    curr = currency_str.lower()
    
    show_usd = True
    show_iqd = True

    if curr in ['دولار', 'usdt', 'usd']:
        base = 'USD'
        name = "دولار (USDT)"
        usd_val = amount
        show_usd = False  

    elif curr == 'ماستر':
        base = 'IQD'
        name = "ماستر"
        actual_iqd = amount * 1000 if amount < 100000 else amount
        usd_val = actual_iqd / (last_known_iqd / 100)
        show_iqd = False  

    elif curr in ['نجمه', 'نجمة', 'نجوم', 'star', 'stars', 'نج']:
        base = 'STARS'
        name = '<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم'
        usd_val = amount * 0.015 
        
    elif curr in ['تون', 'ton']:
        base = 'TON'
        name = "تون (TON)"
        usd_val = amount * crypto_prices.get('TON', 0)
    elif curr in ['بتكوين', 'بيتكوين', 'btc', 'bitcoin']:
        base = 'BTC'
        name = "بتكوين (BTC)"
        usd_val = amount * crypto_prices.get('BTC', 0)
    elif curr in ['ايثيريوم', 'إيثيريوم', 'eth', 'ethereum']:
        base = 'ETH'
        name = "إيثيريوم (ETH)"
        usd_val = amount * crypto_prices.get('ETH', 0)
    elif curr in ['سولانا', 'sol', 'solana']:
        base = 'SOL'
        name = "سولانا (SOL)"
        usd_val = amount * crypto_prices.get('SOL', 0)
    else:
        return "⚠️ عذراً، العملة غير مدعومة."

    if usd_val == 0:
        return "⚠️ عذراً، لا يمكن حساب القيمة الآن."

    # حساب كل القيم
    iqd_val = (usd_val * last_known_iqd) / 100
    ton_val = usd_val / crypto_prices['TON'] if crypto_prices.get('TON') else 0
    stars_val = usd_val / 0.015 # حساب كمية النجوم
    btc_val = usd_val / crypto_prices['BTC'] if crypto_prices.get('BTC') else 0
    eth_val = usd_val / crypto_prices['ETH'] if crypto_prices.get('ETH') else 0
    sol_val = usd_val / crypto_prices['SOL'] if crypto_prices.get('SOL') else 0

    msg = f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <b>تصريف {amount:g} {name}:</b>\n\n'
    
    if show_usd:
        msg += f'💵 بالدولار: \u2067<b>${usd_val:,.3f}</b>\u2069\n'
        
    if show_iqd:
        msg += f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> بالعراقي: \u2067<b>{iqd_val:,.0f}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
        
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    
    if base != 'TON' and ton_val > 0:
        msg += f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> تون: <b>{ton_val:,.2f}</b> TON\n'
        
    # ضفنا عرض النجوم هنا لأي عملة عدا إذا كانت هي أصلاً نجوم
    if base != 'STARS' and stars_val > 0:
        msg += f'<tg-emoji emoji-id="5951912004590507793">⭐️</tg-emoji> نجوم: <b>{stars_val:,.0f}</b> Stars\n'
        
    if base != 'STARS':
        if base != 'BTC' and btc_val > 0:
            msg += f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> بتكوين: <b>{btc_val:,.6f}</b> BTC\n'
        if base != 'ETH' and eth_val > 0:
            msg += f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> إيثيريوم: <b>{eth_val:,.5f}</b> ETH\n'
        if base != 'SOL' and sol_val > 0:
            msg += f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> سولانا: <b>{sol_val:,.2f}</b> SOL\n'
        
    msg += "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
    msg += f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>'
    
    return msg

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    
    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text for word in forbidden):
        return

    calc_pattern = r'(?:صرف|سعر|حساب)?\s*(\d+(?:\.\d+)?)\s*(تون|ton|دولار|usdt|usd|ماستر|بتكوين|بيتكوين|btc|bitcoin|ايثيريوم|إيثيريوم|eth|ethereum|سولانا|sol|solana|نجمه|نجمة|نجوم|star|stars|نج)'
    calc_match = re.search(calc_pattern, text)
    
    if calc_match:
        amount = float(calc_match.group(1))
        currency_str = calc_match.group(2)
        
        await update_prices_if_needed()
        reply = generate_conversion_msg(amount, currency_str)
        await update.message.reply_text(reply, parse_mode='HTML')
        return

    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol", "ماستر", "نجوم", "نجمة", "نج"]
    is_allowed = False
    
    if text in ["ص", "صر", "صرف", "تون", "دولار", "ماستر", "نجوم", "نجمة", "نج"]:
        is_allowed = True
    elif any(phrase in text for phrase in ["صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار"]):
        is_allowed = True
    elif any(word == text for word in allowed_keywords):
        is_allowed = True

    if is_allowed:
        await update_prices_if_needed()
        reply = cached_msg if cached_msg else "⚠️ عذراً، حاول ثواني.."
        await update.message.reply_text(reply, parse_mode='HTML')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال مع حاسبة الصرافة 🔥"

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
        .build()
    )
    
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت شغال الآن ومستعد للعمل على Koyeb ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
