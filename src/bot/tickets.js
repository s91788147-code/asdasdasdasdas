const {
  ActionRowBuilder,
  AttachmentBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
  StringSelectMenuBuilder,
} = require('discord.js');
const db = require('../db');

const COLOR = 0x5865f2;
const CLOSE_DELAY_MS = 5000;

function isStaff(member, settings) {
  if (!member) return false;
  if (member.permissions.has(PermissionFlagsBits.ManageGuild)) return true;
  return Boolean(settings.support_role_id && member.roles.cache.has(settings.support_role_id));
}

function buildPanel(guildId) {
  const s = db.settings.get(guildId);
  const types = db.ticketTypes.list(guildId);

  const embed = new EmbedBuilder()
    .setColor(COLOR)
    .setTitle(s.panel_title)
    .setDescription(s.panel_description);

  let row;
  if (types.length) {
    const menu = new StringSelectMenuBuilder()
      .setCustomId('ticket:type')
      .setPlaceholder('Выберите тип обращения')
      .addOptions(types.slice(0, 25).map((t) => {
        const opt = { label: t.name.slice(0, 100), value: String(t.id) };
        if (t.description) opt.description = t.description.slice(0, 100);
        if (t.emoji) opt.emoji = t.emoji;
        return opt;
      }));
    row = new ActionRowBuilder().addComponents(menu);
  } else {
    row = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('ticket:create')
        .setLabel('Создать тикет')
        .setEmoji('🎫')
        .setStyle(ButtonStyle.Primary),
    );
  }
  return { embeds: [embed], components: [row] };
}

function ticketControls(claimed = false) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId('ticket:claim')
      .setLabel(claimed ? 'Взят в работу' : 'Взять')
      .setEmoji('🙋')
      .setStyle(ButtonStyle.Secondary)
      .setDisabled(claimed),
    new ButtonBuilder()
      .setCustomId('ticket:close')
      .setLabel('Закрыть')
      .setEmoji('🔒')
      .setStyle(ButtonStyle.Danger),
  );
}

async function openTicket(guild, user, { typeName, subject }) {
  const s = db.settings.get(guild.id);

  if (db.tickets.countOpenByUser(guild.id, user.id) >= s.max_open_tickets) {
    throw new Error(`У вас уже есть открытые тикеты (лимит: ${s.max_open_tickets}).`);
  }

  const ticket = db.tickets.create({
    guildId: guild.id,
    userId: user.id,
    userTag: user.tag,
    typeName,
    subject,
  });

  const overwrites = [
    { id: guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
    {
      id: user.id,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ReadMessageHistory,
        PermissionFlagsBits.AttachFiles,
      ],
    },
    {
      id: guild.client.user.id,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ManageChannels,
        PermissionFlagsBits.ReadMessageHistory,
      ],
    },
  ];
  if (s.support_role_id) {
    overwrites.push({
      id: s.support_role_id,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ReadMessageHistory,
        PermissionFlagsBits.AttachFiles,
      ],
    });
  }

  let channel;
  try {
    channel = await guild.channels.create({
      name: `ticket-${String(ticket.id).padStart(4, '0')}`,
      type: ChannelType.GuildText,
      parent: s.category_id || undefined,
      topic: `Тикет #${ticket.id} | ${user.tag} (${user.id})${subject ? ` | ${subject}` : ''}`.slice(0, 1024),
      permissionOverwrites: overwrites,
    });
  } catch (err) {
    db.tickets.remove(ticket.id);
    throw new Error(`Не удалось создать канал: ${err.message}`);
  }
  db.tickets.setChannel(ticket.id, channel.id);

  const embed = new EmbedBuilder()
    .setColor(COLOR)
    .setTitle(`Тикет #${ticket.id}${typeName ? ` — ${typeName}` : ''}`)
    .setDescription(s.welcome_message.replaceAll('{user}', `<@${user.id}>`))
    .setTimestamp();
  if (subject) embed.addFields({ name: 'Тема', value: subject.slice(0, 1024) });

  await channel.send({
    content: `<@${user.id}>${s.support_role_id ? ` <@&${s.support_role_id}>` : ''}`,
    embeds: [embed],
    components: [ticketControls(false)],
  });

  await log(guild, new EmbedBuilder()
    .setColor(0x57f287)
    .setTitle('Тикет открыт')
    .addFields(
      { name: 'Тикет', value: `#${ticket.id} (<#${channel.id}>)`, inline: true },
      { name: 'Пользователь', value: `<@${user.id}>`, inline: true },
      { name: 'Тип', value: typeName || '—', inline: true },
    )
    .setTimestamp());

  return { ticket: db.tickets.get(ticket.id), channel };
}

function buildTranscript(ticket) {
  const lines = [
    `Тикет #${ticket.id}`,
    `Пользователь: ${ticket.user_tag} (${ticket.user_id})`,
    `Тип: ${ticket.type_name || '—'}`,
    `Тема: ${ticket.subject || '—'}`,
    `Открыт: ${new Date(ticket.created_at).toISOString()}`,
    '',
  ];
  for (const m of db.messages.list(ticket.id)) {
    lines.push(`[${new Date(m.created_at).toISOString()}] ${m.author_tag}${m.from_panel ? ' (панель)' : ''}: ${m.content}`);
  }
  return lines.join('\n');
}

async function closeTicket(client, ticket, { closedById, closedByTag, reason } = {}) {
  if (ticket.status === 'closed') return;
  db.tickets.close(ticket.id, closedById || null);

  const guild = await client.guilds.fetch(ticket.guild_id).catch(() => null);
  const transcript = new AttachmentBuilder(Buffer.from(buildTranscript(ticket), 'utf8'), {
    name: `ticket-${ticket.id}.txt`,
  });

  if (guild) {
    await log(guild, new EmbedBuilder()
      .setColor(0xed4245)
      .setTitle('Тикет закрыт')
      .addFields(
        { name: 'Тикет', value: `#${ticket.id}`, inline: true },
        { name: 'Автор', value: `<@${ticket.user_id}>`, inline: true },
        { name: 'Закрыл', value: closedByTag || '—', inline: true },
        { name: 'Причина', value: reason || '—' },
      )
      .setTimestamp(), [transcript]);
  }

  const user = await client.users.fetch(ticket.user_id).catch(() => null);
  if (user) {
    await user.send({
      content: `Ваш тикет #${ticket.id}${guild ? ` на сервере **${guild.name}**` : ''} закрыт.${reason ? `\nПричина: ${reason}` : ''}`,
    }).catch(() => {});
  }

  const channel = ticket.channel_id ? await client.channels.fetch(ticket.channel_id).catch(() => null) : null;
  if (channel) {
    await channel.send(`🔒 Тикет закрыт${closedByTag ? ` (${closedByTag})` : ''}. Канал будет удалён через ${CLOSE_DELAY_MS / 1000} сек.`)
      .catch(() => {});
    setTimeout(() => channel.delete(`Ticket #${ticket.id} closed`).catch(() => {}), CLOSE_DELAY_MS);
  }
}

async function log(guild, embed, files = []) {
  const { log_channel_id: id } = db.settings.get(guild.id);
  if (!id) return;
  const channel = await guild.channels.fetch(id).catch(() => null);
  if (channel?.isTextBased()) await channel.send({ embeds: [embed], files }).catch(() => {});
}

module.exports = { isStaff, buildPanel, ticketControls, openTicket, closeTicket, buildTranscript };
