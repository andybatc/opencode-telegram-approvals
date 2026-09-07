# opencode-telegram-approvals

Puente bidireccional para **aprobar/denegar los permisos de opencode desde
Telegram**, con dos vías complementarias:

1. **Bridge externo** (`bridger/`): `opencode serve` + bot de Telegram. La vía
   completa: los permisos llegan a Telegram con botones **Approve/Deny** y la
   respuesta vuelve a opencode. (Funciona hoy.)
2. **Plugin de opencode** (`.opencode/plugins/telegram-permission.ts`): notifica
   cada permiso en Telegram sin servidor aparte. Los botones solo aparecen si el
   runtime expone la API de reply (el actual no la expone en TTY), así que hoy es
   **solo notificación**.

## ¿Qué resuelve?

Los permisos de opencode (leer archivo, ejecutar comandos) son diálogos locales
en el terminal. Este proyecto permite que esos prompts se reenvíen a Telegram y
que la respuesta (aprobar/denegar) vuelva a opencode, para supervisar y
autorizar desde el celular.

## Instalar el plugin (solo notificación)

Requiere una sola sesión de opencode y no necesita el bridge.

```bash
# 1. En tu proyecto opencode, crea la carpeta de plugins
mkdir -p .opencode/plugins

# 2. Copia el plugin y el package.json (declara la dependencia del SDK)
cp <repo>/.opencode/plugins/telegram-permission.ts .opencode/plugins/
cp <repo>/.opencode/package.json .opencode/

# 3. Instala la dependencia del SDK (la que el plugin necesita en build)
cd .opencode && bun install && cd ..

# 4. Configura el bot en la raíz del proyecto (.env) o exporta las vars
TELEGRAM_BOT_TOKEN=123456:ABC...   # de @BotFather
TELEGRAM_CHAT_ID=123456789          # tu chat con el bot
```

Reinicia opencode: cada permiso pedido aparece como mensaje `🔐` en el chat.
El mensaje se edita a "Resuelto desde el TTY" cuando respondes en el terminal.

> Para aprobar/denegar **desde Telegram con botones**, usa el bridge
> (`bridger/`), que sí resuelve permisos de forma completa.
>
> ⚠️ El plugin y el bridge usan polling del **mismo bot**: si ambos corren a la
> vez con permisos pendientes, Telegram devuelve `409 Conflict`. Usa uno u otro,
> no los dos simultáneamente.

## Bridge (aprobación desde Telegram)

```bash
# Requisitos: Python 3.11+, uv
cp .env.example .env   # completa TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENCODE_WORKING_DIR
uv sync
# Terminal 1: opencode en modo serve
opencode serve --port 4096
# Terminal 2: el bridge conecta a /event y reenvía los permisos al bot
uv run python -m bridger
```

Detalles de la vía bridge en `docs/`.

## Arquitectura

```
[opencode] ──permiso──▶ [bridger/plugin] ──envía a Telegram──▶ [bot Telegram]
     ▲                        │                                    │
     └────────respuesta────────┘◀───────approve/deny───────────────┘
```

- **bridger**: escucha `permission.asked` vía SSE (`GET /event` del serve),
  manda el permiso a Telegram con botones, y al tocar botón responde
  `POST /permission/:id/reply` (con header `x-opencode-directory`).
- **plugin**: emite la notificación desde dentro de opencode, sin serve.

## Stack

- Python + stdlib (bridge) · TypeScript (plugin) · Bot API de Telegram (sin libs).
