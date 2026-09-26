const { ChannelType, PermissionFlagsBits, SlashCommandBuilder } = require('discord.js');

const commands = [
  new SlashCommandBuilder()
    .setName('setup')
    .setDescription('Настроить тикет-систему')
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
    .setDMPermission(false)
    .addChannelOption((o) => o.setName('category').setDescription('Категория для тикетов')
      .addChannelTypes(ChannelType.GuildCategory))
    .addRoleOption((o) => o.setName('support_role').setDescription('Роль поддержки'))
    .addChannelOption((o) => o.setName('log_channel').setDescription('Канал для логов')
      .addChannelTypes(ChannelType.GuildText)),

  new SlashCommandBuilder()
    .setName('panel')
    .setDescription('Отправить панель создания тикетов')
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
    .setDMPermission(false)
    .addChannelOption((o) => o.setName('channel').setDescription('Канал (по умолчанию текущий)')
      .addChannelTypes(ChannelType.GuildText)),

  new SlashCommandBuilder()
    .setName('close')
    .setDescription('Закрыть текущий тикет')
    .setDMPermission(false)
    .addStringOption((o) => o.setName('reason').setDescription('Причина').setMaxLength(500)),

  new SlashCommandBuilder()
    .setName('claim')
    .setDescription('Взять текущий тикет в работу')
    .setDMPermission(false),

  new SlashCommandBuilder()
    .setName('add')
    .setDescription('Добавить пользователя в тикет')
    .setDMPermission(false)
    .addUserOption((o) => o.setName('user').setDescription('Пользователь').setRequired(true)),

  new SlashCommandBuilder()
    .setName('remove')
    .setDescription('Убрать пользователя из тикета')
    .setDMPermission(false)
    .addUserOption((o) => o.setName('user').setDescription('Пользователь').setRequired(true)),
];

module.exports = commands.map((c) => c.toJSON());
