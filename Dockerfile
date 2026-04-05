# استخدام نسخة Node.js المستقرة والخالية من الأخطاء
FROM node:20

# تحديد مسار العمل
WORKDIR /usr/src/app

# تثبيت cmake المطلوب لبناء مكتبة ماين كرافت الجوال
RUN apt-get update && apt-get install -y cmake

# نسخ قائمة المكاتب وتثبيتها
COPY package*.json ./
RUN npm install

# نسخ باقي الملفات
COPY . .

# فتح المنفذ المطلوب
EXPOSE 7860

# أمر التشغيل
CMD [ "node", "server.js" ]
