import { readFileSync, appendFileSync } from "node:fs"
import { join } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"

// Notifica en Telegram los permisos que opencode pide en cualquier sesión
// (TTY o serve). Usa el bot y chat del .env del proyecto.
// ponytail: parseo manual del .env, fetch nativo.

const LOG = "/tmp/telegram-plugin.log"
function plog(msg: string) {
  try {
    appendFileSync(LOG, `${new Date().toISOString()} ${msg}\n`)
  } catch {
    // sin log no es fatal
  }
}

let envCache: Record<string, string> | null = null

// Resuelve el .env relativo al propio plugin (../.. desde .opencode/plugins/)
// porque directory del PluginInput llega como objeto en el runtime real.
function envPath(): string {
  const here = (import.meta as any).dir ?? process.cwd()
  return join(here, "..", "..", ".env")
}

export function loadEnv(): Record<string, string> {
  if (envCache) return envCache
  // Env vars del proceso primero; un .env junto al proyecto las sobrescribe.
  envCache = { ...process.env }
  try {
    const raw = readFileSync(envPath(), "utf8")
    for (const line of raw.split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/)
      if (m && !line.trim().startsWith("#")) {
        envCache[m[1]] = m[2].replace(/^["']|["']$/g, "")
      }
    }
  } catch {
    // sin .env: se usan las env vars del proceso (o no hay notificación)
  }
  plog(`ENV keys=${Object.keys(envCache).join(",") || "(vacío)"} file=${envPath()}`)
  return envCache
}

function escMd(s: string): string {
  return s.replace(/([_*`[\]])/g, "\\$1")
}

export function formatPermission(input: any): string {
  const id = input.id ?? input.requestID ?? input.permissionID ?? "?"
  const tool = input.tool ?? "unknown"
  const cmd = input.metadata?.command ?? ""
  const patterns = Array.isArray(input.patterns) && input.patterns.length
    ? input.patterns.map(escMd).join(", ")
    : "(ninguno)"
  const lines = [
    "🔐 Permiso solicitado",
    `Tool: \`${escMd(tool)}\``,
    `Patrón: ${patterns}`,
    cmd ? `Comando: \`${escMd(cmd)}\`` : "",
    `ID: \`${escMd(id)}\``,
  ]
  return lines.filter(Boolean).join("\n")
}

// ---- Aprobación desde Telegram ----
// ponytail: polling con ventana activa (solo mientras hay pendientes) para
// no pelear 409 con el bridge ruta 2, que lleva polling continuo del MISMO
// bot. Si ambos corren a la vez el botón puede perderse: apagar el bridge
// cuando se quiera usar el botón del plugin.
let offset = 0 // offset de getUpdates, persistente en el módulo
const pending = new Map<string, { chat_id: number; message_id: number; ts: number; sessionID?: string }>()
let pendingTimer: ReturnType<typeof setInterval> | null = null
let inPoll = false
let client: any = null
let localBase: string | undefined // baseUrl del proceso local si el DIAG lo encuentra
// ¿El runtime permite responder permisos? Detección única en carga (DIAG).
// ponytail: el runtime actual NO expone reply de permiso TTY — sin botones que no
// responden. Cuando una versión futura lo exponga (o se use contra el serve headless
// con bridge), canReply=true y vuelven los botones Approve/Deny.
let canReply = false
// Base local descubierta por el DIAG (solo si existe; p.ej. contra el serve).
let diagBase = ""

function startPolling() {
  if (!pendingTimer) pendingTimer = setInterval(pollOnce, 2000)
}

function stopPollingIfIdle() {
  if (pending.size === 0 && pendingTimer) {
    clearInterval(pendingTimer)
    pendingTimer = null
  }
}

async function tgCall(token: string, method: string, body: Record<string, unknown>) {
  const resp = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10_000),
  })
  return (await resp.json()) as { ok?: boolean; description?: string; result?: any }
}

async function doReply(id: string, reply: "once" | "reject", chatId?: number, messageId?: number) {
  const env = loadEnv()
  const entry = pending.get(id)
  const sID = entry?.sessionID ?? ""
  try {
    if (typeof client?.permission?.reply === "function") {
      await client.permission.reply({ requestID: id, reply })
      plog(`REPLY-v2 id=${id} reply=${reply}`)
    } else if (sID && typeof client?.session?.permission?.reply === "function") {
      await client.session.permission.reply({ sessionID: sID, requestID: id, reply })
      plog(`REPLY-v2s id=${id} session=${sID} reply=${reply}`)
    } else if (localBase) {
      // Vía D: HTTP directo al proceso local (el client del runtime no expone permisos).
      // Con directorio del .env (OPENCODE_WORKING_DIR) para que el requestID matchee.
      const dir = loadEnv().OPENCODE_WORKING_DIR ?? ""
      const paths = [`/session/${sID}/permission/${id}/reply`, `/permission/${id}/reply`]
      let sent = false
      for (const p of paths) {
        try {
          const r = await fetch(`${localBase}${p}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...(dir ? { "x-opencode-directory": dir } : {}) },
            body: JSON.stringify({ reply }),
            signal: AbortSignal.timeout(10_000),
          })
          const body = (await r.json().catch(() => null)) as { error?: string } | null
          plog(`HTTP-DIRECT status=${r.status} path=${p} body=${JSON.stringify(body)?.slice(0, 200)}`)
          if (r.ok) {
            sent = true
            break
          }
        } catch (err) {
          plog(`HTTP-DIRECT err path=${p} err=${String(err)}`)
        }
      }
      if (!sent) return
    } else {
      plog(
        `REPLY unavailable session=${sID} clientKeys=${Object.keys(client ?? {}).join(",")} ` +
          `sessionKeys=${Object.keys(client?.session ?? {}).join(",")} ` +
          `sessionPerm=${typeof client?.session?.permission?.reply === "function" ? "ok" : "no"} localBase=${localBase ?? "n/a"}`,
      )
    }
  } catch (err) {
    plog(`REPLY err=${String(err)}`)
  }
  if (chatId && messageId) {
    try {
      await tgCall(env.TELEGRAM_BOT_TOKEN, "editMessageText", {
        chat_id: chatId,
        message_id: messageId,
        text: `🔐 ${reply === "once" ? "✅ Aprobado por Telegram" : "❌ Denegado por Telegram"} — \`${escMd(id)}\``,
        parse_mode: "Markdown",
      })
    } catch (err) {
      plog(`EDIT err=${String(err)}`)
    }
  }
  pending.delete(id)
  stopPollingIfIdle()
}

async function pollOnce() {
  if (inPoll) return
  inPoll = true
  try {
    const env = loadEnv()
    const now = Date.now()
    for (const [id, p] of pending) {
      if (now - p.ts > 120_000) {
        plog(`PENDING expired id=${id}`)
        pending.delete(id)
      }
    }
    if (pending.size === 0) {
      stopPollingIfIdle()
      return
    }
    const resp = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getUpdates?timeout=20&offset=${offset}`,
      { signal: AbortSignal.timeout(25_000) },
    )
    if (resp.status === 409) {
      plog("TELEGRAM 409 (poller concurrente: ¿bridge activo?)")
      return
    }
    const data = (await resp.json()) as { result?: Array<{ update_id: number; callback_query?: any }> }
    for (const u of data.result ?? []) {
      offset = Math.max(offset, u.update_id + 1)
      const cb = u.callback_query
      const cbData = cb?.data as string | undefined
      if (cbData?.startsWith("perm:")) {
        const [, id, reply] = cbData.split(":")
        plog(`CALLBACK id=${id} reply=${reply}`)
        await doReply(id, reply === "reject" ? "reject" : "once", cb.message?.chat?.id, cb.message?.message_id)
      }
    }
  } catch (err) {
    plog(`POLL err=${String(err)}`)
  } finally {
    inPoll = false
  }
}

async function notify(input: any): Promise<void> {
  const env = loadEnv()
  const token = env.TELEGRAM_BOT_TOKEN
  const chatId = env.TELEGRAM_CHAT_ID
  if (!token || !chatId) {
    plog(`MISSING token=${token ? "ok" : "NO"} chatId=${chatId ? "ok" : "NO"} keys=${Object.keys(env).join(",")}`)
    return
  }
  const id = input.id ?? "?"
  const text = formatPermission(input)
  const reply_markup = canReply
    ? {
        inline_keyboard: [[
          { text: "✅ Approve", callback_data: `perm:${id}:once` },
          { text: "❌ Deny", callback_data: `perm:${id}:reject` },
        ]],
      }
    : undefined
  try {
    const data = await tgCall(token, "sendMessage", {
      chat_id: chatId,
      text,
      parse_mode: "Markdown",
      disable_web_page_preview: true,
      ...(reply_markup ? { reply_markup } : {}),
    })
    plog(`API ok=${data.ok} desc=${data.description ?? ""} botones=${canReply ? "si" : "no"}`)
    if (data.ok && data.result?.message_id) {
      // pending SIEMPRE (aunque no haya botones): alimenta el cleanup por
      // permission.replied ("Resuelto desde el TTY") y la expiración.
      pending.set(id, {
        chat_id: Number(chatId),
        message_id: data.result.message_id,
        ts: Date.now(),
        sessionID: typeof input.sessionID === "string" ? input.sessionID : undefined,
      })
      if (canReply) startPolling()
    }
  } catch (err) {
    plog(`FETCH err=${String(err)}`)
  }
}

export default (async (input: any) => {
  client = input?.client
  plog("plugin-LOADED")
  // Diag del client real del runtime: ¿dónde vive el reply de permiso?
  const c = input?.client ?? {}
  const cu = c as any
  const sess = cu.session ?? {}
  const cc = cu._client ?? {}
  const sc = sess._client ?? {}
  const sink = (o: any) => (typeof o?.baseUrl === "string" ? o.baseUrl : typeof o?.url === "string" ? o.url : undefined)
  localBase = sink(cc) ?? sink(sc)
  plog(
    `DIAG clientKeys=${Object.keys(c).join(",")} sessionKeys=${Object.keys(sess).join(",")} ` +
      `perm=${typeof cu.permission?.reply === "function" ? "ok" : "no"} ` +
      `sessionPerm=${typeof sess.permission?.reply === "function" ? "ok" : "no"} ` +
      `clientClientKeys=${Object.keys(cc).join(",")} clientBase=${sink(cc) ?? "n/a"} ` +
      `sessionClientKeys=${Object.keys(sc).join(",")} sessBase=${sink(sc) ?? "n/a"} ` +
`sameClient=${cc === sc ? "same" : "diff"} localBase=${localBase ?? "n/a"}`,
    )
  canReply = typeof cu.permission?.reply === "function" || typeof sess.permission?.reply === "function" || !!localBase
  plog(`CANREPLY ${canReply ? "si" : "no"} (rutas reply: perm/session-perm/http-local)`)
  return {
    async event(input: any) {
      // Runtime real: el hook recibe { event: { id, type, properties } }.
      // (El SDK types.gen.d.ts declara "permission.updated" — no coincide con el runtime.)
      const evt = input?.event ?? input
      const t = evt?.type
      if (typeof t === "string" && t.startsWith("permission")) {
        plog(`EVT type=${t} raw=${JSON.stringify(input)?.slice(0, 400)}`)
      }
      if (t === "permission.asked" || t === "permission.updated") {
        const src = evt?.properties ?? evt
        const pat = Array.isArray(src.patterns)
          ? src.patterns
          : src.pattern != null
            ? Array.isArray(src.pattern)
              ? src.pattern
              : [src.pattern]
            : []
        const tool =
          typeof src.permission === "string"
            ? src.permission
            : typeof src.type === "string"
              ? src.type
              : typeof src.tool === "string"
                ? src.tool
                : "unknown"
        plog(`SRC id=${src.id} tool=${tool} patterns=${JSON.stringify(pat)} cmd=${JSON.stringify(src.metadata?.command ?? "")}`)
        await notify({
          id: src.id,
          tool,
          patterns: pat,
          metadata: src.metadata ?? {},
          sessionID: typeof src.sessionID === "string" ? src.sessionID : undefined,
        })
        return
      }
      // Permiso resuelto en otro lado (por ejemplo el TTY): quitar el botón
      // y dejar constancia, en lugar de dejar un botón huérfano.
      if (t === "permission.replied") {
        const rp = evt?.properties ?? evt
        const id = rp?.requestID ?? rp?.id
        const p = id && pending.get(id)
        if (p) {
          plog(`REPLIED elsewhere id=${id} reply=${rp?.reply}`)
          try {
            await tgCall(loadEnv().TELEGRAM_BOT_TOKEN, "editMessageText", {
              chat_id: p.chat_id,
              message_id: p.message_id,
              text: `🔐 Resuelto desde el TTY — \`${escMd(id)}\``,
              parse_mode: "Markdown",
            })
          } catch (err) {
            plog(`EDIT err=${String(err)}`)
          }
          pending.delete(id)
          stopPollingIfIdle()
        }
      }
    },
  }
}) satisfies Plugin