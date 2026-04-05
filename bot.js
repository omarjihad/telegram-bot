'use strict';

process.on('uncaughtException', err => console.error('UncaughtException:', err));
process.on('unhandledRejection', err => console.error('UnhandledRejection:', err));

const { Telegraf, Scenes, session, Markup } = require('telegraf');
const mineflayer = require('mineflayer');
const bedrock    = require('bedrock-protocol');
const db         = require('./database');

// ─── Constants ──────────────────────────────────────────────────────────────
const BOT_TOKEN = '8531009639:AAGy87MDKAWeCpRCLMx81PIpQSu56VIXeKo';
const OWNER_ID  = 7126816492;

// ─── Active MC Connections ──────────────────────────────────────────────────
// Map<serverId, { client, stopped: bool, startedAt: string }>
const activeConnections = new Map();

// ─── Helpers ────────────────────────────────────────────────────────────────
function parseServerAddress(input) {
  input = input.trim().replace(/^(https?:\/\/)?(www\.)?/, '');
  input = input.split('/')[0];
  const match = input.match(/^([a-zA-Z0-9._\-]+):(\d+)$/);
  if (match) return { host: match[1], port: parseInt(match[2]) };
  return { host: input, port: null };
}

function formatUptime(startedAt) {
  if (!startedAt) return 'غير معروف';
  const seconds = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}س ${m}د ${s}ث`;
}

function isOwner(userId)         { return userId === OWNER_ID; }
async function isAdminOrOwner(userId) {
  return isOwner(userId) || await db.isAdmin(userId);
}

async function checkSubscription(ctx) {
  const channels = await db.getAllChannels();
  if (!channels.length) return true;
  for (const ch of channels) {
    try {
      const member = await ctx.telegram.getChatMember(ch.channel_id, ctx.from.id);
      if (['left', 'kicked'].includes(member.status)) return false;
    } catch { return false; }
  }
  return true;
}

async function subscriptionKeyboard() {
  const channels = await db.getAllChannels();
  const buttons  = channels.map(ch => [
    Markup.button.url(
      `📢 ${ch.channel_title || ch.channel_id}`,
      `https://t.me/${ch.channel_id.replace('@', '')}`
    ),
  ]);
  buttons.push([Markup.button.callback('✅ تحققت من الاشتراك', 'check_sub')]);
  return Markup.inlineKeyboard(buttons);
}

function translateMCError(err) {
  const msg = (err?.message || String(err)).toLowerCase();
  if (msg.includes('econnrefused'))                              return '❌ رفض الاتصال. تأكد أن السيرفر شغال وأن IP/Port صحيح.';
  if (msg.includes('enotfound'))                                 return '❌ لم يتم العثور على السيرفر. تحقق من الـ IP.';
  if (msg.includes('etimedout') || msg.includes('timeout'))     return '❌ انتهت مهلة الاتصال. السيرفر لا يستجيب.';
  if (msg.includes('invalid session') || msg.includes('auth'))  return '❌ خطأ في المصادقة. تأكد أن السيرفر في وضع Offline/Cracked.';
  if (msg.includes('kicked'))                                    return '⚠️ تم طرد البوت من السيرفر.';
  if (msg.includes('disconnect'))                                return '⚠️ انقطع الاتصال بالسيرفر.';
  return `❌ خطأ: ${err?.message || err}`;
}

// ─── Minecraft Connection ────────────────────────────────────────────────────
function connectJava(server, onSuccess, onError, onDisconnect) {
  try {
    const client = mineflayer.createBot({
      host:       server.host,
      port:       server.port || 25565,
      username:   server.bot_name || 'MCBot',
      auth:       'offline',   // CRACKED/OFFLINE forced
      version:    false,
      hideErrors: false,
    });

    client.once('spawn', () => onSuccess(client));
    client.on('error',   (err)    => onError(err));
    client.on('kicked',  (reason) => onDisconnect(`kicked: ${reason}`));
    client.on('end',     (reason) => onDisconnect(reason || 'end'));

    // Anti-AFK: jump every 25 s
    client._afkInterval = setInterval(() => {
      try {
        if (client?.entity) {
          client.setControlState('jump', true);
          setTimeout(() => { try { client.setControlState('jump', false); } catch {} }, 500);
        }
      } catch {}
    }, 25000);

    return client;
  } catch (err) {
    onError(err);
    return null;
  }
}

function connectBedrock(server, onSuccess, onError, onDisconnect) {
  try {
    const client = bedrock.createClient({
      host:     server.host,
      port:     server.port || 19132,
      username: server.bot_name || 'MCBot',
      offline:  true,          // CRACKED/OFFLINE forced
      skipPing: true,
    });

    client.on('join',       ()       => onSuccess(client));
    client.on('error',      (err)    => onError(err));
    client.on('disconnect', (packet) => onDisconnect(packet?.message || 'disconnect'));
    client.on('close',      ()       => onDisconnect('close'));

    // Anti-AFK every 25 s
    client._afkInterval = setInterval(() => {
      try {
        client.queue('PlayerAuthInput', {
          pitch: 0, yaw: 0,
          position:     { x: 0, y: 64, z: 0 },
          move_vector:  { x: 0, z: 0 },
          head_yaw:     0,
          input_data:   { jump: true },
          input_mode:   0,
          play_mode:    0,
          interaction_model: 1,
          tick:  BigInt(Date.now()),
          delta: { x: 0, y: 0, z: 0 },
        });
      } catch {}
    }, 25000);

    return client;
  } catch (err) {
    onError(err);
    return null;
  }
}

async function startMinecraftBot(serverId, telegramBot, chatId, messageId) {
  const server = await db.getServer(serverId);
  if (!server) return;

  await db.updateServerStatus(serverId, 'connecting');

  const reconnect = () => {
    const conn = activeConnections.get(serverId);
    if (!conn || conn.stopped) return;
    setTimeout(() => {
      if (activeConnections.get(serverId)?.stopped) return;
      launchConnection();
    }, 5000);
  };

  const launchConnection = async () => {
    const fresh = await db.getServer(serverId);
    if (!fresh) return;

    const onSuccess = async (client) => {
      await db.updateServerStatus(serverId, 'running');
      activeConnections.set(serverId, {
        client,
        stopped:   false,
        startedAt: new Date().toISOString(),
      });

      telegramBot.telegram.editMessageText(
        chatId, messageId, null,
        `✅ انضم البوت بنجاح إلى \`${fresh.host}:${fresh.port || (fresh.type === 'java' ? 25565 : 19132)}\`!`,
        { parse_mode: 'Markdown' }
      ).catch(() => {});

      setTimeout(async () => {
        const s = await db.getServer(serverId);
        if (!s) return;
        telegramBot.telegram.editMessageText(
          chatId, messageId, null,
          buildServerInfoText(s, activeConnections.get(serverId)),
          { parse_mode: 'Markdown', ...serverSettingsKeyboard(s) }
        ).catch(() => {});
      }, 2000);
    };

    const onError = async (err) => {
      console.error(`MC Error [${serverId}]:`, err);
      await db.updateServerStatus(serverId, 'error');
      const conn = activeConnections.get(serverId);
      if (conn) {
        clearInterval(conn.client?._afkInterval);
        conn.stopped = true;
        activeConnections.delete(serverId);
      }
      telegramBot.telegram.sendMessage(chatId, translateMCError(err)).catch(() => {});
    };

    const onDisconnect = async (reason) => {
      console.log(`MC Disconnect [${serverId}]: ${reason}`);
      const conn = activeConnections.get(serverId);
      if (conn?.client?._afkInterval) clearInterval(conn.client._afkInterval);
      if (!conn || conn.stopped) {
        await db.updateServerStatus(serverId, 'stopped');
        return;
      }
      await db.updateServerStatus(serverId, 'reconnecting');
      telegramBot.telegram.sendMessage(
        chatId,
        `⚠️ انقطع الاتصال بـ *${fresh.name}*. جاري إعادة الاتصال خلال 5 ثواني...`,
        { parse_mode: 'Markdown' }
      ).catch(() => {});
      reconnect();
    };

    if (fresh.type === 'java') {
      connectJava(fresh, onSuccess, onError, onDisconnect);
    } else {
      connectBedrock(fresh, onSuccess, onError, onDisconnect);
    }
  };

  activeConnections.set(serverId, { client: null, stopped: false, startedAt: new Date().toISOString() });
  launchConnection();
}

function stopMinecraftBot(serverId) {
  const conn = activeConnections.get(serverId);
  if (!conn) return;
  conn.stopped = true;
  try {
    if (conn.client?._afkInterval) clearInterval(conn.client._afkInterval);
    if (conn.client?.quit)         conn.client.quit();
    else if (conn.client?.disconnect) conn.client.disconnect();
    else if (conn.client?.end)     conn.client.end();
  } catch {}
  activeConnections.delete(serverId);
  db.updateServerStatus(serverId, 'stopped').catch(() => {});
}

// ─── Keyboard Builders ───────────────────────────────────────────────────────
function mainMenuKeyboard(userId, adminFlag) {
  const buttons = [
    [Markup.button.callback('📖 شرح التفعيل',           'guide')],
    [Markup.button.callback('🖥️ إدارة سيرفراتي',        'my_servers')],
    [Markup.button.callback('➕ إضافة سيرفر',            'add_server')],
  ];
  if (adminFlag) {
    buttons.push([Markup.button.callback('⚙️ أوامر الأدمن', 'admin_menu')]);
  }
  return Markup.inlineKeyboard(buttons);
}

function adminMenuKeyboard(userId) {
  const buttons = [
    [Markup.button.callback('➕ إضافة حسابات',          'add_accounts')],
    [Markup.button.callback('📢 الاشتراك الإجباري',     'force_sub_menu')],
    [Markup.button.callback('📡 إذاعة رسالة',           'broadcast_menu')],
    [Markup.button.callback('🚫 إدارة المحظورين',       'ban_menu')],
    [Markup.button.callback('📊 حدود المستخدمين',       'user_limits')],
    [Markup.button.callback('🔙 رجوع',                  'main_menu')],
  ];
  if (isOwner(userId)) {
    buttons.unshift([
      Markup.button.callback('➕ إضافة أدمن',  'add_admin'),
      Markup.button.callback('🗑️ مسح أدمن',   'remove_admin'),
    ]);
  }
  return Markup.inlineKeyboard(buttons);
}

function buildServerInfoText(server, conn) {
  const statusMap = {
    running:      '🟢 يعمل',
    stopped:      '🔴 متوقف',
    connecting:   '🟡 جاري الاتصال',
    reconnecting: '🟠 إعادة اتصال',
    error:        '❌ خطأ',
  };
  const uptime = conn?.startedAt
    ? formatUptime(conn.startedAt)
    : server.started_at ? formatUptime(server.started_at) : '-';
  return (
    `🖥️ *${server.name}*\n` +
    `👾 اسم البوت: \`${server.bot_name}\`\n` +
    `🌐 النوع: ${server.type === 'java' ? '☕ Java' : '📱 Bedrock'}\n` +
    `📡 العنوان: \`${server.host}:${server.port || (server.type === 'java' ? 25565 : 19132)}\`\n` +
    `📶 الحالة: ${statusMap[server.status] || server.status}\n` +
    `⏱️ مدة التشغيل: ${uptime}`
  );
}

function serverSettingsKeyboard(server) {
  const running = ['running', 'reconnecting', 'connecting'].includes(server.status);
  return Markup.inlineKeyboard([
    [running
      ? Markup.button.callback('⏹️ إيقاف البوت',     `stop_bot_${server.id}`)
      : Markup.button.callback('▶️ تشغيل البوت',     `start_bot_${server.id}`)],
    [Markup.button.callback('ℹ️ عرض المعلومات',      `server_info_${server.id}`)],
    [Markup.button.callback('✏️ تغيير اسم البوت',    `change_name_${server.id}`)],
    [Markup.button.callback('🗑️ حذف السيرفر',        `delete_server_${server.id}`)],
    [Markup.button.callback('🔙 رجوع',               'my_servers')],
  ]);
}

// ─── Scenes ──────────────────────────────────────────────────────────────────

// ── Add Server ──
const addServerScene = new Scenes.WizardScene('add_server',
  // Step 0: choose type
  async (ctx) => {
    const kb = Markup.inlineKeyboard([
      [Markup.button.callback('☕ Java', 'type_java'), Markup.button.callback('📱 Bedrock', 'type_bedrock')],
      [Markup.button.callback('🔙 إلغاء', 'main_menu')],
    ]);
    await ctx.editMessageText('🎮 اختر نوع السيرفر:', kb).catch(
      () => ctx.reply('🎮 اختر نوع السيرفر:', kb)
    );
    return ctx.wizard.next();
  },
  // Step 1: wait for type action → handled in bot.action
  async () => {},
  // Step 2: receive IP
  async (ctx) => {
    if (!ctx.message?.text) return;
    const { host, port } = parseServerAddress(ctx.message.text);
    if (!host || host.length < 3) {
      return ctx.reply('❌ عنوان غير صحيح. أرسل عنوان صحيح:');
    }
    const type        = ctx.wizard.state.serverType;
    const finalPort   = port || (type === 'java' ? 25565 : 19132);
    const userId      = ctx.from.id;
    const limit       = parseInt(await db.getSetting('user_server_limit') || '3');
    const count       = await db.countUserServers(userId);
    if (count >= limit) {
      await ctx.reply(`❌ وصلت للحد الأقصى (${limit} سيرفرات). تواصل مع الأدمن لرفع الحد.`);
      return ctx.scene.leave();
    }
    await db.addServer(userId, host, finalPort, type, 'MCBot');
    const adminFlag = await isAdminOrOwner(userId);
    await ctx.reply(
      `✅ تم إضافة السيرفر!\n📡 \`${host}:${finalPort}\`\n🎮 النوع: ${type === 'java' ? '☕ Java' : '📱 Bedrock'}`,
      { parse_mode: 'Markdown', ...mainMenuKeyboard(userId, adminFlag) }
    );
    return ctx.scene.leave();
  }
);

// ── Change Bot Name ──
const changeBotNameScene = new Scenes.WizardScene('change_bot_name',
  async (ctx) => {
    await ctx.reply('✏️ أرسل الاسم الجديد للبوت (اسم اللاعب في الماين كرافت):',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'main_menu')]])
    );
    return ctx.wizard.next();
  },
  async (ctx) => {
    if (!ctx.message?.text) return;
    const name     = ctx.message.text.trim().replace(/\s+/g, '_').slice(0, 16);
    const serverId = ctx.scene.state.serverId;
    await db.updateBotName(serverId, name);
    if (activeConnections.has(serverId)) stopMinecraftBot(serverId);
    await ctx.reply(`✅ تم تغيير اسم البوت إلى \`${name}\``, { parse_mode: 'Markdown' });
    const server = await db.getServer(serverId);
    if (server) {
      await ctx.reply(
        buildServerInfoText(server, activeConnections.get(serverId)),
        { parse_mode: 'Markdown', ...serverSettingsKeyboard(server) }
      );
    }
    return ctx.scene.leave();
  }
);

// ── Add Admin ──
const addAdminScene = new Scenes.WizardScene('add_admin',
  async (ctx) => {
    await ctx.reply('👤 أرسل ID المستخدم الذي تريد إضافته أدمناً:',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'admin_menu')]])
    );
    return ctx.wizard.next();
  },
  async (ctx) => {
    if (!ctx.message?.text) return;
    const targetId = parseInt(ctx.message.text.trim());
    if (isNaN(targetId)) return ctx.reply('❌ ID غير صحيح. أرسل رقم صحيح:');
    await db.addAdmin(targetId, ctx.from.id);
    await ctx.reply(`✅ تم إضافة المستخدم \`${targetId}\` كأدمن.`, { parse_mode: 'Markdown' });
    return ctx.scene.leave();
  }
);

// ── Remove Admin ──
const removeAdminScene = new Scenes.WizardScene('remove_admin',
  async (ctx) => {
    const admins = await db.getAllAdmins();
    if (!admins.length) {
      await ctx.reply('لا يوجد أدمنية.');
      return ctx.scene.leave();
    }
    const buttons = admins.map(a => [
      Markup.button.callback(`🗑️ ${a.user_id}`, `del_admin_${a.user_id}`)
    ]);
    buttons.push([Markup.button.callback('🔙 إلغاء', 'admin_menu')]);
    await ctx.reply('اختر الأدمن الذي تريد مسحه:', Markup.inlineKeyboard(buttons));
    return ctx.wizard.next();
  },
  async () => { /* handled via bot.action */ }
);

// ── Ban User ──
const banUserScene = new Scenes.WizardScene('ban_user',
  async (ctx) => {
    await ctx.reply('🚫 أرسل ID المستخدم الذي تريد حظره:',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'ban_menu')]])
    );
    return ctx.wizard.next();
  },
  async (ctx) => {
    if (!ctx.message?.text) return;
    const targetId = parseInt(ctx.message.text.trim());
    if (isNaN(targetId)) return ctx.reply('❌ ID غير صحيح:');
    await db.banUser(targetId);
    await ctx.reply(`✅ تم حظر المستخدم \`${targetId}\`.`, { parse_mode: 'Markdown' });
    return ctx.scene.leave();
  }
);

// ── Unban User ──
const unbanUserScene = new Scenes.WizardScene('unban_user',
  async (ctx) => {
    await ctx.reply('✅ أرسل ID المستخدم الذي تريد رفع حظره:',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'ban_menu')]])
    );
    return ctx.wizard.next();
  },
  async (ctx) => {
    if (!ctx.message?.text) return;
    const targetId = parseInt(ctx.message.text.trim());
    if (isNaN(targetId)) return ctx.reply('❌ ID غير صحيح:');
    await db.unbanUser(targetId);
    await ctx.reply(`✅ تم رفع الحظر عن المستخدم \`${targetId}\`.`, { parse_mode: 'Markdown' });
    return ctx.scene.leave();
  }
);

// ── Add Accounts ──
const addAccountsScene = new Scenes.WizardScene('add_accounts',
  // Step 0: choose type
  async (ctx) => {
    await ctx.reply('🎮 اختر نوع الحسابات:', Markup.inlineKeyboard([
      [Markup.button.callback('☕ Java', 'acc_java'), Markup.button.callback('📱 Bedrock', 'acc_bedrock')],
      [Markup.button.callback('🔙 إلغاء', 'admin_menu')],
    ]));
    return ctx.wizard.next();
  },
  // Step 1: wait for type action
  async () => {},
  // Step 2: choose method
  async (ctx) => {
    await ctx.reply('📋 كيف تريد إرسال الحسابات؟', Markup.inlineKeyboard([
      [Markup.button.callback('📄 ملف TXT', 'method_file'), Markup.button.callback('✏️ نص مباشر', 'method_text')],
    ]));
    return ctx.wizard.next();
  },
  // Step 3: wait for method action
  async () => {},
  // Step 4: receive accounts
  async (ctx) => {
    let lines = [];

    if (ctx.scene.state.method === 'file') {
      if (!ctx.message?.document) return ctx.reply('❌ أرسل ملف TXT:');
      const fileLink = await ctx.telegram.getFileLink(ctx.message.document.file_id);
      const https    = require('https');
      const http     = require('http');
      const content  = await new Promise((resolve, reject) => {
        const mod = fileLink.href.startsWith('https') ? https : http;
        mod.get(fileLink.href, res => {
          let data = '';
          res.on('data',  chunk => data += chunk);
          res.on('end',   ()    => resolve(data));
          res.on('error', reject);
        });
      });
      lines = content.split('\n');
    } else {
      if (!ctx.message?.text) return ctx.reply('❌ أرسل الحسابات كنص:');
      lines = ctx.message.text.split('\n');
    }

    const type = ctx.scene.state.accountType;
    let added  = 0;
    for (const line of lines) {
      const trimmed   = line.trim();
      const colonIdx  = trimmed.indexOf(':');
      if (colonIdx > 0) {
        const email    = trimmed.slice(0, colonIdx).trim();
        const password = trimmed.slice(colonIdx + 1).trim();
        if (email && password) {
          await db.addAccount(email, password, type);
          added++;
        }
      }
    }
    await ctx.reply(`✅ تم إضافة ${added} حساب ${type === 'java' ? 'Java ☕' : 'Bedrock 📱'} بنجاح.`);
    return ctx.scene.leave();
  }
);

// ── Add Channel ──
const addChannelScene = new Scenes.WizardScene('add_channel',
  async (ctx) => {
    await ctx.reply(
      '📢 تأكد من إضافة البوت كمشرف في القناة، ثم أرسل رابط القناة أو معرّفها (@username أو -100xxx):',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'force_sub_menu')]])
    );
    return ctx.wizard.next();
  },
  async (ctx) => {
    if (!ctx.message?.text) return;
    let channelId = ctx.message.text.trim();
    if (channelId.includes('t.me/')) {
      channelId = '@' + channelId.split('t.me/')[1].split('/')[0];
    }
    try {
      const chatMember = await ctx.telegram.getChatMember(channelId, ctx.botInfo.id);
      if (!['administrator', 'creator'].includes(chatMember.status)) {
        await ctx.reply('❌ البوت ليس مشرفاً في هذه القناة. أضفه كمشرف وأعد المحاولة.');
        return ctx.scene.leave();
      }
      const chat = await ctx.telegram.getChat(channelId);
      await db.addChannel(channelId, chat.title || channelId);
      await ctx.reply(`✅ تم إضافة القناة "${chat.title || channelId}" للاشتراك الإجباري.`);
    } catch (e) {
      await ctx.reply(`❌ فشل: تأكد أن البوت مشرف في القناة وأن المعرّف صحيح.\n${e.message}`);
    }
    return ctx.scene.leave();
  }
);

// ── Broadcast ──
let broadcastStop = false;

const broadcastScene = new Scenes.WizardScene('broadcast',
  // Step 0: choose target
  async (ctx) => {
    await ctx.reply('📡 اختر الجمهور المستهدف:', Markup.inlineKeyboard([
      [Markup.button.callback('👥 الجميع',         'bc_all')],
      [Markup.button.callback('💬 الخاص فقط',     'bc_private')],
      [Markup.button.callback('📢 القنوات فقط',   'bc_channels')],
      [Markup.button.callback('🔙 إلغاء',         'admin_menu')],
    ]));
    return ctx.wizard.next();
  },
  // Step 1: wait for target action
  async () => {},
  // Step 2: ask for message
  async (ctx) => {
    await ctx.reply('✉️ أرسل الرسالة التي تريد إذاعتها (نص أو صورة أو فيديو):',
      Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'admin_menu')]])
    );
    return ctx.wizard.next();
  },
  // Step 3: do broadcast
  async (ctx) => {
    if (!ctx.message) return;
    const target = ctx.scene.state.broadcastTarget;
    broadcastStop = false;

    let recipients = [];
    if (target === 'all' || target === 'private') {
      recipients = [...recipients, ...await db.getAllUserIds()];
    }
    if (target === 'all' || target === 'channels') {
      const chans = await db.getAllChannels();
      recipients  = [...recipients, ...chans.map(c => c.channel_id)];
    }

    const stopKb    = Markup.inlineKeyboard([[Markup.button.callback('⏹️ إيقاف الإذاعة', 'stop_broadcast')]]);
    const statusMsg = await ctx.reply(`📡 جاري الإذاعة لـ ${recipients.length} مستلم...`, stopKb);

    let success = 0, fail = 0;
    for (const recipient of recipients) {
      if (broadcastStop) break;
      try {
        await ctx.telegram.copyMessage(recipient, ctx.chat.id, ctx.message.message_id);
        success++;
      } catch {
        fail++;
      }
      await new Promise(r => setTimeout(r, 50));
    }

    await ctx.telegram.editMessageText(
      ctx.chat.id, statusMsg.message_id, null,
      `📊 *تقرير الإذاعة:*\n✅ نجح: ${success}\n❌ فشل: ${fail}\n${broadcastStop ? '⏹️ تم الإيقاف مبكراً.' : '✅ اكتملت الإذاعة.'}`,
      { parse_mode: 'Markdown' }
    ).catch(() => {});

    return ctx.scene.leave();
  }
);

// ─── Setup Telegraf ──────────────────────────────────────────────────────────
const stage = new Scenes.Stage([
  addServerScene,
  changeBotNameScene,
  addAdminScene,
  removeAdminScene,
  banUserScene,
  unbanUserScene,
  addAccountsScene,
  addChannelScene,
  broadcastScene,
]);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());
bot.use(stage.middleware());

// ─── Global Middleware ───────────────────────────────────────────────────────
bot.use(async (ctx, next) => {
  if (!ctx.from) return next();
  const u = ctx.from;
  await db.upsertUser(u.id, u.username, `${u.first_name}${u.last_name ? ' ' + u.last_name : ''}`);
  const user = await db.getUser(u.id);
  if (user?.is_banned) {
    return ctx.reply('🚫 أنت محظور من استخدام هذا البوت.').catch(() => {});
  }
  return next();
});

// ─── /start ──────────────────────────────────────────────────────────────────
bot.start(async (ctx) => {
  const subscribed = await checkSubscription(ctx);
  if (!subscribed) {
    return ctx.reply('⚠️ يجب الاشتراك في القنوات التالية أولاً:', await subscriptionKeyboard());
  }
  const adminFlag = await isAdminOrOwner(ctx.from.id);
  await ctx.reply(
    `👋 أهلاً ${ctx.from.first_name}!\n🤖 بوت إدارة سيرفرات ماين كرافت`,
    mainMenuKeyboard(ctx.from.id, adminFlag)
  );
});

// ─── check_sub ───────────────────────────────────────────────────────────────
bot.action('check_sub', async (ctx) => {
  await ctx.answerCbQuery();
  const subscribed = await checkSubscription(ctx);
  if (!subscribed) {
    return ctx.answerCbQuery('❌ لم تشترك في جميع القنوات بعد!', { show_alert: true });
  }
  const adminFlag = await isAdminOrOwner(ctx.from.id);
  await ctx.editMessageText(
    `👋 أهلاً ${ctx.from.first_name}!\n🤖 بوت إدارة سيرفرات ماين كرافت`,
    mainMenuKeyboard(ctx.from.id, adminFlag)
  );
});

// ─── main_menu ───────────────────────────────────────────────────────────────
bot.action('main_menu', async (ctx) => {
  await ctx.answerCbQuery();
  const adminFlag = await isAdminOrOwner(ctx.from.id);
  await ctx.editMessageText(
    `👋 أهلاً ${ctx.from.first_name}!\n🤖 بوت إدارة سيرفرات ماين كرافت`,
    mainMenuKeyboard(ctx.from.id, adminFlag)
  ).catch(() => ctx.reply('🏠 القائمة الرئيسية:', mainMenuKeyboard(ctx.from.id, adminFlag)));
});

// ─── guide ───────────────────────────────────────────────────────────────────
bot.action('guide', async (ctx) => {
  await ctx.answerCbQuery();
  await ctx.editMessageText(
    `📖 *دليل الاستخدام:*\n\n` +
    `1️⃣ اضغط على "➕ إضافة سيرفر" واختر نوع السيرفر (Java أو Bedrock).\n` +
    `2️⃣ أرسل عنوان IP السيرفر (مع البورت إن لزم، مثل: \`play.example.com:25565\`).\n` +
    `3️⃣ ادخل إلى "🖥️ إدارة سيرفراتي" واضغط على السيرفر للتحكم فيه.\n` +
    `4️⃣ اضغط "▶️ تشغيل البوت" ليدخل البوت للسيرفر تلقائياً.\n\n` +
    `⚠️ *ملاحظة مهمة:* يجب أن يكون السيرفر مفعّل المكرك *(Cracked/Offline mode)* حتى يعمل البوت.\n\n` +
    `🔁 البوت يعيد الاتصال تلقائياً إذا انقطع.\n` +
    `🕹️ البوت يتحرك كل 25 ثانية لمنع طرده بسبب Anti-AFK.`,
    {
      parse_mode: 'Markdown',
      ...Markup.inlineKeyboard([[Markup.button.callback('🔙 رجوع', 'main_menu')]])
    }
  );
});

// ─── my_servers ──────────────────────────────────────────────────────────────
bot.action('my_servers', async (ctx) => {
  await ctx.answerCbQuery();
  const servers = await db.getUserServers(ctx.from.id);
  if (!servers.length) {
    return ctx.editMessageText('📭 لا توجد سيرفرات مضافة بعد.', Markup.inlineKeyboard([
      [Markup.button.callback('➕ إضافة سيرفر', 'add_server')],
      [Markup.button.callback('🔙 رجوع',        'main_menu')],
    ]));
  }
  const statusEmoji = { running: '🟢', stopped: '🔴', connecting: '🟡', reconnecting: '🟠', error: '❌' };
  const buttons = servers.map(s => [
    Markup.button.callback(
      `${statusEmoji[s.status] || '⚪'} ${s.name} — ${s.host}`,
      `view_server_${s.id}`
    )
  ]);
  buttons.push([Markup.button.callback('🔙 رجوع', 'main_menu')]);
  await ctx.editMessageText('🖥️ سيرفراتك:', Markup.inlineKeyboard(buttons));
});

bot.action(/^view_server_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  const server   = await db.getServer(serverId);
  if (!server || server.user_id !== ctx.from.id) {
    return ctx.answerCbQuery('❌ السيرفر غير موجود.', { show_alert: true });
  }
  await ctx.editMessageText(
    buildServerInfoText(server, activeConnections.get(serverId)),
    { parse_mode: 'Markdown', ...serverSettingsKeyboard(server) }
  );
});

// ─── add_server ──────────────────────────────────────────────────────────────
bot.action('add_server', async (ctx) => {
  await ctx.answerCbQuery();
  const subscribed = await checkSubscription(ctx);
  if (!subscribed) {
    return ctx.reply('⚠️ يجب الاشتراك في القنوات أولاً:', await subscriptionKeyboard());
  }
  await ctx.scene.enter('add_server');
});

// Scene action: choose server type
bot.action(['type_java', 'type_bedrock'], async (ctx) => {
  if (ctx.scene.current?.id !== 'add_server') return ctx.answerCbQuery();
  await ctx.answerCbQuery();
  ctx.wizard.state.serverType = ctx.callbackQuery.data === 'type_java' ? 'java' : 'bedrock';
  const label = ctx.wizard.state.serverType === 'java' ? 'Java ☕' : 'Bedrock 📱';
  await ctx.editMessageText(
    `🌐 أرسل عنوان السيرفر ${label}:\nمثال: \`play.example.com:25565\``,
    { parse_mode: 'Markdown' }
  );
  ctx.wizard.selectStep(2);
});

// ─── start_bot / stop_bot ────────────────────────────────────────────────────
bot.action(/^start_bot_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  const server   = await db.getServer(serverId);
  if (!server || server.user_id !== ctx.from.id) return;
  if (activeConnections.has(serverId)) {
    return ctx.answerCbQuery('⚠️ البوت يعمل بالفعل.', { show_alert: true });
  }
  const edited = await ctx.editMessageText(
    `🟡 جاري الاتصال بـ \`${server.host}:${server.port}\`...`,
    { parse_mode: 'Markdown' }
  );
  await startMinecraftBot(serverId, bot, ctx.chat.id, edited.message_id);
});

bot.action(/^stop_bot_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  const server   = await db.getServer(serverId);
  if (!server || server.user_id !== ctx.from.id) return;
  stopMinecraftBot(serverId);
  const fresh = await db.getServer(serverId);
  await ctx.editMessageText(
    buildServerInfoText(fresh, null),
    { parse_mode: 'Markdown', ...serverSettingsKeyboard(fresh) }
  );
});

// ─── server_info ─────────────────────────────────────────────────────────────
bot.action(/^server_info_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  const server   = await db.getServer(serverId);
  if (!server || server.user_id !== ctx.from.id) return;
  await ctx.editMessageText(
    buildServerInfoText(server, activeConnections.get(serverId)),
    { parse_mode: 'Markdown', ...serverSettingsKeyboard(server) }
  );
});

// ─── change_name ─────────────────────────────────────────────────────────────
bot.action(/^change_name_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  await ctx.scene.enter('change_bot_name', { serverId });
});

// ─── delete_server ────────────────────────────────────────────────────────────
bot.action(/^delete_server_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  const serverId = parseInt(ctx.match[1]);
  const server   = await db.getServer(serverId);
  if (!server || server.user_id !== ctx.from.id) return;
  stopMinecraftBot(serverId);
  await db.deleteServer(serverId);
  const adminFlag = await isAdminOrOwner(ctx.from.id);
  await ctx.editMessageText('🗑️ تم حذف السيرفر بنجاح.', mainMenuKeyboard(ctx.from.id, adminFlag));
});

// ─── admin_menu ───────────────────────────────────────────────────────────────
bot.action('admin_menu', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) {
    return ctx.answerCbQuery('🚫 ليس لديك صلاحية.', { show_alert: true });
  }
  await ctx.editMessageText('⚙️ لوحة الأدمن:', adminMenuKeyboard(ctx.from.id));
});

// ─── add_admin / remove_admin ─────────────────────────────────────────────────
bot.action('add_admin', async (ctx) => {
  await ctx.answerCbQuery();
  if (!isOwner(ctx.from.id)) return;
  await ctx.scene.enter('add_admin');
});

bot.action('remove_admin', async (ctx) => {
  await ctx.answerCbQuery();
  if (!isOwner(ctx.from.id)) return;
  await ctx.scene.enter('remove_admin');
});

bot.action(/^del_admin_(\d+)$/, async (ctx) => {
  await ctx.answerCbQuery();
  if (!isOwner(ctx.from.id)) return;
  const targetId = parseInt(ctx.match[1]);
  await db.removeAdmin(targetId);
  await ctx.editMessageText(`✅ تم مسح الأدمن \`${targetId}\`.`, { parse_mode: 'Markdown' });
  await ctx.scene.leave();
});

// ─── add_accounts scene actions ───────────────────────────────────────────────
bot.action('add_accounts', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  await ctx.scene.enter('add_accounts');
});

bot.action(['acc_java', 'acc_bedrock'], async (ctx) => {
  if (ctx.scene.current?.id !== 'add_accounts') return ctx.answerCbQuery();
  await ctx.answerCbQuery();
  ctx.wizard.state.accountType = ctx.callbackQuery.data === 'acc_java' ? 'java' : 'bedrock';
  ctx.wizard.selectStep(2);
  await ctx.reply('📋 كيف تريد إرسال الحسابات؟', Markup.inlineKeyboard([
    [Markup.button.callback('📄 ملف TXT', 'method_file'), Markup.button.callback('✏️ نص مباشر', 'method_text')],
  ]));
});

bot.action(['method_file', 'method_text'], async (ctx) => {
  if (ctx.scene.current?.id !== 'add_accounts') return ctx.answerCbQuery();
  await ctx.answerCbQuery();
  ctx.scene.state.method = ctx.callbackQuery.data === 'method_file' ? 'file' : 'text';
  ctx.wizard.selectStep(4);
  const instructions = ctx.scene.state.method === 'file'
    ? '📄 أرسل ملف TXT يحتوي على الحسابات بصيغة:\n`email:password` (سطر لكل حساب)'
    : '✏️ أرسل الحسابات كنص بصيغة:\n`email:password` (سطر لكل حساب)';
  await ctx.reply(instructions, { parse_mode: 'Markdown' });
});

// ─── force_sub_menu ───────────────────────────────────────────────────────────
bot.action('force_sub_menu', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  const channels = await db.getAllChannels();
  let text = '📢 *قنوات الاشتراك الإجباري:*\n';
  const buttons = [];
  if (channels.length) {
    channels.forEach(ch => {
      text += `\n• ${ch.channel_title || ch.channel_id}`;
      buttons.push([Markup.button.callback(`🗑️ ${ch.channel_title || ch.channel_id}`, `rm_channel_${ch.channel_id}`)]);
    });
  } else {
    text += '\nلا توجد قنوات مضافة.';
  }
  buttons.push([Markup.button.callback('➕ إضافة قناة', 'add_channel')]);
  buttons.push([Markup.button.callback('🔙 رجوع',       'admin_menu')]);
  await ctx.editMessageText(text, { parse_mode: 'Markdown', ...Markup.inlineKeyboard(buttons) });
});

bot.action('add_channel', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  await ctx.scene.enter('add_channel');
});

bot.action(/^rm_channel_(.+)$/, async (ctx) => {
  await ctx.answerCbQuery('✅ تم حذف القناة.', { show_alert: true });
  if (!await isAdminOrOwner(ctx.from.id)) return;
  const channelId = ctx.match[1];
  await db.removeChannel(channelId);
  // Refresh the list
  const channels = await db.getAllChannels();
  const buttons  = channels.map(ch => [
    Markup.button.callback(`🗑️ ${ch.channel_title || ch.channel_id}`, `rm_channel_${ch.channel_id}`)
  ]);
  buttons.push([Markup.button.callback('➕ إضافة قناة', 'add_channel')]);
  buttons.push([Markup.button.callback('🔙 رجوع',       'admin_menu')]);
  await ctx.editMessageText(
    '📢 *قنوات الاشتراك الإجباري:*',
    { parse_mode: 'Markdown', ...Markup.inlineKeyboard(buttons) }
  );
});

// ─── broadcast ────────────────────────────────────────────────────────────────
bot.action('broadcast_menu', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  await ctx.scene.enter('broadcast');
});

bot.action(['bc_all', 'bc_private', 'bc_channels'], async (ctx) => {
  if (ctx.scene.current?.id !== 'broadcast') return ctx.answerCbQuery();
  await ctx.answerCbQuery();
  const map = { bc_all: 'all', bc_private: 'private', bc_channels: 'channels' };
  ctx.scene.state.broadcastTarget = map[ctx.callbackQuery.data];
  ctx.wizard.selectStep(2);
  await ctx.reply('✉️ أرسل الرسالة التي تريد إذاعتها:',
    Markup.inlineKeyboard([[Markup.button.callback('🔙 إلغاء', 'admin_menu')]])
  );
});

bot.action('stop_broadcast', async (ctx) => {
  broadcastStop = true;
  await ctx.answerCbQuery('⏹️ جاري إيقاف الإذاعة...', { show_alert: true });
});

// ─── ban_menu ─────────────────────────────────────────────────────────────────
bot.action('ban_menu', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  const banned = await db.getBannedUsers();
  await ctx.editMessageText(
    `🚫 *إدارة المحظورين:*\nعدد المحظورين: ${banned.length}`,
    {
      parse_mode: 'Markdown',
      ...Markup.inlineKeyboard([
        [Markup.button.callback('🚫 حظر مستخدم',        'do_ban'),
         Markup.button.callback('✅ رفع حظر',           'do_unban')],
        [Markup.button.callback('🗑️ مسح كل المحظورين', 'clear_bans')],
        [Markup.button.callback('🔙 رجوع',              'admin_menu')],
      ])
    }
  );
});

bot.action('do_ban',   async (ctx) => { await ctx.answerCbQuery(); await ctx.scene.enter('ban_user');   });
bot.action('do_unban', async (ctx) => { await ctx.answerCbQuery(); await ctx.scene.enter('unban_user'); });

bot.action('clear_bans', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  await db.clearAllBans();
  await ctx.answerCbQuery('✅ تم مسح جميع المحظورين.', { show_alert: true });
});

// ─── user_limits ─────────────────────────────────────────────────────────────
async function renderLimitsMenu(ctx) {
  const limit = await db.getSetting('user_server_limit');
  await ctx.editMessageText(
    `📊 *حد السيرفرات لكل مستخدم:* ${limit}`,
    {
      parse_mode: 'Markdown',
      ...Markup.inlineKeyboard([
        [
          Markup.button.callback('➖ تقليل',    'dec_limit'),
          Markup.button.callback(`[ ${limit} ]`, 'noop'),
          Markup.button.callback('➕ زيادة',    'inc_limit'),
        ],
        [Markup.button.callback('🔙 رجوع', 'admin_menu')],
      ])
    }
  );
}

bot.action('user_limits', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  await renderLimitsMenu(ctx);
});

bot.action('inc_limit', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  const current = parseInt(await db.getSetting('user_server_limit') || '3');
  await db.setSetting('user_server_limit', current + 1);
  await renderLimitsMenu(ctx);
});

bot.action('dec_limit', async (ctx) => {
  await ctx.answerCbQuery();
  if (!await isAdminOrOwner(ctx.from.id)) return;
  const current = parseInt(await db.getSetting('user_server_limit') || '3');
  await db.setSetting('user_server_limit', Math.max(1, current - 1));
  await renderLimitsMenu(ctx);
});

bot.action('noop', ctx => ctx.answerCbQuery());

// ─── Launch ───────────────────────────────────────────────────────────────────
db.init()
  .then(() => {
    console.log('✅ قاعدة البيانات جاهزة.');
    return bot.launch();
  })
  .then(() => console.log('✅ البوت يعمل...'))
  .catch(err => {
    console.error('❌ فشل تشغيل البوت:', err);
    process.exit(1);
  });

process.once('SIGINT',  () => { activeConnections.forEach((_, id) => stopMinecraftBot(id)); bot.stop('SIGINT');  });
process.once('SIGTERM', () => { activeConnections.forEach((_, id) => stopMinecraftBot(id)); bot.stop('SIGTERM'); });