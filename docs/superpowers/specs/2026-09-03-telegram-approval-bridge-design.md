# opencode ↔ Telegram Approval Bridge — Diseño

> **Estado:** Aprobado (2026-09-03)
> **Alcance:** Fases 1-3 del plan (notificación unidireccional + retorno bidireccional + robustez)
> **Arquitectura:** Puente externo Python (decisión tomada en la Fase 0)

## Propósito

Permitir aprobar/denegar los permisos de opencode (leer archivo, ejecutar comandos) desde
Telegram sin tocar el terminal local. opencode dispara el evento `permission.asked` y un
puente lo reenvía a Telegram; el usuario responde con botones inline (o comandos `/approve`/`/deny`)
y la decisión vuelve a opencode vía HTTP.

## Arquitectura

```
┌─────────────┐    SSE /event     ┌──────────────┐    Bot API     ┌──────────┐
│   opencode   │ ──────────────── │   bridger     │ ───────────── │ Telegram  |
│  (serve)     │ ◀────────────────│   (Python)    │ ◀─────────────│  (user)   |
│              │  POST /reply     │               │  callback     │           |
└─────────────┘                   └──────────────┘   query        └──────────┘
```

**Componentes:**
- **bridger** (un solo proceso Python): escucha SSE de `opencode serve`, manda mensajes a
  Telegram con inline keyboards, recibe callbacks, responde vía HTTP a opencode.
- **opencode**: corre con `opencode serve` y `permission: "*": "ask"`.
- **Telegram**: usuario recibe notificación, toca Approve/Deny o escribe `/approve` `/deny`.

**Flujo completo:**
1. opencode pide permiso → evento `permission.asked` en SSE.
2. bridger formatea mensaje (qué se pide, patrón, contexto) y lo envía a Telegram con botones
   Approve/Deny.
3. Usuario toca botón → callback query llega al bridger.
4. bridger llama `POST /permission/:id/reply` con header `x-opencode-directory`.
5. bridger edita el mensaje original en Telegram confirmando "Aprobado ✅" o "Denegado ❌".

**Stack:** Python 3.11+, `python-telegram-bot`, `httpx`. Nada más.

## Estructura del repo

```
opencode-telegram-approvals/
├── bridger/
│   ├── __init__.py
│   ├── __main__.py          # entry point: python -m bridger
│   ├── config.py            # env vars, defaults
│   ├── sse_listener.py      # conecta a opencode SSE, parsea permission.asked
│   ├── telegram_bot.py      # python-telegram-bot setup, handlers
│   ├── opencode_client.py   # POST /permission/:id/reply
│   └── models.py            # dataclasses: PermissionRequest, Reply
├── docs/
├── tests/
│   ├── test_models.py
│   └── test_opencode_client.py
├── pyproject.toml
├── .env.example
└── README.md
```

## Configuración (env vars)

| Var | Default | Descripción |
|-----|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | — | Chat destino (personal o grupo) |
| `OPENCODE_SERVER_URL` | `http://127.0.0.1:4096` | URL del server de opencode |
| `OPENCODE_WORKING_DIR` | — | Dir de trabajo (header `x-opencode-directory`) |
| `BRIDGER_TIMEOUT` | `300` | Segundos antes de auto-rechazar un permiso pendiente |
| `BRIDGER_LOG_LEVEL` | `INFO` | Nivel de logging |

**pyproject.toml:** minimal, deps = `python-telegram-bot`, `httpx`. Script entry:
`bridger = "bridger.__main__:main"`.

## Lógica core

### `models.py`
```python
@dataclass
class PermissionRequest:
    id: str
    session_id: str
    tool: str          # "bash", "edit", "read", etc.
    patterns: list[str]
    metadata: dict     # command, cwd, etc.
    timestamp: float
```

### `sse_listener.py`
- Conecta a `GET /event` (SSE) de `opencode serve`
- Parsea eventos `permission.asked` y `permission.updated`
- Normaliza el payload: el ID puede ser `id`, `requestID`, o `permissionID` según la fuente
- Expone un `asyncio.Queue` de `PermissionRequest`
- Reconexión automática con backoff exponencial (1s → 2s → 4s → 8s → 16s → max 30s)
- En reconexión, consulta `GET /api/permission/request` para recuperar pendientes perdidos

### `telegram_bot.py`
- Inicia `python-telegram-bot` en modo polling
- Al recibir un `PermissionRequest` de la cola:
  - Formatea mensaje: "**Permiso solicitado**\nTool: `bash`\nComando: `git push origin main`\n\n¿Aprobar?"
  - Envía con `InlineKeyboardMarkup` de 2 botones: ✅ Approve / ❌ Deny
  - Guarda `request_id → message_id` en un dict para mapear callbacks
- Hanndler de callback query: extrae `request_id` de `callback_data`, llama a
  `opencode_client.reply()`, edita el mensaje original confirmando la decisión
- Handler de comandos `/approve [id]` y `/deny [id]` como fallback
- `/list` muestra permisos pendientes activos

### `opencode_client.py`
- `async def reply(request_id, reply, directory)`:
  - `POST /permission/{request_id}/reply`
  - Header: `x-opencode-directory: {directory}`
  - Body: `{"reply": "once"|"always"|"reject"}`
  - Retry 1x en 5xx, timeout 10s

## Robustez (Fase 3)

**Timeouts:**
- Cada `PermissionRequest` tiene timestamp. El bridger verifica cada 30s si hay requests
  pendientes > `BRIDGER_TIMEOUT` segundos.
- Si expira: responde `"reject"` a opencode, edita el mensaje en Telegram con "⏰ Timeout — auto-rechazado".

**Sesiones concurrentes:**
- El bridger usa `dict[session_id, list[PermissionRequest]]` para rastrear pendientes por sesión.
- `/list` muestra todos los pendientes con su session ID.
- Cada callback query lleva `request_id` embebido en `callback_data`, sin ambigüedad.

**Persistencia mínima:**
- En memoria nada más. Si el bridger muere, los pendientes se pierden (opencode timeoutea de
  todos modos). Log a stderr con `logging` stdlib, nivel configurable.

**Reconexión SSE:**
- Backoff exponencial (arriba). En cada reconexión se recuperan pendientes vía
  `GET /api/permission/request`.

**Signal handling:**
- `SIGINT`/`SIGTERM` → graceful shutdown: cancela tareas asyncio, cierra conexiones.

## Testing

- `test_models.py`: normalización de payload (diferentes formatos de ID/campos)
- `test_opencode_client.py`: mock de httpx, retry en 5xx, timeout
- No se testea el bot de Telegram directamente (requiere token real). La lógica de formateo
  de mensajes se testea separadamente.

## Fuera de alcance

- No se implementa plugin de opencode (futuro, decisión ya documentada)
- No auth/password (`OPENCODE_SERVER_PASSWORD`) — se asume server local sin password
