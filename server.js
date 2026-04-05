const http = require('http');

// تشغيل البوت الأساسي مالتنا
require('./bot.js');

// خادم وهمي لمنع توقف الاستضافة
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('البوت يعمل بكفاءة يا ساسكي! 🚀');
}).listen(7860, () => {
  console.log('🌐 خادم الويب يعمل على المنفذ 7860...');
});
