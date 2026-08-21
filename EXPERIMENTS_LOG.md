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
| h2h_weight (0.05-0.35) x h2h_max_matches (10/20/30) | Mejor ROI test por split: +15.1% (n=109), +0.5% (n=125), +2.3% (n=51) | Ni se acerca a 30% en ningún split; h2h_weight apenas mueve el resultado en este rango |
| common_opp_k (10-50) x common_opp_cap (20/40/60) | Mejor ROI test por split: +15.5% (n=111), ~+0.5% (n≈125), +1.1% (n=48) | Ni se acerca a 30%; common_opp_k apenas mueve el resultado |
| elo_scale (200-600) x rolling_elo_k (12-40), 25 combos | Mejor ROI test por split (combo distinta cada vez, ninguna gana en los 3): Split1 +22.9% (n=67, elo_scale=500,k=12), Split2 +4.1% (n=137, elo_scale=500,k=40), Split3 +23.1% (n=57, elo_scale=300,k=32) | Ni se acerca a 30%; Split2 se queda casi plano (+4.1%) pase lo que pase con elo_scale/rolling_elo_k -- no es la palanca. Ninguna combo unica gana en los 3 splits a la vez. |
| streak_bonus_pp (0-4.0), señal de racha calibrada (código nuevo, ver replay.py) | Con streak_bonus_pp=0 (sin efecto): +12.1% (n=110), +0.6% (n=128), +2.3% (n=51) -- igual al baseline. Cualquier valor >0: Split1 mejora apenas (+12.3% en 0.5), Split2 EMPEORA monótonamente con cualquier bonus positivo (+0.6%→-13.7% de 0 a 4.0), Split3 mejora algo (+2.3%→+4.3% de 0 a 4.0) | La racha NO es señal aprovechable con este modelo: en Split2 activa ruido puro (empeora con cualquier magnitud), no hay valor único que mejore los 3 splits a la vez. Descartado sin necesidad de ajuste fino (la condición de "mejora consistente" del protocolo no se cumple -- Split2 nunca mejora). Código queda en el repo como parámetro opt-in (default 0.0, no-op) por si sirve combinado con otra señal más adelante. |

## En curso -- señal prometedora (no descartada aún)

`min_matches_played`: barrido [2,3,4,5,6] con from_active=true, min_test_samples=15.
A diferencia de TODAS las teorías anteriores, esta mejora el ROI de test de forma
**monótona y consistente en los 3 splits a la vez** al subir el umbral de partidos
previos exigidos:

| min_matches_played | Split1 (07-25/07-31) | Split2 (08-10/08-16) | Split3 (08-17/08-19) |
|---|---|---|---|
| 2 | +7.7% (n=163) | -6.5% (n=184) | +9.1% (n=78) |
| 3 (activo) | +12.1% (n=110) | +0.6% (n=128) | +2.3% (n=51) |
| 4 | **+19.8% (n=58)** | **+12.7% (n=60)** | **+31.5% (n=24)** |

Con min_matches_played=4, picks/día ronda 8-8.6 en los 3 splits (bien por
encima del mínimo de 4-5/día), y Split3 YA CRUZA el 30%. Split1 (+19.8%) y
Split2 (+12.7%) todavía no llegan -- así que TODAVÍA NO califica como
candidato validado (exige los 3 simultáneamente), pero es la primera vez que
algo mejora consistentemente en los 3 splits a la vez sin excepciones, así
que aplica la excepción de "una vuelta de ajuste fino" antes de descartar.
min_matches_played=5 y 6 quedaron filtrados por min_test_samples=15 (n
insuficiente ahí) -- lanzado un sweep exploratorio adicional (min_test_samples=5,
grid [4,5,6,7,8]) para ver si la tendencia sigue subiendo o se revierte, y
para tener el n real en cada punto antes de decidir.

## Cola de teorías nuevas (si min_matches_played no termina de pasar el listón)

- [ ] min_market_gap (siempre 0.005) -- nunca barrido.
- [ ] min_market_gap (siempre 0.005) -- nunca barrido.
- [ ] Filtro por franja horaria / posición dentro de la sesión (partidos tempranos vs tardíos).
- [ ] Cuando haya más días de datos: repetir todo lo anterior contra splits nuevos, no solo los 3 de siempre.

## Cómo evaluar cada teoría

1. Sweep walk-forward en los splits vigentes, `min_test_samples` >= 15-20 por split.
2. Leer el leaderboard COMPLETO (no solo top-15 si el grid es grande -- usar grids pequeños y enfocados, no de 100+ combos, para poder ver todo).
3. Para cada combo candidata: ¿ROI >= 30% Y n >= 15-20 en LOS TRES splits? Si algún split falla ese doble criterio, descartar y anotar en "Probado y descartado".
4. Si algo pasa: verificar volumen (picks/día), y SOLO ENTONCES avisar al usuario con la evidencia completa.
5. Actualizar esta bitácora siempre, pase o no pase.
