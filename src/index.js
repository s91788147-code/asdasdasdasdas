require('dotenv').config();
const client = require('./bot/client');
const createServer = require('./web/server');
const deployCommands = require('./bot/deploy-commands');

async function main() {
  const { DISCORD_TOKEN, CLIENT_ID, PORT = 3000 } = process.env;
  if (!DISCORD_TOKEN || !CLIENT_ID) {
    console.error('DISCORD_TOKEN и CLIENT_ID обязательны (см. .env.example)');
    process.exit(1);
  }
  if (!process.env.ADMIN_PASSWORD) {
    console.warn('[web] ADMIN_PASSWORD не задан — вход в админку невозможен');
  }

  await deployCommands().catch((err) => console.error('[bot] Failed to register commands:', err.message));
  await client.login(DISCORD_TOKEN);

  createServer(client).listen(PORT, () => {
    console.log(`[web] Admin panel: http://localhost:${PORT}`);
  });
}

main();
