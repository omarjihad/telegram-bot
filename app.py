import time
import aiohttp
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest  # الاستدعاء الجديد لحل مشكلة التايم أوت

# إعدادات تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.ERROR)

TOKEN = '8679057078:AAF0KIf-GtSSMPoHovqeOiiaM80CmDy8GGY'

CACHE_TIME = 20
last_fetch_time = 0
cached_msg = ""

async def get_all_prices():
    global last_fetch_time, cached_msg
    current_time = time.time()
    
    if current_time - last_fetch_time < CACHE_TIME and cached_msg:
        return cached_msg
        
    try:
        async with aiohttp.ClientSession() as session:
            crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,the-open-network,ethereum,solana&vs_currencies=usd"
            async with session.get(crypto_url, timeout=10) as response:
                crypto_data = await response.json()
                
                btc = crypto_data['bitcoin']['usd']
                ton = crypto_data['the-open-network']['usd']
                eth = crypto_data['ethereum']['usd']
                sol = crypto_data['solana']['usd']

                usd_iqd = 153000

                msg = (
                    f'<tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji> نشرة الأسعار المباشرة <tg-emoji emoji-id="5197504520921326761">⭐</tg-emoji>\n\n'
                    f'<tg-emoji emoji-id="5334775631366331709">🇮🇶</tg-emoji> الدولار (100$): {usd_iqd:,} IQD \u200f<tg-emoji emoji-id="5850343127621046732">🐸</tg-emoji>\n'
                    "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                    f'<tg-emoji emoji-id="5292058354791756351">🪙</tg-emoji> Bitcoin: ${btc:,}\n'
                    f'<tg-emoji emoji-id="5321330914851040564">💎</tg-emoji> TON: ${ton}\n'
                    f'<tg-emoji emoji-id="6034838120745143682">💠</tg-emoji> Ethereum: ${eth:,}\n'
                    f'<tg-emoji emoji-id="6034974692115221805">☀️</tg-emoji> Solana: ${sol}\n'
                    "╼╼╼╼╼╼╼╼╼╼╼╼╼╼╼\n"
                    f'<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji> <i>يتم التحديث من الأسواق العالمية</i>\n'
                    f'Dev : <tg-emoji emoji-id="4949843327810798325">👨‍💻</tg-emoji>'
                )
                
                cached_msg = msg
                last_fetch_time = current_time
                return msg

    except Exception as e:
        if cached_msg:
            return cached_msg
        return "⚠️ عذراً، اكو ضغط على السيرفر، حاول ثواني.."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        text = update.message.text.lower()

        exact_shortcuts = ["ص", "صر", "صرف", "تون"]
        keywords = ["أسعار العملات", "اسعار العملات", "الأسعار", "السعر", "دولار", "بتكوين", "ايثيريوم", "ايثر", "سولانا", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "ton"]

        if text in exact_shortcuts or any(word in text for word in keywords):
            prices_msg = await get_all_prices()
            await update.message.reply_text(prices_msg, parse_mode='HTML')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"⚠️ رمشة بالنت تم تجاوزها: {context.error}")

# ==========================================
# السيرفر الوهمي
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "البوت شغال 100% يالذيب 🔥"

def run_web():
    web_app.run(host="0.0.0.0", port=7860)
# ==========================================

def main():
    # تشغيل السيرفر الوهمي
    threading.Thread(target=run_web, daemon=True).start()

    # إعطاء السيرفر 5 ثواني حتى تستقر شبكة الإنترنت مالته قبل لا يتصل بالتيليجرام
    print("جاري انتظار استقرار الشبكة...")
    time.sleep(5)

    # إعدادات اتصال مخصصة للشبكات الضعيفة (انتظار 60 ثانية بدل 10 ثواني)
    t_request = HTTPXRequest(connection_pool_size=8, connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=60.0)

    app = (
        Application.builder()
        .token(TOKEN)
        .request(t_request) # ربط الإعدادات المخصصة بالبوت
        .build()
    )
    
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)
    
    print("--- البوت المطور شغال الآن ومستعد للرفع ---")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
