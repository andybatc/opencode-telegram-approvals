# opencode-telegram-approvals

Puente bidireccional para **aprobar/denegar los permisos de opencode desde
Telegram**.

## ¿Qué resuelve?

Los permisos de opencode (leer archivo, ejecutar comandos) son diálogos locales
en el terminal. Este proyecto permite que esos prompts se reenvíen a Telegram y
que la respuesta (aprobar/denegar) vuelva a opencode, para supervisar y
autorizar desde el celular.

## Estado

⚠️ **Esqueleto.** El puente no está implementado todavía. Este repo define la
arquitectura y el plan de construcción.

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

### Decisiones pendientes (antes de implementar)

- [ ] Mecanismo de interceptación de permisos en opencode (hooks vs API).
- [ ] Cómo esperar la respuesta de Telegram sin bloquear el loop de opencode.
- [ ] Canal de retorno: `approval.respond` de Hermes vs llamada directa.

## Cómo empezar a construir

Ver `docs/PLAN.md` para el plan detallado por fases.

## Stack sugerido

- Python + stdlib (lazy) o mínimo de deps.
- Hermes para el envío/recepción de Telegram (`hermes send`).
- GitHub Actions opcional para CI del puente.
