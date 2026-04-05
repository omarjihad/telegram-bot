'use strict';

const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const DB_PATH = path.join(__dirname, 'bot.db');

// ─── Promise Wrapper ────────────────────────────────────────────────────────
// We open the DB once and keep the connection alive for the entire process.
const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) {
    console.error('❌ Failed to open database:', err.message);
    process.exit(1);
  }
});

// Enable WAL mode for better concurrent performance
db.run('PRAGMA journal_mode = WAL;');
db.run('PRAGMA foreign_keys = ON;');

/**
 * Run a write query (INSERT, UPDATE, DELETE, CREATE).
 * Resolves with { lastID, changes }.
 */
function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function (err) {
      if (err) return reject(err);
      resolve({ lastID: this.lastID, changes: this.changes });
    });
  });
}

/**
 * Fetch a single row. Resolves with the row object or undefined.
 */
function get(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      if (err) return reject(err);
      resolve(row);
    });
  });
}

/**
 * Fetch all matching rows. Resolves with an array of row objects.
 */
function all(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) return reject(err);
      resolve(rows);
    });
  });
}

/**
 * Execute multiple statements separated by semicolons (no params).
 */
function exec(sql) {
  return new Promise((resolve, reject) => {
    db.exec(sql, (err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

// ─── Init ───────────────────────────────────────────────────────────────────
async function init() {
  await exec(`
    CREATE TABLE IF NOT EXISTS users (
      id        INTEGER PRIMARY KEY,
      user_id   INTEGER UNIQUE NOT NULL,
      username  TEXT,
      full_name TEXT,
      is_banned INTEGER DEFAULT 0,
      joined_at TEXT    DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS admins (
      id       INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id  INTEGER UNIQUE NOT NULL,
      added_by INTEGER,
      added_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS servers (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id    INTEGER NOT NULL,
      name       TEXT    NOT NULL,
      host       TEXT    NOT NULL,
      port       INTEGER NOT NULL,
      type       TEXT    NOT NULL,
      bot_name   TEXT    DEFAULT 'MCBot',
      status     TEXT    DEFAULT 'stopped',
      started_at TEXT,
      FOREIGN KEY (user_id) REFERENCES users(user_id)
    );

    CREATE TABLE IF NOT EXISTS accounts (
      id       INTEGER PRIMARY KEY AUTOINCREMENT,
      email    TEXT NOT NULL,
      password TEXT NOT NULL,
      type     TEXT NOT NULL,
      status   TEXT DEFAULT 'available',
      added_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS channels (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      channel_id    TEXT UNIQUE NOT NULL,
      channel_title TEXT,
      added_at      TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT
    );
  `);

  // Default settings
  await run(
    "INSERT OR IGNORE INTO settings (key, value) VALUES ('user_server_limit', '3')"
  );
}

// ─── Users ──────────────────────────────────────────────────────────────────
async function upsertUser(userId, username, fullName) {
  await run(
    `INSERT INTO users (user_id, username, full_name)
     VALUES (?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       username  = excluded.username,
       full_name = excluded.full_name`,
    [userId, username || '', fullName || '']
  );
}

async function getUser(userId) {
  return get('SELECT * FROM users WHERE user_id = ?', [userId]);
}

async function getAllUserIds() {
  const rows = await all('SELECT user_id FROM users WHERE is_banned = 0');
  return rows.map(r => r.user_id);
}

async function banUser(userId) {
  await run('UPDATE users SET is_banned = 1 WHERE user_id = ?', [userId]);
}

async function unbanUser(userId) {
  await run('UPDATE users SET is_banned = 0 WHERE user_id = ?', [userId]);
}

async function clearAllBans() {
  await run('UPDATE users SET is_banned = 0');
}

async function getBannedUsers() {
  return all('SELECT * FROM users WHERE is_banned = 1');
}

// ─── Admins ─────────────────────────────────────────────────────────────────
async function addAdmin(userId, addedBy) {
  await run(
    'INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)',
    [userId, addedBy]
  );
}

async function removeAdmin(userId) {
  await run('DELETE FROM admins WHERE user_id = ?', [userId]);
}

async function isAdmin(userId) {
  const row = await get('SELECT 1 FROM admins WHERE user_id = ?', [userId]);
  return !!row;
}

async function getAllAdmins() {
  return all('SELECT * FROM admins');
}

// ─── Servers ─────────────────────────────────────────────────────────────────
async function addServer(userId, host, port, type, botName) {
  const row = await get(
    'SELECT COUNT(*) AS c FROM servers WHERE user_id = ?',
    [userId]
  );
  const name = `Server-${(row.c || 0) + 1}`;
  const result = await run(
    `INSERT INTO servers (user_id, name, host, port, type, bot_name)
     VALUES (?, ?, ?, ?, ?, ?)`,
    [userId, name, host, port, type, botName || 'MCBot']
  );
  return result.lastID;
}

async function getUserServers(userId) {
  return all('SELECT * FROM servers WHERE user_id = ?', [userId]);
}

async function getServer(serverId) {
  return get('SELECT * FROM servers WHERE id = ?', [serverId]);
}

async function updateServerStatus(serverId, status) {
  const startedAt = status === 'running' ? new Date().toISOString() : null;
  await run(
    'UPDATE servers SET status = ?, started_at = ? WHERE id = ?',
    [status, startedAt, serverId]
  );
}

async function updateBotName(serverId, botName) {
  await run('UPDATE servers SET bot_name = ? WHERE id = ?', [botName, serverId]);
}

async function deleteServer(serverId) {
  await run('DELETE FROM servers WHERE id = ?', [serverId]);
}

async function countUserServers(userId) {
  const row = await get(
    'SELECT COUNT(*) AS c FROM servers WHERE user_id = ?',
    [userId]
  );
  return row ? row.c : 0;
}

// ─── Accounts ────────────────────────────────────────────────────────────────
async function addAccount(email, password, type) {
  await run(
    'INSERT OR IGNORE INTO accounts (email, password, type) VALUES (?, ?, ?)',
    [email, password, type]
  );
}

async function getAccountStats() {
  const total = await get('SELECT COUNT(*) AS c FROM accounts');
  const java  = await get("SELECT COUNT(*) AS c FROM accounts WHERE type = 'java'");
  const bedrock = await get("SELECT COUNT(*) AS c FROM accounts WHERE type = 'bedrock'");
  return {
    total:   total.c,
    java:    java.c,
    bedrock: bedrock.c,
  };
}

// ─── Channels ────────────────────────────────────────────────────────────────
async function addChannel(channelId, title) {
  await run(
    'INSERT OR IGNORE INTO channels (channel_id, channel_title) VALUES (?, ?)',
    [channelId, title]
  );
}

async function removeChannel(channelId) {
  await run('DELETE FROM channels WHERE channel_id = ?', [channelId]);
}

async function getAllChannels() {
  return all('SELECT * FROM channels');
}

// ─── Settings ─────────────────────────────────────────────────────────────────
async function getSetting(key) {
  const row = await get('SELECT value FROM settings WHERE key = ?', [key]);
  return row ? row.value : null;
}

async function setSetting(key, value) {
  await run(
    'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
    [key, String(value)]
  );
}

// ─── Exports ──────────────────────────────────────────────────────────────────
module.exports = {
  init,
  // users
  upsertUser, getUser, getAllUserIds, banUser, unbanUser, clearAllBans, getBannedUsers,
  // admins
  addAdmin, removeAdmin, isAdmin, getAllAdmins,
  // servers
  addServer, getUserServers, getServer, updateServerStatus, updateBotName, deleteServer, countUserServers,
  // accounts
  addAccount, getAccountStats,
  // channels
  addChannel, removeChannel, getAllChannels,
  // settings
  getSetting, setSetting,
};