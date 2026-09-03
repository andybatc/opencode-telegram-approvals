# opencode-telegram-approvals

Puente bidireccional para **aprobar/denegar los permisos de opencode desde
Telegram**.

## ¿Qué resuelve?

Los permisos de opencode (leer archivo, ejecutar comandos) son diálogos locales
en el terminal. Este proyecto permite que esos prompts se reenvíen a Telegram y
que la respuesta (aprobar/denegar) vuelva a opencode, para supervisar y
autorizar desde el celular.

## Estado

🚧 **Fase 0 completada / esqueleto.** El puente aún no está implementado, pero la
viabilidad ya está confirmada: opencode expone el evento `permission.asked` y permite
responder programáticamente (`POST /permission/:id/reply` o `client.permission.reply()`).
Ver `docs/INVESTIGACION-FASE-0.md`.

## Arquitectura (borrador)

```
[opencode] ──permiso──▶ [bridger] ──envía a Telegram──▶ [bot Telegram]
     ▲                        │                              │
     └────────respuesta────────┘◀───────approve/deny────────┘
```

- **bridger**: intercepta el evento de permiso de opencode, lo manda vía
  `hermes send -t telegram:...` y espera la respuesta del usuario.
- **bot/gateway**: recibe la decisión (`/approve`, `/deny`) y la traduce de
  vuelta a la API de permisos de opencode.

### Decisiones (resueltas en Fase 0)

- [x] Mecanismo de interceptación de permisos: evento `permission.asked` via SSE
  (`GET /event`) o hook de plugin (`event`).
- [x] Cómo responder sin bloquear: `POST /permission/:requestID/reply` (HTTP, con
  header `x-opencode-directory`) o `client.permission.reply()` (SDK). No hay driver TTY.
- [ ] Cómo esperar la respuesta de Telegram (long-poll vs webhook) sin bloquear el
  loop de opencode.

### Decisión de arquitectura (2 rutas válidas)

1. **Plugin de opencode** (`.opencode/plugins/telegram-permission.ts`): el client SDK
   viene inyectado; enfoque Espressif (blueprint oficial).
2. **Puente externo Python/Node**: `opencode serve` + `GET /event` + `POST /permission`
   — más robusto a upgrades, no requiere plugin.

Se recomienda arrancar por la ruta 2 (puente externo) por ser la más simple y estable,
y dejar la 1 como mejora futura.

## Cómo empezar a construir

Ver `docs/PLAN.md` para el plan detallado por fases.

## Stack sugerido

- Python + stdlib (lazy) o mínimo de deps.
- Hermes para el envío/recepción de Telegram (`hermes send`).
- GitHub Actions opcional para CI del puente.
