# SearchKaro WhatsApp (Baileys)

Bridge that uses [Baileys](https://baileys.wiki/) (WhatsApp Web protocol) to post free-course updates to a **WhatsApp group or Channel**.

> Unofficial library — not affiliated with WhatsApp. Use responsibly; spam can get numbers banned.

## Why a separate service?

Baileys needs:

1. A **long-running Node process**
2. **QR login once**, then saved session (`auth_info/`)
3. Outbound WebSocket to WhatsApp

GitHub Actions cannot host that reliably. Actions only **HTTP POST** into this bridge.

```
GitHub Actions (daily courses)
        │  POST /send
        ▼
Your VPS / PC / Railway  ← Baileys socket → WhatsApp Channel/Group
```

## Install (on a PC or VPS)

```bash
cd whatsapp-baileys
npm install
export API_SECRET="pick-a-long-random-string"
export TARGET_JID="YOUR_CHANNEL_OR_GROUP_JID"
npm start
```

Scan the **QR code** in the terminal with WhatsApp → **Linked devices**.

Keep the process running (`pm2`, `systemd`, or Docker).

### Env vars

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | no | Default `8787` |
| `API_SECRET` | yes (prod) | Bearer token for `/send` |
| `TARGET_JID` | yes | Destination JID |
| `LOG_LEVEL` | no | `warn` / `info` / `debug` |

### JID formats

| Destination | Example |
|-------------|---------|
| Personal chat | `923001234567@s.whatsapp.net` |
| Group | `1203630...@g.us` |
| **Channel (newsletter)** | `1203630...@newsletter` |

**How to get a group JID**

1. Add your linked number to the group  
2. Temporarily log messages in the bot, or use any Baileys “list chats” snippet  
3. Copy the `...@g.us` id

**How to get a Channel JID**

1. Open the channel in WhatsApp (you must be admin to post)  
2. Channel IDs look like `120363xxxxxxxxxx@newsletter`  
3. Some tools show it in invite / admin APIs; with Baileys you can also inspect `chats` after open

## Test send

```bash
curl -X POST http://127.0.0.1:8787/send \
  -H "Authorization: Bearer YOUR_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"text":"Test from SearchKaro Baileys bridge"}'
```

Health:

```bash
curl http://127.0.0.1:8787/health
```

## Connect GitHub Actions

Repo **Settings → Secrets**:

| Secret | Value |
|--------|--------|
| `BAILEYS_WEBHOOK_URL` | `https://your-public-host:8787/send` (or tunnel URL) |
| `BAILEYS_API_SECRET` | same as `API_SECRET` on the server |
| `SITE_BASE_URL` | `https://searchkaro.online` |

The daily courses workflow calls `scripts/notify_whatsapp.py`, which posts to this webhook when provider is `baileys` or `webhook`.

### Public URL without a VPS

For testing, use [ngrok](https://ngrok.com/) or Cloudflare Tunnel:

```bash
ngrok http 8787
# use the https URL + /send as BAILEYS_WEBHOOK_URL
```

## pm2 (recommended on VPS)

```bash
npm i -g pm2
cd whatsapp-baileys
pm2 start src/index.js --name searchkaro-wa
pm2 save
pm2 startup
```

## Security notes

- Never commit `auth_info/` (session = full account access)
- Always set `API_SECRET`
- Prefer a **dedicated WhatsApp number** for automation
- Do not blast spam; post only useful course updates
