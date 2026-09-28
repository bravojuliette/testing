# BLOQUEO: BetsAPI devuelve 403 PERMISSION_DENIED (desde el 28-sep-2026)

Toda la recoleccion de datos esta parada. No es un fallo del codigo ni un
limite de ritmo: es la **cobertura de la cuenta de BetsAPI**.

## Lo medido (28-sep-2026)

Cuatro sondas independientes, todas con `--no-cache` para forzar red, todas
con el secret `BETSAPI_TOKEN_BBALL` de Actions:

| endpoint | parametros | resultado |
|---|---|---|
| `/v3/events/ended` | `sport_id=18, league_id=244, day=20260922` | **403 PERMISSION_DENIED** |
| `/v3/events/inplay` | `sport_id=18` (basket) | **403 PERMISSION_DENIED** |
| `/v2/event/odds/summary` | `event_id=12011377` | **403 PERMISSION_DENIED** |
| `/v3/events/inplay` | `sport_id=92` (tenis de mesa) | **403 PERMISSION_DENIED** |

Cuerpo identico en los cuatro casos:

```json
{"success":0,"error":"PERMISSION_DENIED",
 "error_detail":"Check Coverage on https://betsapi.com/mm/pricing_table"}
```

Runs: 36401275542 (intentos 1 y 2, el mismo 403 dos veces seguidas: no es
pasajero), 36401985609, 36402107868, 36402117991.

## Lectura

- **No es un endpoint concreto.** Fallan `ended`, `inplay` y `odds/summary`.
- **No es el basket.** La sonda de tenis de mesa (`sport_id=92`, el deporte
  del otro sistema, `tt_elite`) devuelve el mismo 403 con el mismo token.
- **No es rate-limit.** Un 429 se reintenta y tiene cabecera de reset; esto es
  un 403 con `PERMISSION_DENIED` inmediato.

Lo consistente con las cuatro sondas es que la suscripcion/cobertura de la
cuenta ha caducado o bajado de plan. El arreglo esta en la cuenta de BetsAPI
(`betsapi.com/mm/pricing_table`), no en este repo.

## Que se para y que no

**Se para:**
- Recoleccion de partidos y cuotas nuevas (`collect`, `collect-chicas`).
- El scanner en vivo (`scan-q1`, `scan`), que necesita `/v3/events/inplay`.
- La confirmacion del hueco de bwin prevista para el 1-oct
  (`PREREGISTRO_hueco_bwin.md`): sin datos nuevos en vivo no se puede correr.
  El criterio queda congelado tal cual esta escrito; no se toca.
- La cosecha emparejada `bet365`+`betfair` que era la via 2 del consolidado.
- Tambien el sistema de tenis de mesa, que comparte token.

**No se para:**
- Turso se lee sin problemas. Todo el analisis sobre lo ya recolectado sigue
  funcionando: 19.783 respuestas en cache, los partidos y cuotas de hasta el
  21-sep-2026 incluido.
- Los veredictos ya dictados no cambian: se dictaron con estos datos.

## Ultimo dia con datos

WNBA: 2026-09-21 (el 22-sep es el primer dia que la API ya no deja pedir).
