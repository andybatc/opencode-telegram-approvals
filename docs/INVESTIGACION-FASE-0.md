# Fase 0 — Investigación del mecanismo de permisos de opencode

> **Estado:** ✅ Completada (2026-09-03)
> **Versión objetivo:** opencode 1.18.x
> **Fuentes:** github.com/anomalyco/opencode (dev branch) + opencode.ai/docs/{permissions,plugins,sdk,server,cli,config,ecosystem}

## Conclusión

opencode **tiene hooks y una API HTTP de primera clase** para exactamente lo que
necesita el puente. No hace falta nada oculto ni un driver TTY.

Flujo canónico: cuando opencode pide permiso dispara el evento **`permission.asked`**
en un stream SSE y dentro de los hooks de plugin. Se responde programáticamente con
**`client.permission.reply({ requestID, reply })`** o con un **`POST /permission/:id/reply`**
HTTP.

Un puente de aprobación remota real ya existe (el demo BLE de Espressif) y prueba que
el patrón funciona end-to-end. Nuestro puente es el primero dedicado a Telegram, pero
el mecanismo de interceptar/responder está 100% documentado.

---

## 1. Configuración de permisos

En `opencode.json[c]`, bloque `permission`:

```jsonc
{
  "permission": {
    "*": "ask",        // default global para todas las tools
    "bash": "allow",
    "edit": "deny"
  }
}
```

Tres modos: `"allow"` (sin prompt), `"ask"` (pide aprobación), `"deny"` (bloquea).
**Gana la última regla** que matchea; convención: `"*"` primero, reglas específicas después.
Comodines `*` (0+ chars) y `?` (1 char); `~`/`$HOME` se expanden al inicio del patrón.

Claves disponibles: `read`, `edit` (cubre edit/write/patch), `glob`, `grep`, `bash`,
`task`, `skill`, `lsp`, `question`, `webfetch`, `websearch`, `external_directory`,
`doom_loop`.

Defaults: la mayoría `allow`; `external_directory` y `doom_loop` (misma tool repetida 3×)
= `ask`; `read` = `allow` pero `.env*` = `deny`.

Override por env var: `OPENCODE_PERMISSION=<JSON inline>`.

## 2. Hooks = plugins JS/TS (NO son hooks de comando shell)

No existe el bloque `hooks:` estilo Claude Code. Los hooks viven en **plugins
JavaScript/TypeScript** en `.opencode/plugins/`, `~/.config/opencode/plugins/`, o vía
la clave `plugin` de npm. Un plugin exporta:

```ts
export const MyPlugin = async ({ client, project, directory, ... }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "permission.asked")  { /* prompt mostrado */ }
      if (event.type === "permission.replied") { /* prompt resuelto */ }
    },
  }
}
```

### Eventos exactos

- **`permission.asked`** — opencode decide pedir permiso y la tool queda bloqueada esperando.
  Payload (struct `Request`):
  ```json
  {
    "type": "permission.asked",
    "properties": {
      "id": "per_01JXYZ...",
      "sessionID": "abc123",
      "permission": "bash",
      "patterns": ["git push origin main"],
      "metadata": { "command": "git push origin main", "cwd": "/home/andy/repo" },
      "always": ["git push *"],
      "tool": { "messageID": "msg_...", "callID": "call_..." }
    }
  }
  ```
- **`permission.replied`** — se resuelve. Properties: `{ sessionID, requestID, reply }`.

Reply = `"once"` | `"always"` | `"reject"`.

Otros eventos útiles: `tool.execute.before/after`, `question.asked/replied`,
`shell.env`, `session.idle`, `server.connected`, `lsp`, `todo`, etc.

## 3. Inyección programática (responder sin TTY) — 3 vías

### (a) HTTP crudo (la más simple, sin SDK)
`opencode serve` expone HTTP (default `127.0.0.1:4096`, config `server.port`).

```
POST /permission/:requestID/reply
Content-Type: application/json
x-opencode-directory: <cwd url-encoded>        // HEADER REQUERIDO
[Authorization: Basic ...]                       // si OPENCODE_SERVER_PASSWORD está set

{ "reply": "once" | "always" | "reject", "message": "razón opcional" }
```

Solo necesita `fetch` + el `requestID` del evento + el header de directorio. Es la ruta
que usa el puente oficial de Espressif como fallback. **No necesita session ID.**

### (b) SDK (recomendado)
```ts
import { createOpencodeClient } from "@opencode-ai/sdk"
const client = createOpencodeClient({ baseUrl: "http://localhost:4096" })

client.permission.reply({
  requestID,          // del evento permission.asked
  reply: "once" | "always" | "reject",
  message?,           // razón opcional del reject
  directory,
})
```
También ruta v2: `POST /api/session/:sessionID/permission/:requestID/reply`.

### (c) CLI auto-aprobar
- `opencode --auto` / `opencode run --auto` — aprueba todo lo que no esté `"deny"`.
- **No existe** la flag `--dangerously-bypass-approvals-and-sandbox` (eso es Claude Code).
  El bypass seguro actual = `--auto` o `permission: "allow"`.

### Lado receptor (vigilar el prompt)
- SDK: `client.event.subscribe()` → `for await (const event of stream)` yields `{ type, properties }`.
- HTTP raw: `GET /event` (SSE; primer evento `server.connected`, luego bus events incl.
  `permission.asked`). También `GET /global/event`.

⚠️ Los endpoints `/tui/control/*` manejan el UI de question/prompt de la TUI, **NO** los
permisos. No enrutar el reply de permisos por ahí.

## 4. Proyectos de referencia

- **Espressif ESP-IDF BLE UART bridge demo** (oficial, Apache-2.0) en
  `espressif/esp-idf` → `tools/ble/ble_uart_bridge/demos/opencode/`. Es un **plugin de
  opencode**: hooke `event` matcheando `permission.asked`/`permission.updated`, normaliza
  el payload, lo manda a un dispositivo BLE, recibe decisión → `replyToOpenCodePermission`
  → `client.permission.reply` / raw fetch. **Blueprint exacto: solo cambia transporte BLE
  por Telegram.** Archivos clave: `opencode-ble-uart-bridge.ts`,
  `opencode-permission-reply.ts` (fallback HTTP + headers/URL exactos), `permission-payload.ts`.
  `normalizePermissionEvent` maneja las diferencias de nombres de campos.
- **kimaki** (`remorses/kimaki`, MIT, ~1.4k★, en el ecosistema oficial): bot de Discord
  para controlar sesiones de opencode vía SDK; maneja `permission.asked` y responde con
  `client.permission.reply`, con timeout/reject-on-away. Es lo más cercano (Discord).
- openwork, assistant-ui, MiMo-Code/openscience/kilocode: confirman superficie API estable.

Ninguno es un plugin dedicado de aprobación opencode→Telegram. **El nuestro es novedoso,
pero el mecanismo está totalmente establecido.**

## 5. Bloqueos (no intentar lo imposible)

- ❌ No hay hooks de comando shell (bloque `hooks:` estilo Claude Code). Hook = plugin JS.
- ❌ No hay archivo de pendientes en disco: las peticiones viven in-process (Map en el
  servicio de Permission). Lo consultable es `GET /api/permission/request` (lista de
  pendientes) y `GET /api/session/:id/permission/`.
- ❌ No existe la flag `--dangerously-bypass`.
- ⚠️ Los nombres de campos del payload difieren levemente entre el stream del SDK y el
  hook del plugin (`permission`/`patterns` vs `type`/`pattern`). Un puente robusto debe
  aceptar ambos (`permissionID`/`requestID`/`id` como ID, y `permission.asked` y
  `permission.updated` como tipo). Referencia: `normalizePermissionEvent` de Espressif.

## 6. Arquitectura canónica (2 rutas equivalentes)

1. **Como plugin de opencode** (`.opencode/plugins/telegram-permission.ts`): recibe
   `client` (SDK) y `$` (shell) gratis; hook `event` → `permission.asked` → POST a la
   Bot API de Telegram → espera `/allow`|`/deny` → `client.permission.reply(...)`.
   Enfoque Espressif, el más limpio (client inyectado).
2. **Como puente externo Python/Node**: correr `opencode serve`, `GET /event` (SSE) para
   `permission.asked`, mandar mensaje de Telegram con teclado inline, y en el callback
   `POST /permission/:requestID/reply` con header `x-opencode-directory` (capturar el
   directorio al arrancar). No necesita plugin de opencode; el más robusto a upgrades.

---

## Punto de integración exacto (resumen)

```
GET /event (SSE)  ──►  permission.asked  ──►  send Telegram msg (inline keyboard)
                                                    │
                                              user taps /allow | /deny
                                                    │
POST /permission/:id/reply  ──►  opencode resuelve el prompt
```
o equivalente vía plugin con `client.permission.reply`.
