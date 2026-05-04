import time
import aiohttp
import logging
import threading
import re
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# إعدادات تسجيل الأخطاء بصمت
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.ERROR)

TOKEN = '8679057078:AAF0KIf-GtSSMPoHovqeOiiaM80CmDy8GGY'

# نظام الكاش (10 ثواني) لضمان أقصى سرعة بدون حظر السيرفر
CACHE_TIME = 10
last_fetch_time = 0
cached_msg = ""
last_known_iqd = "152000" # قيمة افتراضية في حال تأخرت القناة

async def fetch_iqd_price(session):
    """دالة مخصصة لسحب سعر الدولار من القناة مباشرة"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with session.get("https://t.me/s/borsat_alkfah", headers=headers, timeout=5) as response:
            html = await response.text()
            # استخراج نصوص الرسائل من الـ HTML
            texts = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
            if texts:
                # نبحث من الأحدث للأقدم
                for text in reversed(texts):
                    clean_text = re.sub(r'<[^>]+>', '', text) # تنظيف النص من أكواد HTML
                    # استخراج أي رقم مكون من 5 أو 6 مراتب (مثل 152600 أو 152,600)
                    match = re.search(r'(\d{3}(?:,\d{3})*|\d{5,6})', clean_text)
                    if match:
                        return match.group(1).replace(',', '') # إرجاع الرقم الصافي
    except Exception:
        pass
    return None

async def get_all_prices():
    global last_fetch_time, cached_msg, last_known_iqd
    current_time = time.time()
    
    if current_time - last_fetch_time < CACHE_TIME and cached_msg:
        return cached_msg
        
    try:
        async with aiohttp.ClientSession() as session:
            crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,the-open-network,ethereum,solana&vs_currencies=usd"
            
            # جلب أسعار الكريبتو وسعر الدينار في نفس اللحظة للحصول على أقصى سرعة
            crypto_task = session.get(crypto_url, timeout=10)
            iqd_task = fetch_iqd_price(session)
            
            response, iqd_price_str = await asyncio.gather(crypto_task, iqd_task, return_exceptions=True)
            
            crypto_data = await response.json()
            btc = crypto_data.get('bitcoin', {}).get('usd', 0)
            ton = crypto_data.get('the-open-network', {}).get('usd', 0)
            eth = crypto_data.get('ethereum', {}).get('usd', 0)
            sol = crypto_data.get('solana', {}).get('usd', 0)

            # تحديث السعر إذا تم جلبه بنجاح من القناة
            if isinstance(iqd_price_str, str) and iqd_price_str.isdigit():
                last_known_iqd = iqd_price_str
                
            usd_iqd_int = int(last_known_iqd)

            # التصميم مع الأرقام الغامقة واسم المطور
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
    except Exception:
        return cached_msg if cached_msg else "⚠️ عذراً، حاول ثواني.."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    
    # 1. الكلمات الممنوعة
    forbidden = ["الو", "يا", "بوت", "شلونك", "منو", "اسمع"]
    if any(word in text for word in forbidden):
        return

    # 2. الكلمات المسموحة
    allowed_keywords = ["صرف", "سعر", "اسعار", "أسعار", "دولار", "بتكوين", "تون", "ايثيريوم", "سولانا", "btc", "ton", "sol"]
    
    # 3. الفحص
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
    pass # تجاوز أخطاء الشبكة بصمت

# سيرفر وهمي للاستضافة
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "البوت شغال 🔥"

def run_web():
    web_app.run(host="0.0.0.0", port=7860)

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
    
    print("--- البوت شغال الآن بأفضل أداء ---")
    app.run_polling(drop_pending_updates=True, bootstrap_retries=10)

if __name__ == "__main__":
    main()
