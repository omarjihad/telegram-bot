import os
import time
import aiohttp
import logging
import threading
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# إعدادات اللوج
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# التوكن مالتك (الجديد)
TOKEN = '8679057078:AAH27klAkXPLu9bWVr-_jhmg06gdYvefVps'

# نظام الكاش (5 ثواني)
CACHE_TIME = 5
last_fetch_time = 0
cached_msg = ""
last_known_iqd = "153000" # سعر افتراضي في حال تأخر بينانس

async def fetch_mastercard_price(session):
    """سحب السعر الرقمي (الماستر) من منصة Binance P2P"""
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        payload = {
            "fiat": "IQD",
            "page": 1,
            "rows": 1,
            "tradeType": "BUY",
            "asset": "USDT",
            "countries": [],
            "payTypes": [], # نخليه فارغ حتى يجيب أفضل سعر رقمي متاح
            "publisherType": None,
            "merchantCheck": False
        }
        async with session.post(url, json=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('data') and len(data['data']) > 0:
                    price = data['data'][0]['adv']['price']
                    # السعر لـ 1 دولار، نضربه في 100 لورقة الدولار
                    return str(int(float(price) * 100))
    except Exception as e:
        print(f"⚠️ خطأ بسحب السعر الرقمي من بينانس: {e}")
    return None

async def get_all_prices():
    global last_fetch_time, cached_msg, last_known_iqd
    current_time = time.time()
    
    if current_time - last_fetch_time < CACHE_TIME and cached_msg:
        return cached_msg
        
    try:
        async with aiohttp.ClientSession() as session:
            # رابط API بينانس للكريبتو
            crypto_url = 'https://api.binance.com/api/v3/ticker/price?symbols=["BTCUSDT","ETHUSDT","SOLUSDT","TONUSDT"]'
            
            crypto_task = session.get(crypto_url, timeout=10)
            master_task = fetch_mastercard_price(session)
            
            response, master_price_str = await asyncio.gather(
                crypto_task, master_task, return_exceptions=True
            )
            
            btc = ton = eth = sol = 0
            if not isinstance(response, Exception) and response.status == 200:
                crypto_data = await response.json()
                prices = {item['symbol']: float(item['price']) for item in crypto_data}
                
                btc = int(prices.get('BTCUSDT', 0))
                ton = round(prices.get('TONUSDT', 0), 2)
                eth = int(prices.get('ETHUSDT', 0))
                sol = round(prices.get('SOLUSDT', 0), 2)

            # تحديث السعر إذا تم جلبه بنجاح من بينانس
            if isinstance(master_price_str, str) and master_price_str.isdigit():
                last_known_iqd = master_price_str
                
            usd_iqd_int = int(last_known_iqd)

            # الكليشة الأصلية مالتك بدون أي سطر زايد
            msg = (
                f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): \u2067<b>{usd_iqd_int:,}</b> IQD <tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\u2069\n'
                "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: <b>${btc:,}</b>\n'
                f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: <b>${ton}</b>\n'
                f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: <b>${eth:,}</b>\n'
                f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: <b>${sol}</b>\n'
                "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية والمحلية</i>\n'
                f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji> | <b>الروسي</b>'
            )
            
            cached_msg = msg
            last_fetch_time = current_time
            return msg
    except Exception as e:
        print(f"⚠️ خطأ بجلب الأسعار: {e}")
        return cached_msg if cached_msg else "⚠️ عذراً، حاول ثواني.."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    
    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text for word in forbidden):
        return

    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol"]
    
    is_allowed = False
    if text in ["ص", "صر", "صرف", "تون", "دولار"]:
        is_allowed = True
    elif any(phrase in text for phrase in ["صرف العملات", "اسعار العملات", "أسعار العملات", "صرف دولار", "صرف الدولار"]):
        is_allowed = True
    elif any(word == text for word in allowed_keywords):
        is_allowed = True

    if is_allowed:
        prices_msg = await get_all_prices()
        await update.message.reply_text(prices_msg, parse_mode='HTML')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ ظهر خطأ بالبوت: {context.error}")

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال 🔥"

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
