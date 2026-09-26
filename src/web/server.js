const crypto = require('crypto');
const path = require('path');
const express = require('express');
const session = require('express-session');
const { ChannelType } = require('discord.js');
const db = require('../db');
const { buildPanel, buildTranscript, closeTicket } = require('../bot/tickets');

const PAGE_SIZE = 25;

function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

function createServer(client) {
  const app = express();
  app.set('view engine', 'ejs');
  app.set('views', path.join(__dirname, 'views'));
  app.set('trust proxy', 1);
  app.disable('x-powered-by');

  app.use(express.urlencoded({ extended: false }));
  app.use('/static', express.static(path.join(__dirname, 'public')));
  app.use(session({
    secret: process.env.SESSION_SECRET || crypto.randomBytes(32).toString('hex'),
    resave: false,
    saveUninitialized: false,
    cookie: { httpOnly: true, sameSite: 'lax', maxAge: 7 * 24 * 60 * 60 * 1000 },
  }));

  // CSRF token + common locals
  app.use((req, res, next) => {
    if (!req.session.csrf) req.session.csrf = crypto.randomBytes(24).toString('hex');
    res.locals.csrf = req.session.csrf;
    res.locals.user = req.session.user;
    res.locals.flash = req.session.flash;
    res.locals.path = req.path;
    res.locals.fmtDate = (ts) => (ts ? new Date(ts).toLocaleString('ru-RU') : '—');
    delete req.session.flash;
    if (req.method === 'POST' && !safeEqual(req.body._csrf || '', req.session.csrf)) {
      return res.status(403).send('Invalid CSRF token');
    }
    next();
  });

  const flash = (req, type, text) => { req.session.flash = { type, text }; };

  // ---------- auth ----------
  const loginAttempts = new Map();
  app.get('/login', (req, res) => res.render('login', { error: null }));
  app.post('/login', (req, res) => {
    const ip = req.ip;
    const entry = loginAttempts.get(ip) || { count: 0, until: 0 };
    if (entry.until > Date.now()) {
      return res.status(429).render('login', { error: 'Слишком много попыток. Подождите минуту.' });
    }
    // Evaluate both comparisons to keep timing independent of which field is wrong.
    const userOk = safeEqual(req.body.username || '', process.env.ADMIN_USERNAME || 'admin');
    const passOk = safeEqual(req.body.password || '', process.env.ADMIN_PASSWORD || '');
    const ok = userOk && passOk;
    if (!ok || !process.env.ADMIN_PASSWORD) {
      entry.count += 1;
      if (entry.count >= 5) { entry.count = 0; entry.until = Date.now() + 60_000; }
      loginAttempts.set(ip, entry);
      return res.status(401).render('login', { error: 'Неверный логин или пароль' });
    }
    loginAttempts.delete(ip);
    req.session.regenerate(() => {
      req.session.user = req.body.username;
      res.redirect('/');
    });
  });
  app.post('/logout', (req, res) => req.session.destroy(() => res.redirect('/login')));

  app.use((req, res, next) => (req.session.user ? next() : res.redirect('/login')));

  // ---------- helpers ----------
  const guildList = () => [...client.guilds.cache.values()]
    .map((g) => ({ id: g.id, name: g.name, icon: g.iconURL({ size: 64 }) }));

  function loadGuild(req, res, next) {
    const guild = client.guilds.cache.get(req.params.guildId);
    if (!guild) return res.status(404).render('error', { message: 'Бот не состоит на этом сервере' });
    req.guild = guild;
    next();
  }

  function loadTicket(req, res, next) {
    const ticket = db.tickets.get(Number(req.params.id));
    if (!ticket) return res.status(404).render('error', { message: 'Тикет не найден' });
    req.ticket = ticket;
    next();
  }

  // ---------- dashboard ----------
  app.get('/', (req, res) => {
    const guilds = guildList().map((g) => ({ ...g, stats: db.tickets.stats(g.id) }));
    res.render('dashboard', {
      stats: db.tickets.stats(),
      guilds,
      recent: db.tickets.list({ limit: 10 }).rows,
      botTag: client.user?.tag,
      guildName: (id) => client.guilds.cache.get(id)?.name || id,
    });
  });

  // ---------- tickets ----------
  app.get('/tickets', (req, res) => {
    const page = Math.max(1, Number(req.query.page) || 1);
    const filters = {
      guildId: req.query.guild || undefined,
      status: ['open', 'closed'].includes(req.query.status) ? req.query.status : undefined,
      search: (req.query.q || '').trim() || undefined,
    };
    const { rows, total } = db.tickets.list({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    res.render('tickets', {
      rows,
      total,
      page,
      pages: Math.max(1, Math.ceil(total / PAGE_SIZE)),
      query: req.query,
      guilds: guildList(),
      guildName: (id) => client.guilds.cache.get(id)?.name || id,
    });
  });

  app.get('/tickets/:id', loadTicket, (req, res) => {
    res.render('ticket', {
      ticket: req.ticket,
      messages: db.messages.list(req.ticket.id),
      guildName: client.guilds.cache.get(req.ticket.guild_id)?.name || req.ticket.guild_id,
    });
  });

  app.get('/tickets/:id/transcript.txt', loadTicket, (req, res) => {
    res.type('text/plain; charset=utf-8')
      .attachment(`ticket-${req.ticket.id}.txt`)
      .send(buildTranscript(req.ticket));
  });

  app.post('/tickets/:id/reply', loadTicket, async (req, res) => {
    const content = (req.body.content || '').trim().slice(0, 1900);
    const { ticket } = req;
    if (!content) return res.redirect(`/tickets/${ticket.id}`);
    if (ticket.status !== 'open') {
      flash(req, 'error', 'Тикет закрыт');
      return res.redirect(`/tickets/${ticket.id}`);
    }
    const channel = await client.channels.fetch(ticket.channel_id).catch(() => null);
    if (!channel) {
      flash(req, 'error', 'Канал тикета не найден');
      return res.redirect(`/tickets/${ticket.id}`);
    }
    await channel.send(`**[Поддержка]** ${content}`);
    db.messages.add({
      ticketId: ticket.id,
      authorId: client.user.id,
      authorTag: `${req.session.user} (панель)`,
      content,
      fromPanel: true,
    });
    flash(req, 'success', 'Сообщение отправлено');
    res.redirect(`/tickets/${ticket.id}`);
  });

  app.post('/tickets/:id/close', loadTicket, async (req, res) => {
    await closeTicket(client, req.ticket, {
      closedByTag: `${req.session.user} (панель)`,
      reason: (req.body.reason || '').trim().slice(0, 500) || undefined,
    });
    flash(req, 'success', `Тикет #${req.ticket.id} закрыт`);
    res.redirect(`/tickets/${req.ticket.id}`);
  });

  // ---------- guild settings ----------
  app.get('/guilds/:guildId', loadGuild, async (req, res) => {
    const { guild } = req;
    await guild.roles.fetch().catch(() => {});
    await guild.channels.fetch().catch(() => {});
    const channels = [...guild.channels.cache.values()].sort((a, b) => a.rawPosition - b.rawPosition);
    res.render('guild', {
      guild,
      settings: db.settings.get(guild.id),
      types: db.ticketTypes.list(guild.id),
      stats: db.tickets.stats(guild.id),
      categories: channels.filter((c) => c.type === ChannelType.GuildCategory),
      textChannels: channels.filter((c) => c.type === ChannelType.GuildText),
      roles: [...guild.roles.cache.values()]
        .filter((r) => r.id !== guild.id && !r.managed)
        .sort((a, b) => b.position - a.position),
    });
  });

  app.post('/guilds/:guildId/settings', loadGuild, (req, res) => {
    const b = req.body;
    db.settings.update(req.guild.id, {
      category_id: b.category_id || null,
      support_role_id: b.support_role_id || null,
      log_channel_id: b.log_channel_id || null,
      panel_title: (b.panel_title || 'Поддержка').slice(0, 256),
      panel_description: (b.panel_description || '—').slice(0, 4000),
      welcome_message: (b.welcome_message || '—').slice(0, 4000),
      max_open_tickets: Math.min(10, Math.max(1, Number(b.max_open_tickets) || 1)),
    });
    flash(req, 'success', 'Настройки сохранены');
    res.redirect(`/guilds/${req.guild.id}`);
  });

  app.post('/guilds/:guildId/types', loadGuild, (req, res) => {
    const name = (req.body.name || '').trim().slice(0, 100);
    if (!name) {
      flash(req, 'error', 'Укажите название');
    } else if (db.ticketTypes.list(req.guild.id).length >= 25) {
      flash(req, 'error', 'Максимум 25 типов');
    } else {
      db.ticketTypes.create(req.guild.id, {
        name,
        emoji: (req.body.emoji || '').trim().slice(0, 32),
        description: (req.body.description || '').trim().slice(0, 100),
      });
      flash(req, 'success', 'Тип добавлен. Отправьте панель заново, чтобы обновить меню.');
    }
    res.redirect(`/guilds/${req.guild.id}#types`);
  });

  app.post('/guilds/:guildId/types/:typeId/delete', loadGuild, (req, res) => {
    db.ticketTypes.remove(req.guild.id, Number(req.params.typeId));
    flash(req, 'success', 'Тип удалён');
    res.redirect(`/guilds/${req.guild.id}#types`);
  });

  app.post('/guilds/:guildId/panel', loadGuild, async (req, res) => {
    const channel = req.guild.channels.cache.get(req.body.channel_id);
    if (!channel?.isTextBased()) {
      flash(req, 'error', 'Выберите текстовый канал');
    } else {
      try {
        await channel.send(buildPanel(req.guild.id));
        flash(req, 'success', `Панель отправлена в #${channel.name}`);
      } catch (err) {
        flash(req, 'error', `Не удалось отправить: ${err.message}`);
      }
    }
    res.redirect(`/guilds/${req.guild.id}#panel`);
  });

  // ---------- errors ----------
  app.use((req, res) => res.status(404).render('error', { message: 'Страница не найдена' }));
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    console.error('[web]', err);
    res.status(500).render('error', { message: 'Внутренняя ошибка сервера' });
  });

  return app;
}

module.exports = createServer;
