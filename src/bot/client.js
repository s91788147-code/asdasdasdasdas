const {
  ActionRowBuilder,
  Client,
  Events,
  GatewayIntentBits,
  MessageFlags,
  ModalBuilder,
  Partials,
  PermissionFlagsBits,
  TextInputBuilder,
  TextInputStyle,
} = require('discord.js');
const db = require('../db');
const { isStaff, buildPanel, ticketControls, openTicket, closeTicket } = require('./tickets');

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
  partials: [Partials.Channel],
});

const ephemeral = (content) => ({ content, flags: MessageFlags.Ephemeral });

function subjectModal(typeId) {
  return new ModalBuilder()
    .setCustomId(`ticket:modal:${typeId || 0}`)
    .setTitle('Новый тикет')
    .addComponents(new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId('subject')
        .setLabel('Кратко опишите проблему')
        .setStyle(TextInputStyle.Paragraph)
        .setMaxLength(1000)
        .setRequired(true),
    ));
}

client.once(Events.ClientReady, (c) => {
  console.log(`[bot] Logged in as ${c.user.tag}`);
});

// Log every message in ticket channels for transcripts and the admin panel.
client.on(Events.MessageCreate, (message) => {
  if (!message.guild || message.author.id === client.user.id) return;
  const ticket = db.tickets.byChannel(message.channelId);
  if (!ticket || ticket.status !== 'open') return;
  const attachments = [...message.attachments.values()].map((a) => a.url);
  const content = [message.content, ...attachments].filter(Boolean).join('\n');
  if (!content) return;
  db.messages.add({
    ticketId: ticket.id,
    authorId: message.author.id,
    authorTag: message.author.tag,
    content,
  });
});

// Mark ticket closed if its channel is deleted manually.
client.on(Events.ChannelDelete, (channel) => {
  const ticket = db.tickets.byChannel(channel.id);
  if (ticket && ticket.status === 'open') db.tickets.close(ticket.id, null);
});

client.on(Events.InteractionCreate, async (interaction) => {
  try {
    if (interaction.isChatInputCommand()) return await handleCommand(interaction);
    if (interaction.isButton()) return await handleButton(interaction);
    if (interaction.isStringSelectMenu()) return await handleSelect(interaction);
    if (interaction.isModalSubmit()) return await handleModal(interaction);
  } catch (err) {
    console.error('[bot] interaction error', err);
    const reply = ephemeral(`❌ ${err.message}`);
    if (interaction.deferred || interaction.replied) await interaction.editReply(reply).catch(() => {});
    else if (interaction.isRepliable()) await interaction.reply(reply).catch(() => {});
  }
});

async function handleCommand(interaction) {
  const { commandName, guild, member } = interaction;
  const settings = db.settings.get(guild.id);

  if (commandName === 'setup') {
    const category = interaction.options.getChannel('category');
    const role = interaction.options.getRole('support_role');
    const logChannel = interaction.options.getChannel('log_channel');
    const data = {};
    if (category) data.category_id = category.id;
    if (role) data.support_role_id = role.id;
    if (logChannel) data.log_channel_id = logChannel.id;
    db.settings.update(guild.id, data);
    const s = db.settings.get(guild.id);
    return interaction.reply(ephemeral([
      '✅ Настройки сохранены:',
      `Категория: ${s.category_id ? `<#${s.category_id}>` : '—'}`,
      `Роль поддержки: ${s.support_role_id ? `<@&${s.support_role_id}>` : '—'}`,
      `Канал логов: ${s.log_channel_id ? `<#${s.log_channel_id}>` : '—'}`,
    ].join('\n')));
  }

  if (commandName === 'panel') {
    const channel = interaction.options.getChannel('channel') || interaction.channel;
    await channel.send(buildPanel(guild.id));
    return interaction.reply(ephemeral(`✅ Панель отправлена в <#${channel.id}>`));
  }

  const ticket = db.tickets.byChannel(interaction.channelId);
  if (!ticket || ticket.status !== 'open') {
    return interaction.reply(ephemeral('Эта команда работает только внутри открытого тикета.'));
  }

  if (commandName === 'close') {
    if (!isStaff(member, settings) && member.id !== ticket.user_id) {
      return interaction.reply(ephemeral('Недостаточно прав.'));
    }
    await interaction.reply('Закрываю тикет…');
    return closeTicket(client, ticket, {
      closedById: member.id,
      closedByTag: interaction.user.tag,
      reason: interaction.options.getString('reason'),
    });
  }

  if (!isStaff(member, settings)) return interaction.reply(ephemeral('Только для команды поддержки.'));

  if (commandName === 'claim') return claim(interaction, ticket);

  if (commandName === 'add' || commandName === 'remove') {
    const user = interaction.options.getUser('user');
    if (commandName === 'add') {
      await interaction.channel.permissionOverwrites.edit(user.id, {
        ViewChannel: true, SendMessages: true, ReadMessageHistory: true, AttachFiles: true,
      });
      return interaction.reply(`➕ <@${user.id}> добавлен в тикет.`);
    }
    if (user.id === ticket.user_id) return interaction.reply(ephemeral('Нельзя убрать автора тикета.'));
    await interaction.channel.permissionOverwrites.delete(user.id);
    return interaction.reply(`➖ <@${user.id}> убран из тикета.`);
  }
}

async function claim(interaction, ticket) {
  if (ticket.claimed_by) {
    return interaction.reply(ephemeral(`Тикет уже взят: <@${ticket.claimed_by}>`));
  }
  db.tickets.claim(ticket.id, interaction.user.id);
  if (interaction.isButton()) {
    await interaction.update({ components: [ticketControls(true)] });
    return interaction.followUp(`🙋 <@${interaction.user.id}> взял тикет в работу.`);
  }
  return interaction.reply(`🙋 <@${interaction.user.id}> взял тикет в работу.`);
}

async function handleButton(interaction) {
  const { customId, guild, member } = interaction;

  if (customId === 'ticket:create') return interaction.showModal(subjectModal(0));

  const ticket = db.tickets.byChannel(interaction.channelId);
  if (!ticket || ticket.status !== 'open') return interaction.reply(ephemeral('Тикет уже закрыт.'));
  const settings = db.settings.get(guild.id);

  if (customId === 'ticket:claim') {
    if (!isStaff(member, settings)) return interaction.reply(ephemeral('Только для команды поддержки.'));
    return claim(interaction, ticket);
  }

  if (customId === 'ticket:close') {
    if (!isStaff(member, settings) && member.id !== ticket.user_id) {
      return interaction.reply(ephemeral('Недостаточно прав.'));
    }
    await interaction.reply('Закрываю тикет…');
    return closeTicket(client, ticket, { closedById: member.id, closedByTag: interaction.user.tag });
  }
}

async function handleSelect(interaction) {
  if (interaction.customId !== 'ticket:type') return;
  const typeId = Number(interaction.values[0]);
  await interaction.showModal(subjectModal(typeId));
  // Reset the select so the same option can be picked again.
  await interaction.message.edit(buildPanel(interaction.guildId)).catch(() => {});
}

async function handleModal(interaction) {
  if (!interaction.customId.startsWith('ticket:modal:')) return;
  const typeId = Number(interaction.customId.split(':')[2]);
  const type = typeId ? db.ticketTypes.get(typeId) : null;
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  if (!interaction.guild.members.me.permissions.has(PermissionFlagsBits.ManageChannels)) {
    return interaction.editReply('У бота нет права «Управлять каналами».');
  }

  const { channel } = await openTicket(interaction.guild, interaction.user, {
    typeName: type?.name,
    subject: interaction.fields.getTextInputValue('subject'),
  });
  return interaction.editReply(`✅ Тикет создан: <#${channel.id}>`);
}

module.exports = client;
