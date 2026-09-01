/**
 * SearchKaro WhatsApp bridge (Baileys)
 * Docs: https://baileys.wiki/
 *
 * 1. npm install && npm start
 * 2. Scan QR with WhatsApp → Linked Devices
 * 3. Set env TARGET_JID (group @g.us or channel @newsletter)
 * 4. Point GitHub secret BAILEYS_WEBHOOK_URL to https://YOUR_HOST:PORT/send
 *
 * POST /send
 *   Header: Authorization: Bearer <API_SECRET>
 *   Body: { "text": "message", "jid": "optional override" }
 */

import http from 'http'
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys'
import { Boom } from '@hapi/boom'
import pino from 'pino'
import qrcode from 'qrcode-terminal'
import { mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, '..')
const AUTH_DIR = join(ROOT, 'auth_info')

const PORT = Number(process.env.PORT || 8787)
const API_SECRET = process.env.API_SECRET || process.env.BAILEYS_API_SECRET || ''
const TARGET_JID = process.env.TARGET_JID || process.env.WHATSAPP_TARGET_JID || ''

mkdirSync(AUTH_DIR, { recursive: true })

const logger = pino({ level: process.env.LOG_LEVEL || 'warn' })

/** @type {import('@whiskeysockets/baileys').WASocket | null} */
let sock = null
let isOpen = false

async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      console.log('\n📱 Scan this QR with WhatsApp → Linked Devices:\n')
      qrcode.generate(qr, { small: true })
    }

    if (connection === 'open') {
      isOpen = true
      console.log('✅ WhatsApp connected (Baileys)')
      if (TARGET_JID) console.log('🎯 Default TARGET_JID =', TARGET_JID)
      else console.log('⚠️  TARGET_JID not set — pass jid in POST body')
    }

    if (connection === 'close') {
      isOpen = false
      const code = new Boom(lastDisconnect?.error)?.output?.statusCode
      const loggedOut = code === DisconnectReason.loggedOut
      console.log('Connection closed. code=', code, 'loggedOut=', loggedOut)
      if (!loggedOut) {
        console.log('Reconnecting…')
        startSocket()
      } else {
        console.log('Logged out. Delete auth_info/ and run again to scan a new QR.')
      }
    }
  })
}

function json(res, status, body) {
  const data = JSON.stringify(body)
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(data),
  })
  res.end(data)
}

function authorize(req) {
  if (!API_SECRET) return true // open only if you intentionally leave secret empty (not recommended)
  const header = req.headers.authorization || ''
  const token = header.startsWith('Bearer ') ? header.slice(7) : header
  return token && token === API_SECRET
}

async function readBody(req) {
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const raw = Buffer.concat(chunks).toString('utf8')
  if (!raw) return {}
  return JSON.parse(raw)
}

async function sendText(jid, text) {
  if (!sock || !isOpen) throw new Error('WhatsApp socket not ready')
  if (!jid) throw new Error('Missing jid')
  if (!text || !String(text).trim()) throw new Error('Missing text')

  // Supports:
  //   92300...@s.whatsapp.net  (personal)
  //   1203...@g.us             (group)
  //   1203...@newsletter       (WhatsApp Channel / newsletter)
  const result = await sock.sendMessage(jid, { text: String(text) })
  return result
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/health') {
      return json(res, 200, {
        ok: true,
        whatsapp: isOpen ? 'connected' : 'disconnected',
        target: TARGET_JID || null,
      })
    }

    if (req.method === 'POST' && (req.url === '/send' || req.url?.startsWith('/send?'))) {
      if (!authorize(req)) return json(res, 401, { error: 'unauthorized' })

      const body = await readBody(req)
      const jid = (body.jid || TARGET_JID || '').trim()
      const text = body.text || body.message || body.body || ''

      const msg = await sendText(jid, text)
      return json(res, 200, {
        ok: true,
        id: msg?.key?.id || null,
        jid,
      })
    }

    return json(res, 404, { error: 'not_found', try: ['GET /health', 'POST /send'] })
  } catch (err) {
    console.error(err)
    return json(res, 500, { error: String(err?.message || err) })
  }
})

server.listen(PORT, () => {
  console.log(`SearchKaro Baileys bridge listening on :${PORT}`)
  console.log('GET  /health')
  console.log('POST /send  { "text": "...", "jid": "optional" }')
  startSocket()
})
