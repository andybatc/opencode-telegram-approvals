# opencode-telegram-approvals

## Plan de construcción (por fases)

### Fase 0 — Investigar mecanismo de permisos de opencode ✅
- **Hecho (2026-09-03).** Ver `docs/INVESTIGACION-FASE-0.md` para el detalle completo.
- Hallazgo clave: opencode dispara el evento `permission.asked` (SSE + hook de plugin)
  y se responde con `POST /permission/:id/reply` (HTTP) o `client.permission.reply()`
  (SDK). **No hace falta driver TTY.**
- Hay un blueprint oficial (demo BLE de Espressif, plugin de opencode) que vale como
  plantilla exacta: solo cambia el transporte BLE por Telegram.

### Fase 1 — Prueba de concepto (unidireccional)
- Cuando opencode pide permiso, el bridger notifica a Telegram vía
  `hermes send -t telegram:1083549311 "<qué se pide>"`.
- No resuelve la decisión todavía. Valida que la notificación sea confiable.
- Meta: ver el prompt de permiso reflejado en Telegram.

### Fase 2 — Retorno bidireccional (MVP)
- Arrancar `opencode serve` (o usar el plugin de opencode) y suscribirse a
  `permission.asked`.
- Ante un prompt, enviar a Telegram un mensaje con teclado inline (approve/deny).
- El usuario responde desde Telegram; el bridger traduce y resuelve el prompt vía
  `POST /permission/:requestID/reply` con header `x-opencode-directory` (capturado al
  arrancar), o `client.permission.reply({ requestID, reply })`.
- Meta: aprobar/denegar un permiso desde Telegram sin tocar el terminal.

### Fase 3 — Robustez
- Timeouts, sesiones concurrentes, persistencia de pendientes.
- Logging y reintentos del envío a Telegram (la red api.telegram.org es
  intermitente en esta máquina).

## Estructura del repo (objetivo)

```
opencode-telegram-approvals/
├── README.md
├── docs/PLAN.md
├── bridger/          # lógica de interceptación + retorno
├── gateway/          # capa de Telegram (envío/recepción)
└── tests/
```
