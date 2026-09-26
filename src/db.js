const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const dbPath = path.resolve(process.env.DATABASE_PATH || './data/tickets.db');
fs.mkdirSync(path.dirname(dbPath), { recursive: true });

const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id          TEXT PRIMARY KEY,
    category_id       TEXT,
    support_role_id   TEXT,
    log_channel_id    TEXT,
    panel_title       TEXT NOT NULL DEFAULT 'Поддержка',
    panel_description TEXT NOT NULL DEFAULT 'Нажмите кнопку ниже, чтобы создать тикет.',
    welcome_message   TEXT NOT NULL DEFAULT 'Здравствуйте, {user}! Опишите вашу проблему, и команда поддержки скоро ответит.',
    max_open_tickets  INTEGER NOT NULL DEFAULT 1
  );

  CREATE TABLE IF NOT EXISTS ticket_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT NOT NULL,
    name        TEXT NOT NULL,
    emoji       TEXT,
    description TEXT
  );

  CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT NOT NULL,
    channel_id  TEXT UNIQUE,
    user_id     TEXT NOT NULL,
    user_tag    TEXT NOT NULL,
    type_name   TEXT,
    subject     TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    claimed_by  TEXT,
    closed_by   TEXT,
    created_at  INTEGER NOT NULL,
    closed_at   INTEGER
  );

  CREATE TABLE IF NOT EXISTS ticket_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author_id   TEXT NOT NULL,
    author_tag  TEXT NOT NULL,
    content     TEXT NOT NULL,
    from_panel  INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status);
  CREATE INDEX IF NOT EXISTS idx_messages_ticket ON ticket_messages(ticket_id);
`);

const now = () => Date.now();

const settings = {
  get(guildId) {
    db.prepare('INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)').run(guildId);
    return db.prepare('SELECT * FROM guild_settings WHERE guild_id = ?').get(guildId);
  },
  update(guildId, data) {
    settings.get(guildId);
    const fields = [
      'category_id', 'support_role_id', 'log_channel_id',
      'panel_title', 'panel_description', 'welcome_message', 'max_open_tickets',
    ].filter((f) => f in data);
    if (!fields.length) return;
    const sql = `UPDATE guild_settings SET ${fields.map((f) => `${f} = @${f}`).join(', ')} WHERE guild_id = @guild_id`;
    db.prepare(sql).run({ ...Object.fromEntries(fields.map((f) => [f, data[f]])), guild_id: guildId });
  },
};

const ticketTypes = {
  list: (guildId) => db.prepare('SELECT * FROM ticket_types WHERE guild_id = ? ORDER BY id').all(guildId),
  get: (id) => db.prepare('SELECT * FROM ticket_types WHERE id = ?').get(id),
  create: (guildId, { name, emoji, description }) =>
    db.prepare('INSERT INTO ticket_types (guild_id, name, emoji, description) VALUES (?, ?, ?, ?)')
      .run(guildId, name, emoji || null, description || null),
  remove: (guildId, id) => db.prepare('DELETE FROM ticket_types WHERE id = ? AND guild_id = ?').run(id, guildId),
};

const tickets = {
  create({ guildId, userId, userTag, typeName, subject }) {
    const info = db.prepare(`
      INSERT INTO tickets (guild_id, user_id, user_tag, type_name, subject, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(guildId, userId, userTag, typeName || null, subject || null, now());
    return tickets.get(info.lastInsertRowid);
  },
  setChannel: (id, channelId) => db.prepare('UPDATE tickets SET channel_id = ? WHERE id = ?').run(channelId, id),
  get: (id) => db.prepare('SELECT * FROM tickets WHERE id = ?').get(id),
  byChannel: (channelId) => db.prepare('SELECT * FROM tickets WHERE channel_id = ?').get(channelId),
  countOpenByUser: (guildId, userId) =>
    db.prepare("SELECT COUNT(*) AS c FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'")
      .get(guildId, userId).c,
  claim: (id, userId) => db.prepare('UPDATE tickets SET claimed_by = ? WHERE id = ?').run(userId, id),
  close: (id, closedBy) =>
    db.prepare("UPDATE tickets SET status = 'closed', closed_by = ?, closed_at = ? WHERE id = ?")
      .run(closedBy, now(), id),
  remove: (id) => db.prepare('DELETE FROM tickets WHERE id = ?').run(id),
  list({ guildId, status, search, limit = 50, offset = 0 } = {}) {
    const where = [];
    const params = {};
    if (guildId) { where.push('guild_id = @guildId'); params.guildId = guildId; }
    if (status) { where.push('status = @status'); params.status = status; }
    if (search) {
      where.push('(user_tag LIKE @search OR subject LIKE @search OR user_id = @raw OR CAST(id AS TEXT) = @raw)');
      params.search = `%${search}%`;
      params.raw = search;
    }
    const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';
    const rows = db.prepare(`SELECT * FROM tickets ${clause} ORDER BY id DESC LIMIT @limit OFFSET @offset`)
      .all({ ...params, limit, offset });
    const total = db.prepare(`SELECT COUNT(*) AS c FROM tickets ${clause}`).get(params).c;
    return { rows, total };
  },
  stats(guildId) {
    const g = guildId ? 'WHERE guild_id = @guildId' : '';
    const and = guildId ? 'AND guild_id = @guildId' : '';
    const p = guildId ? { guildId } : {};
    return {
      total: db.prepare(`SELECT COUNT(*) AS c FROM tickets ${g}`).get(p).c,
      open: db.prepare(`SELECT COUNT(*) AS c FROM tickets WHERE status = 'open' ${and}`).get(p).c,
      closed: db.prepare(`SELECT COUNT(*) AS c FROM tickets WHERE status = 'closed' ${and}`).get(p).c,
      today: db.prepare(`SELECT COUNT(*) AS c FROM tickets WHERE created_at >= @since ${and}`)
        .get({ ...p, since: now() - 24 * 60 * 60 * 1000 }).c,
      avgCloseMinutes: Math.round(
        (db.prepare(`SELECT AVG(closed_at - created_at) AS a FROM tickets WHERE status = 'closed' ${and}`).get(p).a || 0)
        / 60000,
      ),
    };
  },
};

const messages = {
  add: ({ ticketId, authorId, authorTag, content, fromPanel = false }) =>
    db.prepare(`
      INSERT INTO ticket_messages (ticket_id, author_id, author_tag, content, from_panel, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(ticketId, authorId, authorTag, content, fromPanel ? 1 : 0, now()),
  list: (ticketId) => db.prepare('SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY id').all(ticketId),
};

module.exports = { db, settings, ticketTypes, tickets, messages };
