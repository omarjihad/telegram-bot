'use strict';

const mongoose = require('mongoose');

const MONGO_URI = 'mongodb+srv://markforme771:sosmVO6GbIMyiePS@cluster0.mongodb.net/?retryWrites=true&w=majority';

// ─── Schemas ─────────────────────────────────────────────────────────────────

const userSchema = new mongoose.Schema({
  user_id:   { type: Number, unique: true, required: true },
  username:  { type: String, default: '' },
  full_name: { type: String, default: '' },
  is_banned: { type: Boolean, default: false },
  joined_at: { type: Date, default: Date.now },
});

const adminSchema = new mongoose.Schema({
  user_id:  { type: Number, unique: true, required: true },
  added_by: { type: Number },
  added_at: { type: Date, default: Date.now },
});

const serverSchema = new mongoose.Schema({
  user_id:    { type: Number, required: true },
  name:       { type: String, required: true },
  host:       { type: String, required: true },
  port:       { type: Number, required: true },
  type:       { type: String, required: true },
  bot_name:   { type: String, default: 'MCBot' },
  status:     { type: String, default: 'stopped' },
  started_at: { type: Date, default: null },
});

const accountSchema = new mongoose.Schema({
  email:    { type: String, required: true },
  password: { type: String, required: true },
  type:     { type: String, required: true },
  status:   { type: String, default: 'available' },
  added_at: { type: Date, default: Date.now },
});

const channelSchema = new mongoose.Schema({
  channel_id:    { type: String, unique: true, required: true },
  channel_title: { type: String, default: '' },
  added_at:      { type: Date, default: Date.now },
});

const settingSchema = new mongoose.Schema({
  key:   { type: String, unique: true, required: true },
  value: { type: String, required: true },
});

// ─── Models ───────────────────────────────────────────────────────────────────
const User    = mongoose.model('User',    userSchema);
const Admin   = mongoose.model('Admin',   adminSchema);
const Server  = mongoose.model('Server',  serverSchema);
const Account = mongoose.model('Account', accountSchema);
const Channel = mongoose.model('Channel', channelSchema);
const Setting = mongoose.model('Setting', settingSchema);

// ─── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  await mongoose.connect(MONGO_URI);
  console.log('✅ MongoDB متصل.');
  // Default settings
  await Setting.findOneAndUpdate(
    { key: 'user_server_limit' },
    { $setOnInsert: { key: 'user_server_limit', value: '3' } },
    { upsert: true, new: true }
  );
}

// ─── Users ────────────────────────────────────────────────────────────────────
async function upsertUser(userId, username, fullName) {
  await User.findOneAndUpdate(
    { user_id: userId },
    { $set: { username: username || '', full_name: fullName || '' }, $setOnInsert: { user_id: userId } },
    { upsert: true, new: true }
  );
}

// returns { user, isNew }
async function upsertUserWithStatus(userId, username, fullName) {
  const existing = await User.findOne({ user_id: userId });
  await User.findOneAndUpdate(
    { user_id: userId },
    { $set: { username: username || '', full_name: fullName || '' }, $setOnInsert: { user_id: userId } },
    { upsert: true, new: true }
  );
  return { isNew: !existing };
}

async function getUser(userId) {
  return User.findOne({ user_id: userId }).lean();
}

async function getAllUserIds() {
  const users = await User.find({ is_banned: false }, 'user_id').lean();
  return users.map(u => u.user_id);
}

async function banUser(userId) {
  await User.findOneAndUpdate({ user_id: userId }, { $set: { is_banned: true } });
}

async function unbanUser(userId) {
  await User.findOneAndUpdate({ user_id: userId }, { $set: { is_banned: false } });
}

async function clearAllBans() {
  await User.updateMany({}, { $set: { is_banned: false } });
}

async function getBannedUsers() {
  return User.find({ is_banned: true }).lean();
}

async function getUserCount() {
  return User.countDocuments();
}

// ─── Admins ───────────────────────────────────────────────────────────────────
async function addAdmin(userId, addedBy) {
  await Admin.findOneAndUpdate(
    { user_id: userId },
    { $setOnInsert: { user_id: userId, added_by: addedBy } },
    { upsert: true }
  );
}

async function removeAdmin(userId) {
  await Admin.deleteOne({ user_id: userId });
}

async function isAdmin(userId) {
  return !!(await Admin.findOne({ user_id: userId }));
}

async function getAllAdmins() {
  return Admin.find().lean();
}

// ─── Servers ──────────────────────────────────────────────────────────────────
async function addServer(userId, host, port, type, botName) {
  const count  = await Server.countDocuments({ user_id: userId });
  const name   = `Server-${count + 1}`;
  const server = await Server.create({ user_id: userId, name, host, port, type, bot_name: botName || 'MCBot' });
  return server._id.toString();
}

async function getUserServers(userId) {
  const servers = await Server.find({ user_id: userId }).lean();
  return servers.map(s => ({ ...s, id: s._id.toString() }));
}

async function getServer(serverId) {
  try {
    const s = await Server.findById(serverId).lean();
    if (!s) return null;
    return { ...s, id: s._id.toString() };
  } catch { return null; }
}

async function updateServerStatus(serverId, status) {
  const startedAt = status === 'running' ? new Date() : null;
  await Server.findByIdAndUpdate(serverId, { $set: { status, started_at: startedAt } });
}

async function updateBotName(serverId, botName) {
  await Server.findByIdAndUpdate(serverId, { $set: { bot_name: botName } });
}

async function deleteServer(serverId) {
  await Server.findByIdAndDelete(serverId);
}

async function countUserServers(userId) {
  return Server.countDocuments({ user_id: userId });
}

// ─── Accounts ─────────────────────────────────────────────────────────────────
async function addAccount(email, password, type) {
  await Account.findOneAndUpdate(
    { email, type },
    { $setOnInsert: { email, password, type } },
    { upsert: true }
  );
}

async function getAccountStats() {
  const total   = await Account.countDocuments();
  const java    = await Account.countDocuments({ type: 'java' });
  const bedrock = await Account.countDocuments({ type: 'bedrock' });
  return { total, java, bedrock };
}

// ─── Channels ─────────────────────────────────────────────────────────────────
async function addChannel(channelId, title) {
  await Channel.findOneAndUpdate(
    { channel_id: channelId },
    { $setOnInsert: { channel_id: channelId, channel_title: title || '' } },
    { upsert: true }
  );
}

async function removeChannel(channelId) {
  await Channel.deleteOne({ channel_id: channelId });
}

async function getAllChannels() {
  return Channel.find().lean();
}

// ─── Settings ─────────────────────────────────────────────────────────────────
async function getSetting(key) {
  const row = await Setting.findOne({ key }).lean();
  return row ? row.value : null;
}

async function setSetting(key, value) {
  await Setting.findOneAndUpdate(
    { key },
    { $set: { value: String(value) } },
    { upsert: true }
  );
}

// ─── Exports ──────────────────────────────────────────────────────────────────
module.exports = {
  init,
  upsertUser, upsertUserWithStatus, getUser, getAllUserIds,
  banUser, unbanUser, clearAllBans, getBannedUsers, getUserCount,
  addAdmin, removeAdmin, isAdmin, getAllAdmins,
  addServer, getUserServers, getServer, updateServerStatus,
  updateBotName, deleteServer, countUserServers,
  addAccount, getAccountStats,
  addChannel, removeChannel, getAllChannels,
  getSetting, setSetting,
};
