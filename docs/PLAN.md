# opencode-telegram-approvals

## Plan de construcción (por fases)

### Fase 0 — Investigar mecanismo de permisos de opencode
- Leer cómo opencode expone los eventos de permiso (hooks, `opencode --auto`,
  config de `permission`).
- Determinar si hay un callback/API para inyectar la respuesta (allow/deny)
  programáticamente, o si hace falta un driver TTY.
- Salida: documento de viabilidad + el punto de integración exacto.

### Fase 1 — Prueba de concepto (unidireccional)
- Cuando opencode pide permiso, el bridger notifica a Telegram vía
  `hermes send -t telegram:1083549311 "<qué se pide>"`.
- No resuelve la decisión todavía. Valida que la notificación sea confiable.
- Meta: ver el prompt de permiso reflejado en Telegram.

### Fase 2 — Retorno bidireccional (MVP)
- El usuario responde desde Telegram con `/approve <id>` o `/deny <id>`.
- El bridger traduce la respuesta y la inyecta en opencode para resolver el
  prompt pendiente.
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
