# استخدام نسخة بايثون خفيفة وسريعة
FROM python:3.11-slim

# تحديد مجلد العمل داخل السيرفر
WORKDIR /app

# نسخ ملف المتطلبات وتثبيت المكاتب
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كل ملفات البوت (app.py وباقي الملفات)
COPY . .

# البورت الافتراضي (Koyeb يستخدم 8000)
EXPOSE 8000

# أمر تشغيل البوت
CMD ["python", "app.py"]
