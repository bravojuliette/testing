# Bitácora de búsqueda de sistema ganador

Registro vivo de teorías probadas para encontrar una configuración con
**ROI de test >= 30% de forma consistente en TODOS los splits de
validación (no solo en promedio), con >= 4-5 picks/día y un n mínimo por
split que no sea puro ruido (>= 15-20 picks por split; si es menor, el
resultado no cuenta como evidencia, por bueno que se vea).**

Este listón lo puso el usuario explícitamente el 2026-08-21 después de ver
que perseguir "el ROI más alto posible" sin este criterio produce números
como +88.5% con n=4 (ruido puro, ver sección "Descartado" más abajo). El
proceso de búsqueda es continuo y autónomo, pero **nunca se reporta ni se
promueve nada que no pase la barra completa** -- eso es lo único que
separa esto de p-hacking con pasos extra.

## Splits de validación (walk-forward, warmup=train_start=2026-06-20)

- Split 1: test 2026-07-25 → 2026-07-31 (7 días)
- Split 2: test 2026-08-10 → 2026-08-16 (7 días)
- Split 3: test 2026-08-17 → 2026-08-19 (3 días)

Según el collect diario (`collect.yml`, cron 05:00 UTC) vaya llenando más
días, hay que **añadir splits nuevos** (periodos que ningún sweep haya
tocado todavía) en vez de seguir exprimiendo solo estos 3 -- son la única
validación real que queda una vez que estos 3 ya se han usado para elegir
`session_k=0`.

## Baseline activo en producción

`baseline_v7_sessk0`: session_k=0, session_delta_cap=50, resto = baseline_v7.
Pooled ROI test +5.28% (289 picks / 17 días ≈ 17/día). Consistente
(positivo en los 3 splits) pero muy por debajo del listón de 30%.

## Probado y descartado

| Teoría | Resultado | Por qué falla |
|---|---|---|
| min_model/min_edge/min_ev (720 combos) | Sin patrón, ganador distinto cada split | Ruido |
| session_k bajo (0-42) | session_k=0 gana los 3 splits, pero solo +5.28% pooled | Consistente pero no llega a 30% |
| max_odds_underdog + min_blowout_rate | +16-17% en 2 splits, -9.9% en el 3º | No consistente; n=3-8 en variantes más agresivas = ruido puro |

## Cola de teorías nuevas (siguiente en negrita)

- [ ] **h2h_weight / h2h_max_matches** -- nunca se ha barrido en esta sesión (siempre 0.15/20 por defecto). Ahora que session_k=0 quitó el ruido de momentum, el peso relativo de h2h podría necesitar recalibrarse.
- [ ] common_opp_k / common_opp_cap -- idem, nunca tocado.
- [ ] elo_scale / rolling_elo_k -- calibración base del Elo, nunca tocado.
- [ ] Señal de racha calibrada (nueva, no la vieja session_delta): un ajuste pequeño y explícito basado en la desviación real medida contra Elo puro (streaks.py sin --full-model: +0.1/+1.1/+2.7/+4.6pp en rachas de victoria 1-4), en vez del session_delta viejo que sobreajustaba.
- [ ] min_matches_played (siempre 3) -- nunca barrido.
- [ ] min_market_gap (siempre 0.005) -- nunca barrido.
- [ ] Filtro por franja horaria / posición dentro de la sesión (partidos tempranos vs tardíos).
- [ ] Cuando haya más días de datos: repetir todo lo anterior contra splits nuevos, no solo los 3 de siempre.

## Cómo evaluar cada teoría

1. Sweep walk-forward en los splits vigentes, `min_test_samples` >= 15-20 por split.
2. Leer el leaderboard COMPLETO (no solo top-15 si el grid es grande -- usar grids pequeños y enfocados, no de 100+ combos, para poder ver todo).
3. Para cada combo candidata: ¿ROI >= 30% Y n >= 15-20 en LOS TRES splits? Si algún split falla ese doble criterio, descartar y anotar en "Probado y descartado".
4. Si algo pasa: verificar volumen (picks/día), y SOLO ENTONCES avisar al usuario con la evidencia completa.
5. Actualizar esta bitácora siempre, pase o no pase.
