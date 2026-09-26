require('dotenv').config();
const { REST, Routes } = require('discord.js');
const commands = require('./commands');

async function deployCommands() {
  const { DISCORD_TOKEN, CLIENT_ID, GUILD_ID } = process.env;
  const rest = new REST().setToken(DISCORD_TOKEN);
  const route = GUILD_ID
    ? Routes.applicationGuildCommands(CLIENT_ID, GUILD_ID)
    : Routes.applicationCommands(CLIENT_ID);
  await rest.put(route, { body: commands });
  console.log(`[bot] Registered ${commands.length} slash commands${GUILD_ID ? ` in guild ${GUILD_ID}` : ' globally'}`);
}

if (require.main === module) {
  deployCommands().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = deployCommands;
