# Bitácora de búsqueda de sistema ganador

## 🚨 BUG CRÍTICO encontrado y arreglado (2026-08-22): orden de sesiones ignoraba la fecha

Mientras se exploraba un factor nuevo, se encontró que `replay.py` ordenaba
las sesiones globalmente SOLO por `rel_min` (minutos desde medianoche de
ESA sesión concreta -- se reinicia a ~0 en cada sesión nueva, ver
`tt_series.assign_datetimes`), sin ningún componente de fecha. Con un
warmup de semanas/meses (el caso normal de TODOS los backtests corridos
en esta sesión), esto mezclaba sesiones de fechas distintas por
hora-del-día en vez de por fecha real.

Confirmado con un probe directo: una sesión del 2024-01-20 (rel_min=50) se
procesaba ANTES que una del 2024-01-01 (rel_min=800) -- 19 días fuera de
orden. Esto corrompía la evolución de Elo/H2H/career_played de
prácticamente todos los backtests corridos hasta ahora: pérdida de
información real (partidos ya jugados cuyo Elo aún no se había aplicado)
y, en el caso general, auténtico look-ahead (un partido posterior en el
tiempo actualizando Elo antes de generarse un pick de un partido
anterior).

**Fix** (commit `0dc68f8`): ordenar primero por fecha, luego por
`rel_min` dentro de esa fecha. Test de regresión que reproduce el
escenario exacto (falla contra el código viejo, pasa con el fix). Suite
completa 38/38 en verde.

**Implicación importante**: esto invalida potencialmente TODAS las
conclusiones de este documento hasta este punto (`baseline_v7_sessk0`
+5.28% pooled, `min_matches_played=4`, `min_market_gap`, `min_avg_games_won`,
etc.) -- todas fueron medidas con el motor roto. Hace falta re-correr los
6 splits contra `baseline_v7_sessk0` puro con el motor corregido antes de
confiar en ningún número anterior a este commit.

### Re-validación de `baseline_v7_sessk0` con el motor corregido (2026-08-22)

Resultado de re-correr los 6 splits (mismas fechas de siempre) contra la
estrategia activa, ya con el fix de orden aplicado:

| Split | Ventana test | n | Hit | ROI test |
|---|---|---|---|---|
| 1 | 2026-07-25→07-31 | 126 | 46% | +7.9% |
| 2 | 2026-08-10→08-16 | 106 | 43% | **-2.9%** |
| 3 | 2026-08-17→08-19 | 46 | 50% | +11.1% |
| 4 (hist.) | 2024-09-24→09-30 | 22 | 50% | +14.5% |
| 5 (hist., malo) | 2024-09-01→09-07 | 38 | 42% | -9.8% |
| 6 (hist.) | 2024-10-20→10-26 | 34 | 47% | +8.5% |

Pooled ponderado por n: ~+3.9% (vs +5.28% pre-fix -- orden de magnitud
parecido, pero la composición por split es MUY distinta):

- **El volumen sube muchísimo** en los splits recientes: Split1 pasa de
  n≈44 a n=126, Split2 de n≈45 a n=106. El motor corregido encuentra
  bastantes más candidatos que cruzan el umbral de edge -- consistente
  con que antes el Elo scrambleado producía separaciones más débiles/
  ruidosas entre jugadores.
- **Split2 se da la vuelta**: de positivo a **-2.9%** con n=106 (antes
  n≈45-58 y resultado positivo). Con el motor roto este split parecía
  favorable; con el motor corregido, no.
- **Split5 (periodo malo) empeora y crece en volumen**: n=38 (antes
  n≈13) y ROI -9.8% (antes -0.8%) -- sigue siendo el peor periodo, y
  ahora con bastante más evidencia detrás.
- Split1, 3, 4 y 6 se mantienen positivos, pero ninguno cerca del
  listón de 20%.

**Conclusión**: `baseline_v7_sessk0` sigue sin pasar el listón (como ya
se sabía), y el panorama por split ahora es fiable por primera vez en
toda la sesión. Cualquier palanca explorada antes de este commit
(`min_matches_played`, `min_market_gap`, `min_avg_games_won`, etc.) hay
que darla por no confirmada y, si se quiere seguir esa línea, volver a
barrerla desde cero contra este baseline corregido -- los números
viejos ya no sirven de referencia.

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

## Backfill histórico en curso (2026-08-21)

Con la cola de 9 teorías agotada (ver abajo), el usuario pidió acelerar la
acumulación de datos en vez de esperar al cron diario: lanzado un collect
histórico manual, run `#7` (id `32513800795`) de `collect.yml`, rango
`2024-08-21 → 2026-06-19` (2 años hacia atrás, hasta justo el día antes de
donde ya había cobertura). Es resumible (`collect_range` guarda el
siguiente día pendiente en la tabla `meta` bajo la clave exacta del rango
start/end) -- si el job corta por el timeout de GitHub Actions (~5.8h), se
puede relanzar con el MISMO start/end y retoma donde se quedó, sin perder
progreso ni repetir trabajo.

El cuello de botella real es el rate-limit de BetsAPI (~1 req/s, solo para
cuotas -- las peticiones a TT-Series/WordPress para descubrir sesiones no
tienen ese límite), así que días sin sesiones se saltan rápido y solo los
días con partidos completados cuestan tiempo real. El primer collect de 61
días (20 jun → 19 ago) tardó ~5.5h, así que 2 años completos con muchos
días de liga activa podría necesitar varias corridas encadenadas.

**Confirmado (2026-08-22, vía `status.yml` consultando Turso directamente,
no logs):** el bloque 2024-08-21 → 2024-10-01 (42 días) ya está completo y
guardado (190-220 partidos/día, sin huecos) -- la liga sí tiene actividad
densa desde hace casi 2 años. El job de backfill sigue corriendo/
relanzándose automáticamente en segundo plano hacia 2026-06-19. Pedido
explícito del usuario (2026-08-22): dejarlo correr hasta cubrir los 2 años
completos, Y EN PARALELO seguir experimentando con los datos que ya van
entrando -- no esperar a que termine todo el backfill para retomar la
búsqueda. Ver Split 4 más abajo, construido ya sobre el primer bloque
histórico confirmado.

Cuando el backfill termine del todo (o se agote el rango sin encontrar más
historial), toca **repetir el barrido completo de teorías descartadas
contra TODOS los splits nuevos** que el historial adicional habilite, ya
que muchas fallaron por n insuficiente, no por falta de señal.

## Splits de validación (walk-forward)

- Split 1: warmup=train_start 2026-06-20, test 2026-07-25 → 2026-07-31 (7 días)
- Split 2: warmup=train_start 2026-06-20, test 2026-08-10 → 2026-08-16 (7 días)
- Split 3: warmup=train_start 2026-06-20, test 2026-08-17 → 2026-08-19 (3 días)
- **Split 4 (histórico, nuevo 2026-08-22)**: warmup=train_start 2024-08-21, test
  2024-09-24 → 2024-09-30 (7 días) -- construido sobre el bloque de backfill
  histórico ya confirmado y completo (2024-08-21 → 2024-10-01, 42 días,
  190-220 partidos/día). Es un periodo TOTALMENTE independiente de los otros
  3 (casi 2 años antes), así que sirve de replicación real: si una teoría
  descartada por poco (ej. min_matches_played=4) se comporta igual aquí,
  es señal mucho más fuerte que cualquier cosa vista hasta ahora.

Según el backfill histórico vaya avanzando (ver sección de arriba) y el
collect diario vaya llenando más días recientes, hay que **seguir añadiendo
splits nuevos** (periodos que ningún sweep haya tocado todavía) en vez de
seguir exprimiendo solo los mismos -- son la única validación real que queda
una vez que se usan para elegir una configuración.

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
| min_matches_played (2-8) | Mejor punto real: min=4 con +19.8% (n=58), +12.7% (n=60), +31.5% (n=24) -- mejora CONSISTENTE en los 3 splits vs el activo (min=3), pero solo Split3 cruza 30%. min=5+ colapsa a n<5 en los 3 splits (ruido, no hay suficientes datos con ~2 meses de historial) | Techo alcanzado por falta de datos, no por falta de señal: no se puede subir más el umbral sin perder el n. Mejor candidato "casi" encontrado hasta ahora -- reconsiderar cuando haya más días de datos acumulados. |
| min_market_gap (0.0-0.03) | Mejor ROI test por split (valor distinto cada vez, ninguno gana en los 3): Split1 +12.8% (n=106, gap=0.01), Split2 +0.6% (n=128, gap=0.005=activo), Split3 +4.7% (n=48, gap=0.03) | Ni se acerca a 30% en ningún split; min_market_gap apenas mueve el resultado. Última teoría de la cola de parámetros simples -- con esta se agota la cola inicial de 9 familias. |

## Mejor candidato aún sin validar (no pasa el listón completo, pero es el mejor hallazgo)

`min_matches_played=4` sobre baseline_v7_sessk0: la única teoría que mejora el ROI
de test de forma consistente en los 3 splits a la vez frente al baseline activo
(min_matches_played=3):

| min_matches_played | Split1 (07-25/07-31) | Split2 (08-10/08-16) | Split3 (08-17/08-19) |
|---|---|---|---|
| 2 | +7.7% (n=163) | -6.5% (n=184) | +9.1% (n=78) |
| 3 (activo) | +12.1% (n=110) | +0.6% (n=128) | +2.3% (n=51) |
| **4** | **+19.8% (n=58)** | **+12.7% (n=60)** | **+31.5% (n=24)** |
| 5 | +67.2% (n=5, ruido) | sin datos (n<5) | sin datos (n<5) |
| 6-8 | sin datos (n<5) | sin datos (n<5) | sin datos (n<5) |

Sweep fino (min_test_samples bajado a 5 para ver el n real) confirma que el
umbral de 4 es un TECHO, no un punto intermedio: subir a 5 hace que el n útil
se desplome a 5 o menos en los 3 splits (con los ~2 meses de datos actuales,
exigir 5 partidos previos deja casi sin candidatos elegibles en ventanas de
7 y sobre todo 3 días) -- el +67.2% en Split1/min=5 es ruido puro de n=5, no
señal. No hay manera de subir mas el umbral sin que el n colapse antes de
que el ROI llegue a 30% en los 3 splits.

**Conclusión: min_matches_played=4 NO pasa el listón completo** (Split1 +19.8%
y Split2 +12.7% se quedan cortos aunque Split3 ya cruce 30%), y no hay margen
para seguir subiendo el umbral con el volumen de datos actual. Descartado como
candidato definitivo, pero es el MEJOR resultado consistente encontrado hasta
ahora (mejor que baseline_v7_sessk0 en los 3 splits simultáneamente) -- vale la
pena reconsiderar min_matches_played=4 cuando haya más días de datos y el n a
umbrales altos dejen de ser ruido.

### Replicación en Split 4 (histórico, 2026-08-22)

Primer resultado sobre datos genuinamente nuevos (backfill 2024-08-21→2024-09-30,
periodo ~2 años antes de los otros 3 splits):

| min_matches_played | Split4 test (2024-09-24/09-30) |
|---|---|
| 2 | +21.5% (n=33) |
| 3 (activo) | **+34.6% (n=25)** |
| 4 | +30.5% (n=16, al límite del mínimo de 15-20) |
| 5-6 | sin datos suficientes (n<15) |

Notable: en Split4 el propio BASELINE (min=3) ya cruza 30%, y de hecho supera a
min=4 -- justo lo contrario del patrón visto en Split1/2/3 (donde min=4 SIEMPRE
ganaba a min=3). Esto no valida min_matches_played=4 como palanca universal --
más bien sugiere que este periodo histórico concreto tiene un ROI de mercado
más alto en general, independientemente del umbral. Con n=16-25 tampoco es
una muestra grande. min_matches_played=4 sigue sin pasar los 4 splits a la
vez con ROI>=30% simultáneo (falla Split1 +19.8% y Split2 +12.7%).
Actualiza el cuadro completo (4 splits) de min_matches_played=4:
Split1 +19.8% (n=58), Split2 +12.7% (n=60), Split3 +31.5% (n=24), Split4 +30.5% (n=16)
-- 2 de 4 ya cruzan 30%, pero Split1/2 siguen muy lejos.

### h2h_weight y common_opp_k replicados en Split4 (2026-08-22)

- **common_opp**: mejor combo es `common_opp_k=25, common_opp_cap=40` (+34.6%,
  n=25) -- que es literalmente el valor por defecto ya activo. Ninguna
  variante mejora sobre el baseline aquí; confirma que Split4 en sí es un
  periodo con ROI alto, no que common_opp sea la palanca.
- **h2h**: mejor combo `h2h_weight=0.15 (default), h2h_max_matches=10`
  (+37.5%, n=26) -- pequeña mejora sobre el default (h2h_max_matches=20,
  que da +34.6%/n=25 aquí), pero en Split1 esta misma familia de parámetros
  ya se había descartado (mejor real +15.1%, n=109 -- lejísimos de 30%), así
  que no hay motivo para pensar que replica en los otros splits.

**Conclusión de esta ronda**: Split4 confirma ser un periodo de ROI de
mercado alto en sí mismo (el baseline puro ya supera 30% ahí), y ningún
ajuste de parámetros lo mejora de forma decisiva ni de forma que generalice
a los otros 3 splits. Sigue sin haber un candidato que pase los 4 splits
a la vez.

### En curso: combinación min_matches_played=4 + h2h_max_matches + elo_scale (2026-08-22)

Pedido del usuario: en vez de seguir probando parámetros uno a uno (todos
agotados individualmente), probar una COMBINACIÓN de dos señales que cada
una por separado no llegó al listón pero mostró algo de vida:
`min_matches_played=4` (fijo, es el mejor candidato) × `h2h_max_matches`
[10,15,20,30] × `elo_scale` [400,500]. Lanzado contra los 4 splits vigentes
(1, 2, 3 y el histórico 4) simultáneamente. Pendiente de revisar resultados.

**Ojo con el riesgo de este camino**: combinar señales multiplica el número
de combinaciones probadas, lo que aumenta el riesgo de encontrar algo que
parezca bueno por puro azar (look-elsewhere effect). El mismo criterio de
siempre aplica sin excepción: solo cuenta si pasa ROI>=30% Y n>=15-20 en
TODOS los splits a la vez, no en promedio ni en la mayoría.

### Resultado del combo (2026-08-22)

| Split | Mejor combo | ROI test |
|---|---|---|
| 1 | h2h_max_matches=15, elo_scale=500 | +21.0% (n=54) |
| 2 | h2h_max_matches=10, elo_scale=400 | +12.7% (n=60) -- igual que min=4 solo |
| 3 | h2h_max_matches=10, **elo_scale=500** | **+46.3% (n=23)** |
| 4 | sin cambio con h2h_max | +30.5% (n=16) -- igual que min=4 solo |

`elo_scale=500` dispara Split3 a +46.3%, pero es sobreajuste clásico: ese
mismo valor HUNDE Split2 (+0.3%, contra +12.7% con elo_scale=400) y reduce
tanto el n de Split4 que las combinaciones con elo_scale=500 ahí quedan
filtradas por debajo del mínimo de 15. No hay una combinación única que
mejore los 4 splits a la vez -- `h2h_max_matches` en concreto no aporta
nada por encima de `min_matches_played=4` solo (los resultados con
elo_scale=400 son idénticos a los ya conocidos).

### Split 5 (histórico, 2024-09-01 → 2024-09-07) -- PRIMER PERIODO CLARAMENTE NEGATIVO

Resultado crítico: en este split, la estrategia BASE (sin ningún ajuste)
da ROI test **negativo**: min_matches_played=2 → -22.9% (n=54),
min_matches_played=3 (activo) → -27.3% (n=40). min_matches_played=4 no
generó ni n=15 candidatos aquí (filtrado).

Es el primer periodo de validación con ROI claramente negativo que
aparece en toda la búsqueda. Confirma algo importante: no es que falte
encontrar el parámetro correcto -- hay semanas reales en las que esta
estrategia pierde dinero, sin más. Ningún ajuste de parámetros debería
"arreglar" eso de forma honesta; si algo pareciera hacerlo, sería
sobreajuste a los periodos buenos, no una mejora real. Esto refuerza por
qué ningún candidato ha pasado nunca el listón completo: la varianza
real entre periodos es alta, y cualquier optimización sobre unos pocos
splits corre el riesgo de estar memorizando ruido de esos splits
concretos en vez de encontrar señal genuina.

## Ronda "20% + mejorar hit rate" (2026-08-22)

Petición explícita del usuario: relajar el listón de ROI de 30% a **20%**
(pero exigido en TODOS los splits vigentes, no en promedio) y buscar
factores nuevos que además **mejoren el hit rate**, no solo el ROI.
Se lanzaron dos grids nuevos contra los 5 splits vigentes (1, 2, 3, 4
histórico, 5 histórico -- este último con `min_test_samples=8` en vez de
15-20, solo para poder ver algo dado su bajo volumen).

**Grid A**: `min_matches_played` [3,4] × `min_model` [0.52, 0.55, 0.60, 0.65]

| Split | Mejor combo | Test n/hit/ROI |
|---|---|---|
| 1 | min=4, min_model=0.52 | 58 / 52% / **+19.8%** |
| 2 | min=4, min_model=0.52 | 60 / 48% / **+12.7%** |
| 3 | min=4, min_model=0.52 | 24 / 58% / **+31.5%** |
| 4 (hist.) | min=3, min_model=0.52 (línea base, sin filtrar) | 25 / 60% / **+34.6%** |
| 5 (hist.) | min=4, min_model=0.52 | 13 / 46% / **-0.8%** |

Todos los valores de `min_matches_played=4` en cada split dieron
resultados **idénticos byte a byte** al ya conocido (no es un hallazgo
nuevo, es la reconfirmación de siempre). El dato realmente nuevo es que
**subir `min_model` de 0.52 a 0.55/0.60/0.65 no cambia NADA** -- en los 5
splits, esas tres filas son exactamente iguales a la de 0.52. Esto quiere
decir que, con los demás filtros activos, ningún pick que hoy se acepta
tiene `model` entre 0.52 y 0.65: el filtro real que decide qué entra ya
es otro (`min_edge`, `min_ev` o el propio mercado), y `min_model` en ese
rango no está mordiendo. No es una palanca útil tal como está planteada.

**Grid B**: `min_matches_played=4` (fijo) × `min_odds_underdog` [1.0, 1.3,
1.5, 1.8] × `fb_min_model` [0.55, 0.99] (0.99 desactiva de facto las
señales de casas de respaldo, `SI_FALLBACK`)

Resultado: en los 5 splits, **las 8 combinaciones de esta grid dieron
resultados idénticos** entre sí y a su vez idénticos al `min_matches_played=4`
plano de la Grid A (mismos n/hit/ROI, split a split). Conclusión doble:
(a) no hay ningún pick aceptado con cuota de underdog por debajo de 1.3,
así que subir `min_odds_underdog` hasta 1.8 no filtra nada; y (b)
desactivar por completo las señales `SI_FALLBACK` (fb_min_model=0.99) no
cambia ni un solo pick, es decir, en estos 5 splits el pool actual no
está usando casas de respaldo en absoluto. Dos palancas nuevas probadas,
las dos inertes.

**Conclusión de la ronda**: ninguna de las 12 combinaciones nuevas
probadas (Grid A + Grid B) le gana al `min_matches_played=4` ya conocido
en ningún split, y ese candidato **sigue sin pasar ni el listón relajado
de 20% en los 5 splits a la vez** -- Split 5 (el periodo históricamente
malo) se queda en -0.8%, la mejor cifra encontrada ahí hasta ahora pero
aún negativa. Tampoco hay mejora de hit rate: los hit rates de
min_matches_played=4 (52%, 48%, 58%, 62%, 46%) son los mismos de siempre,
ninguna palanca nueva los movió. Se descartan ambas grids como "probado,
sin efecto" y se anotan en la cola de teorías pendientes las que aún no
se han tocado.

**Grid C**: `min_matches_played=4` (fijo) × `min_edge` [0.04, 0.08, 0.12, 0.15]
× `min_ev` [0.02, 0.05, 0.08]

Mismo patrón otra vez: las 12 combinaciones dieron resultados idénticos
entre sí en los 5 splits, y esos resultados son los mismos que el
`min_matches_played=4` plano. Subir `min_edge` hasta 0.15 (2.5x el
default) y `min_ev` hasta 0.08 no filtra ni un solo pick adicional.

**Esto ya es un patrón, no un accidente**: tres grids seguidos (A, B, C
-- 20 combinaciones nuevas en total) dieron resultados idénticos al
candidato ya conocido, en los 5 splits, sin excepción. Con
`min_matches_played=4` activo, el pool de candidatos que sobrevive es
tan pequeño que ninguno de los filtros de "calidad de señal" (min_model,
min_edge, min_ev, min_odds_underdog, casas de respaldo) llega a
morder -- los pocos picks que pasan `min_matches_played=4` ya tienen
edge/ev/modelo muy por encima de cualquiera de estos umbrales. La
palanca real que decide qué entra es `min_matches_played` en sí (cuántos
partidos ha jugado cada jugador DENTRO de la sesión actual), no ningún
umbral de calidad de la señal.

## Probado y descartado (ronda 20%+hit rate)

| Teoría | Resultado |
|---|---|
| `min_model` 0.55/0.60/0.65 (vs 0.52) | Sin efecto: resultados idénticos en los 5 splits. El filtro no muerde en ese rango. |
| `min_odds_underdog` 1.3/1.5/1.8 (vs 1.0) | Sin efecto: ningún pick aceptado tiene cuota underdog < 1.3. |
| `fb_min_model=0.99` (desactivar señales de casas de respaldo) | Sin efecto: el pool actual no genera señales `SI_FALLBACK` en estos 5 splits. |
| `min_edge` 0.08/0.12/0.15 (vs 0.04) × `min_ev` 0.05/0.08 (vs 0.02) | Sin efecto: resultados idénticos en los 5 splits. Ningún pick queda filtrado por edge/ev en ese rango. |

## Palanca nueva implementada: `min_career_matches`

Todas las palancas de "calidad de señal" resultaron inertes -- lo único
que de verdad mueve el resultado hasta ahora es `min_matches_played`
(partidos jugados DENTRO de la sesión actual). Se implementó una palanca
relacionada pero distinta, nunca antes disponible: `min_career_matches`
-- partidos TOTALES del jugador desde el inicio del warmup (no solo en
la sesión de hoy). Requirió código nuevo en `replay.py`: un contador
`career_played` que persiste entre sesiones (igual que el Elo), con
snapshot al INICIO de cada sesión para no filtrar con información del
futuro. Suite de tests local (37/37) sigue en verde, `min_career_matches=0`
por defecto es no-op (no cambia ningún resultado existente).

Hipótesis: un jugador con pocos partidos jugados en TODA la temporada
(no solo hoy) puede ser más impredecible que uno con historial largo,
aunque hoy lleve varios partidos en la sesión. Es una señal
independiente de `min_matches_played`.

### Resultado de `min_career_matches` (2026-08-22)

Primer barrido: `min_career_matches` [0,10,20,30,50] contra los 5 splits
(min_matches_played=4 fijo). A diferencia de TODAS las palancas
anteriores de esta ronda, esta SÍ cambió resultados -- ya no es inerte.
Segundo barrido más fino [0,15,20,25] para confirmar:

| Split | Mejor valor | ROI test (mejor) | ROI test (career=0, baseline) |
|---|---|---|---|
| 1 | **0 (sin filtro)** | +19.8% (n=58) | +19.8% (n=58) |
| 2 | 15 | **+19.2%** (n=49) | +12.7% (n=60) |
| 3 | 15 | **+39.8%** (n=21) | +31.5% (n=24) |
| 4 (hist.) | 0 (sin datos por encima) | +30.5% (n=16) | +30.5% (n=16) -- valores >0 filtran por debajo de n=15 |
| 5 (hist., malo) | 20 | **+8.8%** (n=8, al límite) | -0.8% (n=13) |

**Primer hallazgo real, pero NO universal**: en Split1, CUALQUIER valor
de `min_career_matches` > 0 empeora el resultado (cae a +9.6% o peor con
15/20/25) -- justo el split donde el filtro no ayuda en absoluto. En
Split2, Split3 y Split5, en cambio, valores entre 15 y 20 mejoran el ROI
de forma clara y consistente (sube en los tres). Split4 no tiene
suficiente volumen para evaluarlo.

Mismo patrón que ya vimos con `elo_scale=500`: ayuda a unos splits y
perjudica a otro de forma opuesta. No hay un valor único de
`min_career_matches` que pase el listón de 20% en los 5 splits a la vez
(Split1 se cae por debajo de 20% en cuanto se activa el filtro). Se
descarta como candidato definitivo por el mismo motivo que
`elo_scale`: mejora real en algunos periodos, pero no generaliza --
promoverlo sería sobreajustar a 3 de 5 splits e ignorar que el cuarto
(Split1) lo penaliza directamente. Queda documentado como palanca activa
en el código (default 0 = no-op) por si combinada con más datos futuros
sí generaliza.

## Palanca nueva: franja horaria dentro de la sesión (2026-08-22)

Segunda palanca nueva implementada con código (`min/max_session_elapsed_min`
en `replay.py`, minutos transcurridos desde el primer partido de la
sesión hasta el candidato, sin look-ahead). Se probaron las dos
direcciones por separado contra los 5 splits:

**Excluir partidos TARDÍOS** (`max_session_elapsed_min` en [60,120,180,300]
vs sin filtro):

| Split | Mejor valor | ROI test |
|---|---|---|
| 1 | 300 | **+38.0%** (n=27) vs +19.8% baseline -- mejora fuerte |
| 2 | sin filtro (0) | +12.7% (n=60) -- cualquier corte empeora (-1.7% con max=60) |
| 3, 4, 5 | sin datos por encima del baseline (n cae por debajo del mínimo) | sin señal |

**Excluir partidos TEMPRANOS** (`min_session_elapsed_min` en [0,60,120,180]):
sin efecto en NINGÚN split -- resultados idénticos al baseline en los 5.
Explicación: con `min_matches_played=4` ya activo, ambos jugadores
necesitan haber jugado 4 partidos antes de generar un candidato, así que
para cuando eso pasa la sesión ya lleva bastante tiempo corriendo --
excluir los primeros 60-180 minutos no quita ningún pick que
`min_matches_played=4` no quitara ya.

**Mismo patrón que `min_career_matches` y `elo_scale=500` antes**: la
única dirección con efecto real (cortar la sesión a los 300 minutos)
ayuda mucho a Split1 pero perjudica a Split2, y no hay datos suficientes
en los otros 3 splits para saber si generaliza. Se descarta como
candidato definitivo por el mismo motivo de siempre -- no hay un valor
que pase el listón en todos los splits a la vez. Queda como palanca
disponible en el código (default sin filtro, no-op).

### Balance de la búsqueda de "hit rate + 20%" hasta ahora

Cuatro palancas nuevas probadas esta ronda (min_model, min_odds_underdog
+ fallback, min_edge/min_ev, min_career_matches, franja horaria -- 5 en
total). Patrón consistente: la mayoría son completamente inertes con el
pool actual (min_model, min_odds_underdog, fallback, min_edge/min_ev,
franja horaria temprana), y las dos que sí tienen efecto real
(`min_career_matches`, franja horaria tardía) mejoran unos splits y
empeoran otros -- igual que ya pasaba con `elo_scale=500`. Con el volumen
de datos actual (2 meses recientes + 2 semanas históricas confirmadas),
no hay suficiente evidencia para diferenciar "esto generaliza" de "esto
es ruido de un split concreto". La honestidad aquí importa más que
encontrar algo que "parezca" funcionar: ninguna de las dos palancas se
promueve.

### Combo `min_career_matches` + franja horaria tardía (2026-08-22)

Se probó si las dos palancas con efecto real se refuerzan combinadas.
Resultado: NO. En Split1, combinar career_matches>0 con el corte a 300
minutos reduce el n y el ROI respecto al corte solo (+38.0%->+32.6% o
peor). En Split2/3/5, combinar ambos filtros hace que la mayoría de
combinaciones caigan por debajo del n mínimo (se filtran del todo) --
el mejor resultado en cada split sigue siendo el de la palanca individual
sola, nunca la combinación. Las dos palancas no son complementarias:
compiten por el mismo pool ya pequeño de candidatos, así que juntarlas
solo lo reduce más sin sumar señal. Se descarta la combinación.

## `min_market_gap` (2026-08-22)

Última teoría en cola: `min_market_gap` (siempre 0.005, nunca barrido).
Sweep [0.005, 0.01, 0.02, 0.03, 0.05] contra los 5 splits:

| Split | Mejor valor | ROI test | Hit rate |
|---|---|---|---|
| 1 | 0.03 | +19.8% -> **+25.0%** (n=51) | 52% -> **53%** |
| 2 | 0.005 (sin cambio) | +12.7% -- subirlo empeora monótonamente (hasta +10.1%) | 48% -> 47% con gap alto |
| 3 | 0.03 | +31.5% -> **+41.2%** (n=21) | 58% -> **62%** |
| 4 (hist.) | 0.005 (sin cambio) | +30.5% -- subirlo apenas cambia (+26.5% con gap alto, n cae a 15) | 62% -> 60% |
| 5 (hist., malo) | sin efecto | -0.8% en los 5 valores, picks idénticos | 46% sin cambio |

**Primera vez que el MISMO valor (0.03) mejora DOS splits a la vez**
(Split1 y Split3), y en ambos mejora tanto ROI como hit rate -- la señal
que el usuario pidió explícitamente. Pero Split2 lo penaliza con
claridad (cae a ~10-11%, muy por debajo del listón de 20%), y Split4/5
no se mueven. No es "consistencia muy fuerte en todos los splits" (el
protocolo exige eso para preguntar al usuario en vez de descartar solo),
así que se documenta como el hallazgo más prometedor de la sesión pero
NO se promueve: sigue sin pasar el listón de 20% en los 5 splits a la
vez. Queda marcado como el candidato más interesante para revisar en
cuanto el backfill traiga más splits históricos -- si `min_market_gap=0.03`
sigue ganando en nuevos periodos y Split2 resulta ser la excepción (no
la regla), ahí sí habría motivo para preguntar al usuario en vez de
descartar.

### Split 6 (histórico nuevo, 2024-10-20 → 2024-10-26) -- replicación de `min_market_gap=0.03`

El backfill ya confirma un bloque histórico mucho más largo de lo que
se pensaba: **2024-08-21 → 2024-11-03 (75 días completos)**, no solo
hasta 2024-10-05. Se aprovechó para construir un split nuevo,
independiente de Split4/Split5, y replicar ahí el hallazgo más
prometedor de la sesión (`min_market_gap=0.03`).

Resultado: **no se replica**. Con `min_matches_played=3` (activo),
`min_market_gap=0.03` da un resultado IDÉNTICO a 0.005 (test 29/45%/+2.7%)
-- ninguna mejora. Con `min_matches_played=4`, también idéntico entre
ambos valores de gap, pero el resultado en sí es NEGATIVO (test
16/44%/-4.7%), peor que `min_matches_played=3` en este periodo --
justo el patrón inverso al de Split1/2/3 (donde min=4 siempre gana).

Esto es una señal importante EN CONTRA de promover `min_market_gap=0.03`:
la mejora que se vio en Split1 y Split3 no generaliza a un tercer
periodo histórico independiente. Refuerza la lectura de que fue una
coincidencia entre esos dos splits concretos, no una señal real y
estable. Con esta replicación fallida, `min_market_gap` queda
definitivamente descartado como candidato, igual que las demás
palancas de esta ronda.

También confirma, otra vez, que `min_matches_played=4` NO es una
palanca universal -- en Split4 y ahora en Split6, el baseline
(`min_matches_played=3`) le gana. Sigue sin haber ninguna configuración
que sea consistentemente mejor que el baseline en TODOS los periodos
históricos vistos hasta ahora.

## Palanca nueva: `min_avg_games_won` -- juegos ganados por partido, de media (2026-08-22)

Pedido explícito del usuario: incorporar el promedio de juegos (sets)
ganados por partido de cada jugador como factor -- proxy de margen de
victoria/dominio, distinto de `min_matches_played` (que solo cuenta
partidos jugados, no cómo los ganó). Implementado en `replay.py`
reutilizando `st1["sf"]/st1["played"]` (ya calculado dentro de la sesión,
antes del candidato, sin look-ahead) -- exige el promedio en AMBOS
jugadores. Default 0.0 = sin filtro. Tests 37/37 en verde.

Barrido [0, 1.1-2.5] con `min_matches_played=4` contra los 6 splits:

| Split | Mejor valor | ROI test | Hit rate |
|---|---|---|---|
| 1 | 1.5 | +19.8% -> **+22.9%** (n=44) | 52% (sin cambio) |
| 2 | 1.5 | +12.7% -> **+17.2%** (n=45) | 48% -> 49% |
| 3 | 1.1 | +31.5% -> **+41.4%** (n=18) | 58% -> **61%** |
| 4 (hist.) | sin datos por encima del baseline | +30.5% (n=16) | -- |
| 5 (hist., malo) | 0 (cualquier valor >0 empeora) | -0.8% -> -13.5%/-26.1% según el umbral | empeora |
| 6 (hist.) | sin efecto en ningún valor | -4.7% sin cambio | sin cambio |

**Es la palanca más consistente encontrada en toda la sesión**: mejora
Split1, Split2 Y Split3 (los tres splits recientes) cada una con su
propio óptimo entre 1.1 y 1.5. Para confirmar que no es casualidad de
tres óptimos distintos, se probó un **valor único fijo (1.3)** contra
los tres a la vez:

- Split1: +19.8% -> **+22.9%** (n=44) -- mejora
- Split2: +12.7% -> **+17.2%** (n=45) -- mejora
- Split3: el n cae por debajo de 15 con 1.3 (se queda sin datos suficientes)

Con un valor único, Split1 y Split2 mejoran SIMULTÁNEAMENTE -- la
primera vez en toda la sesión que dos splits distintos mejoran a la vez
con un valor fijo de una palanca nueva. Pero: (a) Split3 pierde
volumen con ese mismo valor, (b) no hay datos suficientes en Split4 para
evaluar, (c) Split5 (el periodo históricamente malo) empeora con
cualquier valor positivo, y (d) Split6 no se mueve. **No pasa el listón
de 20% en los 6 splits a la vez** -- Split5 sigue siendo el obstáculo
real, igual que con todas las palancas anteriores.

Aun así, por la regla del protocolo ("consistencia muy fuerte
across-splits sin llegar al listón individual -> preguntar al usuario
en vez de decidir solo"), esta es la primera palanca de la sesión que
se acerca a esa categoría: mejora 3 splits independientes de forma
simultánea (o cercana), con hit rate igual o mejor en los 3. Se reporta
al usuario con el detalle completo en vez de descartarla en silencio.

### Combo `min_matches_played` x `min_avg_games_won` (2026-08-22)

Siguiente paso pedido por el usuario ("empieza ya"): en vez de fijar
`min_matches_played=4`, barrer la combinación completa
`min_matches_played=[3,4,5]` x `min_avg_games_won=[0,1.1,1.3,1.5]`
contra los 6 splits, para ver si otro valor de `min_matches_played`
rescata Split4/5/6 (donde `min_avg_games_won` no ayudaba con min=4).

Resultado ("Mejor por ROI de test" de cada split, grid completo):

| Split | Mejor combo | Test n/hit/ROI |
|---|---|---|
| 1 | min=4, avg=1.3 | 44/52%/**+22.9%** |
| 2 | min=4, avg=1.1 | 52/52%/**+21.6%** |
| 3 | min=4, avg=1.1 | 18/61%/**+41.4%** (n=18, al límite del piso) |
| 4 (hist.) | min=3, avg=0 | 25/60%/**+34.6%** (avg>0 no aporta nada aquí) |
| 5 (hist., malo) | min=4, avg=0 | 13/46%/**-0.8%** (mejor caso sigue siendo negativo; avg>0 lo empeora monótonamente hasta -29.5%) |
| 6 (hist.) | min=3, avg=0 | 29/45%/**+2.7%** (avg>0 no mejora, se queda plano o cae a -4.7%) |

Conclusión: variar `min_matches_played` **no rescata** la palanca en
los splits históricos. En Split4 el baseline ya es bueno por sí solo
(no necesita `min_avg_games_won`); en Split5 cualquier valor >0 de
`min_avg_games_won` empeora las cosas de forma monótona (confirma el
patrón ya visto); en Split6 la palanca sigue sin efecto real (mejor
caso +2.7%, muy por debajo del listón, con o sin ella). El patrón de
antes se mantiene igual de nítido: `min_avg_games_won` ~1.1-1.3
combinado con `min_matches_played=4` es fuerte y consistente en los
3 splits "recientes" (Split1/2/3), y completamente irrelevante o
contraproducente en los 3 históricos (Split4/5/6). No pasa el listón
de 20% en los 6 splits a la vez -- Split5 y Split6 siguen siendo el
obstáculo. Se cierra esta línea de búsqueda (seguir afinando el valor
exacto sobre datos históricos tan escasos empieza a arriesgar
sobreajuste al ruido, no a encontrar señal real) y queda documentada
como el mismo caso "consistencia fuerte en 3/6 splits, no en los otros
3" ya reportado, ahora confirmado que no depende de `min_matches_played`.

## Palanca nueva: hora del día reloj -- `min/max_hour_of_day` (2026-08-22, motor corregido)

Primer factor genuinamente distinto (no otro umbral sobre matches_played/
avg_games) probado contra el motor YA CORREGIDO. Hipótesis: partidos de
madrugada podrían tener líneas menos afinadas o jugadores más
fatigados. Barrido de los dos ejes por separado (excluir horas tardías
con `max_hour_of_day`, excluir horas tempranas con `min_hour_of_day`)
contra los 6 splits:

| Split | Baseline test | Mejor `max_hour_of_day` | Mejor `min_hour_of_day` |
|---|---|---|---|
| 1 | 126/46%/+7.9% | max=18 → 88/50%/**+13.5%** | min=14 → 70/44%/+9.2% |
| 2 | 106/43%/-2.9% | max=10 → 34/62%/**+34.5%** | min=18 → 30/43%/+3.4% |
| 3 | 46/50%/+11.1% | max=18 → 36/50%/+6.5% (resto peor) | min=10 → 28/61%/**+37.9%** |
| 4 (hist.) | 22/50%/+14.5% | sin datos suficientes con recorte | min=6/10 → 17/47%/+11.2% (peor) |
| 5 (hist., malo) | 38/42%/-9.8% | max=18 → 28/46%/-1.8% (sigue negativo) | TODOS peores (-13% a -32%) |
| 6 (hist.) | 34/47%/+8.5% | max=18 → 25/48%/+9.3% | min=14 → 19/47%/+8.6% |

**Contradicción clave**: Split2 mejora muchísimo cortando las horas
TARDÍAS (`max_hour_of_day=10`, +34.5%), mientras que Split3 mejora
muchísimo cortando las horas TEMPRANAS (`min_hour_of_day=10-14`,
+37.9%) -- exactamente la dirección OPUESTA sobre el mismo eje. Ningún
valor fijo de hora puede satisfacer a los dos a la vez. Esto es más
concluyente que un simple "sin efecto": dos splits recientes tirando en
direcciones contrarias es la firma clásica de sobreajuste a ruido de
cada periodo concreto, no señal real. Split4 no tiene volumen
suficiente para evaluar recortes de hora, y Split5 (el periodo malo)
sigue siendo negativo pase lo que pase (mejor caso -1.8%, sigue sin
acercarse al listón).

**Descartada.** No se sigue explorando esta palanca -- el patrón
contradictorio entre Split2 y Split3 es evidencia en contra más fuerte
que la de cualquier palanca anterior.

## Palanca nueva: fatiga del día completo -- `min/max_day_matches_played` (2026-08-22, motor corregido)

Segundo factor genuinamente distinto: partidos ya jugados por el
jugador HOY, cruzando sesiones/torneos (no solo dentro de la sesión
actual). Dos direcciones: `min_day_matches_played` (exigir que ya haya
"calentado" hoy) y `max_day_matches_played` (excluir jugadores
sobrecargados hoy). Barrido de los dos ejes contra los 6 splits:

| Split | Baseline test | Mejor `min_day_matches_played` | Mejor `max_day_matches_played` |
|---|---|---|---|
| 1 | 126/46%/+7.9% | min=5 → 43/51%/**+20.9%** | max=12 → 124/46%/+7.4% (~no-op) |
| 2 | 106/43%/-2.9% | sin mejora (min=5/8 → -16.4%) | max=3 → 23/52%/**+13.8%** |
| 3 | 46/50%/+11.1% | sin mejora (min=5/8 → -5.9%) | max=5 → 23/52%/**+19.9%** |
| 4 (hist.) | 22/50%/+14.5% | sin datos suficientes | max=12 → 21/48%/+10.0% (peor) |
| 5 (hist., malo) | 38/42%/-9.8% | min=5/8 → 10/70%/**+58.8%** | TODOS peores (hasta -49.2%) |
| 6 (hist.) | 34/47%/+8.5% | sin datos suficientes | sin mejora (max=12 → +6.6%) |

Patrón: `min_day_matches_played` (exigir calentamiento) ayuda a Split1 y
Split5; `max_day_matches_played` (limitar sobrecarga) ayuda a Split2 y
Split3 -- pero cada eje es indiferente o CONTRAPRODUCENTE en los splits
que el otro eje mejora (p.ej. `max_day_matches_played=5` hunde Split1 a
-11.3% mientras mejora Split3). Ninguna combinación fija sirve para los
6 a la vez.

**Nota sobre Split5**: `min_day_matches_played=5/8` da el PRIMER
resultado positivo de toda la sesión para el periodo históricamente
malo (+58.8%, hit 70%) -- pero con n=10, justo en el piso mínimo de
muestra, así que es evidencia débil (podría ser ruido de una muestra
muy pequeña). Se anota por si vale la pena revisarlo cuando haya más
datos históricos para ese periodo, pero no cambia la conclusión.

**Descartada** por el mismo motivo que las anteriores: ayuda a splits
distintos según el eje, se contradice entre sí, y no hay combinación
universal. Split4 y Split6 no tienen volumen suficiente para evaluar
ninguno de los dos ejes con confianza.

## Re-validación de `min_avg_games_won` con el motor corregido (2026-08-22)

Pendiente desde el fix del bug de orden: la palanca más prometedora de
toda la sesión (pre-fix) nunca se había confirmado contra el motor
corregido. Re-barrida contra los 6 splits:

| Split | Baseline test | Mejor `min_avg_games_won` |
|---|---|---|
| 1 | +7.9% | **sin mejora** -- TODOS los valores positivos empeoran (hasta -14.8%) |
| 2 | -2.9% | 1.7 → 57/51%/**+16.8%** |
| 3 | +11.1% | 1.7 → 21/52%/**+19.9%**, 1.5 → 28/54%/+19.6% (ambos muy cerca del listón) |
| 4 (hist.) | +14.5% | **sin mejora** -- todos los valores positivos empeoran |
| 5 (hist., malo) | -9.8% | 1.5 → 23/48%/+3.5% (mejora pero lejos del listón) |
| 6 (hist.) | +8.5% | **sin mejora** -- todos los valores positivos empeoran (hasta -11.7%) |

**Resultado clave**: el patrón se INVIERTE por completo respecto a
pre-fix. Antes ayudaba a Split1/2/3 (los splits recientes) y era
neutro/malo en Split4/5/6; ahora AYUDA a Split2/3/5 y EMPEORA
Split1/4/6. Esto confirma de forma directa que la mejora vista antes
del fix era un artefacto del motor roto (Elo mal ordenado), no señal
real -- exactamente la advertencia que se dejó anotada al arreglar el
bug. Con el motor corregido, `min_avg_games_won` tampoco pasa el
listón y no muestra ninguna consistencia direccional confiable.
**Descartada** (esta vez de forma definitiva, con el motor bueno).

## Re-validación de `min_matches_played` con el motor corregido (2026-08-22)

Igual que `min_avg_games_won`, el otro candidato fuerte de antes del
fix (`min_matches_played=4`, la palanca "casi" de toda la sesión)
nunca se había re-confirmado. Barrido [2,3,4,5,6] contra los 6 splits:

| Split | Baseline (min=3) | `min=4` | `min=2` |
|---|---|---|---|
| 1 | 126/46%/+7.9% | 53/45%/**+13.2%** | 179/46%/+6.5% (peor) |
| 2 | 106/43%/-2.9% | 58/45%/**+2.6%** | 166/39%/-14.1% (peor) |
| 3 | 46/50%/+11.1% | 21/76%/**+70.5%** (!) | 71/52%/+18.1% |
| 4 (hist.) | 22/50%/+14.5% (mejor, sin datos para min≥4) | -- | 34/47%/+5.1% (peor) |
| 5 (hist., malo) | 38/42%/-9.8% | 13/54%/**+14.2%** | 51/49%/**+14.7%** |
| 6 (hist.) | 34/47%/+8.5% (mejor) | 18/39%/**-13.1%** (peor) | 50/42%/+0.0% (peor) |

**Esta es la señal más consistente de toda la sesión, con el motor ya
corregido**: `min_matches_played=4` mejora en la MISMA dirección en 4
de los 5 splits evaluables (Split1, Split2, Split3, Split5), incluido
un resultado enorme en Split3 (n=21, hit 76%, ROI +70.5%) y una mejora
sustancial en Split5 (el periodo históricamente malo, de -9.8% a
+14.2%). Solo Split6 empeora con claridad (+8.5% → -13.1%), y Split4 no
tiene volumen suficiente para evaluar min=4 con confianza.

**No pasa el listón** (no todos los splits llegan a ROI≥20%
individualmente, y Split6 falla en dirección contraria), así que
tampoco se promueve. Pero por la regla del protocolo de "consistencia
muy fuerte across-splits sin llegar al listón individual", esto se
reporta al usuario en detalle en vez de descartarse en silencio --
mejorar en la misma dirección en 4/5 splits con el motor YA CORREGIDO
es la evidencia más sólida de toda la sesión hasta ahora, muy por
encima de cualquier otra palanca probada (incluida la propia
`min_avg_games_won` pre-fix, que resultó ser artefacto).

Intento de rescatar Split6 combinando `min_matches_played=4` con
`min_edge`/`min_model` más laxos o más estrictos (grid de 12 combos):
las 12 dan EXACTAMENTE el mismo resultado (18/39%/-13.1%) -- el cuello
de botella en Split6 no es el umbral de señal, son directamente otros
partidos/jugadores los que quedan elegibles con min=4 en ese periodo.
No hay margen para rescatarlo ajustando edge/model; se abandona esa
línea.

## Palanca nueva: `min_h2h_matches` -- historial H2H previo del par concreto (2026-08-22)

Cuarto factor genuinamente distinto probado contra el motor corregido,
combinado con `min_matches_played` en [3,4]. Resultado por split (mejor
combo con h2h>0 vs. el mejor conocido hasta ahora, que siempre es
h2h=0):

| Split | Mejor conocido (h2h=0) | Mejor con h2h>0 |
|---|---|---|
| 1 | min=4 → +13.2% | h2h=1,min=4 → -8.4% (peor) |
| 2 | min=4 → +2.6% | h2h=2,min=3 → +1.4% (peor) |
| 3 | min=4 → +70.5% | h2h=1,min=4 → +60.6% (n=18, casi igual pero peor) |
| 4 (hist.) | min=3 → +14.5% | h2h=1,min=3 → -7.0% (peor) |
| 5 (hist., malo) | min=2/4 → +14.2%/+14.7% | **h2h=1,min=3 → 18/61%/+32.6%** (mejor con diferencia) |
| 6 (hist.) | min=3 → +8.5% | h2h=1,min=3 → -8.7% (peor) |

`min_h2h_matches>0` NUNCA mejora sobre el mejor conocido salvo en
Split5, donde `h2h=1,min=3` da el mejor resultado de ese split en toda
la sesión (+32.6%, n=18) -- pero ese mismo combo EMPEORA con claridad
Split1, Split2, Split4 y Split6. No es una palanca generalizable, es
una mejora aislada de un solo split (y encima el históricamente más
ruidoso). **Tampoco rescata Split6** -- ninguna combinación de
`min_h2h_matches` mejora ese split, sigue siendo el obstáculo.
Descartada como palanca general.

## Cola de teorías nuevas

- [ ] min_market_gap (siempre 0.005) -- nunca barrido.
- [ ] Filtro por volumen histórico TOTAL del jugador a lo largo de todo el warmup -- IMPLEMENTADO y probado (min_career_matches), mejora 3/5 splits pero empeora Split1, descartado por ahora.
- [ ] Filtro por franja horaria dentro de la sesión -- IMPLEMENTADO y probado, mismo patrón mixto, descartado por ahora.
- [ ] min_edge / min_ev barridos en rango más fino (0.04-0.15) -- IMPLEMENTADO y probado, sin efecto.
- [ ] Combinar `min_career_matches` + franja horaria tardía a la vez -- aún no probado, ambas palancas mejoran Split1/3 de forma independiente, ver si se refuerzan sin empeorar Split2 más de lo que ya lo hace cada una por separado.
- [ ] Cuando el backfill traiga más semanas históricas: repetir min_career_matches y franja horaria contra splits nuevos -- con solo 5 splits (2 de ellos con n muy bajo) no hay evidencia suficiente para saber si estas dos palancas generalizan o son ruido de un periodo concreto.

## Cómo evaluar cada teoría

1. Sweep walk-forward en los splits vigentes, `min_test_samples` >= 15-20 por split.
2. Leer el leaderboard COMPLETO (no solo top-15 si el grid es grande -- usar grids pequeños y enfocados, no de 100+ combos, para poder ver todo).
3. Para cada combo candidata: ¿ROI >= 30% Y n >= 15-20 en LOS TRES splits? Si algún split falla ese doble criterio, descartar y anotar en "Probado y descartado".
4. Si algo pasa: verificar volumen (picks/día), y SOLO ENTONCES avisar al usuario con la evidencia completa.
5. Actualizar esta bitácora siempre, pase o no pase.

## Retomados los sweeps sin GitHub Actions (2026-08-23)

GitHub Actions se quedó sin cuota (no resetea en ~10 días). A partir de esta
sesión, los sweeps se corren directamente aquí con Bash contra Turso
(`TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` ya presentes como variables de
entorno del entorno cloud, sin necesidad de credenciales de BetsAPI para
nada de esto). `.venv` no existía en este contenedor fresco -- se recreó con
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
Verificado con `cli status`: 156 días con datos (2024-08-21→2024-12-08 y
2026-06-20→2026-08-22), motor y conexión funcionando.

**Nota metodológica importante para quien continúe**: `dbmod.connect()`
usa Turso automáticamente en cuanto `TURSO_DATABASE_URL` está en el entorno,
IGNORANDO el `db_path` que le pasan los tests (pensados para SQLite local
aislado). Con las credenciales de Turso ya exportadas globalmente en este
entorno, `python -m unittest discover` corría los tests de integración
contra la base de PRODUCCIÓN real, con colisiones de `match_uid` y errores
crípticos (`KeyError: 'result'`) en vez de fallos de test legibles. Hay que
correr la suite con `env -u TURSO_DATABASE_URL -u TURSO_AUTH_TOKEN
.venv/bin/python -m unittest discover -s tt_elite/tests` para que caiga en
SQLite temporal como estaba pensado. Con eso, 42/42 (ahora 43/43) en verde.

### 🚨 Cambio externo detectado en la estrategia activa a mitad de sesión

Al arrancar, `cli status` reportó `Estrategia activa: baseline_v7_sessk0`
(igual que toda la bitácora hasta ahora). En algún momento DURANTE esta
sesión (entre el sweep de `min_session_size` y el de `min_career_win_rate`),
el puntero `active_strategy_params` en Turso cambió a una estrategia
distinta, `candidata_1` (`session_k=42`, `session_delta_cap=105`,
`min_model=0.6`, `min_edge=0.09` -- notablemente distinta de
`baseline_v7_sessk0`). Esta sesión no la promovió -- el cambio vino de fuera
(dashboard web u otro proceso). Aviso al usuario: revisar si esa promoción
fue intencional.

Para que el resto de esta sesión (y cualquier continuación) no dependa de
un puntero "activo" que puede cambiar en cualquier momento desde fuera, se
fijaron explícitamente los parámetros de `baseline_v7_sessk0` (capturados
del propio `active_strategy_params` ANTES del cambio externo) como base de
comparación en vez de leer `load_active_params(conn)` en caliente:
`session_k=0, session_delta_cap=50, min_model=0.52, min_edge=0.04,
min_ev=0.02`, resto = defaults de `StrategyParams`. Verificado que esta
reconstrucción reproduce byte a byte los resultados ya obtenidos con
`--from-active` antes del cambio (mismo hash/mismos números). Todos los
sweeps de esta sesión a partir de este punto usan esta base fija.

## Sweep de `min_session_size`/`max_session_size` (commit `37bbcf3`) -- primera vez con éxito

Palanca implementada la sesión anterior pero nunca barrida contra los 6
splits (número TOTAL de partidos programados en la sesión/torneo del día,
conocido de antemano por el fixture -- sin look-ahead). Distribución real de
tamaños de sesión en los datos: prácticamente bimodal, `{8,10,12,14,15,21}`
con el 89% de las sesiones en tamaño 15 y un 10% en 10/12. Sweep
`min_session_size ∈ [0,10,12,15]` × `max_session_size ∈ [1e9,21,15,14,12]`
contra los 6 splits (`min_test_samples=15`):

| Split | Baseline test | Mejor `min_session_size` | Mejor test |
|---|---|---|---|
| 1 | 126/46%/+7.9% | 15 | 116/47%/**+9.6%** |
| 2 | 106/43%/-2.9% | 12 | 102/45%/**+0.9%** |
| 3 | 46/50%/+11.1% | 12 | 43/53%/**+18.8%** |
| 4 (hist.) | 22/50%/+14.5% | sin efecto (idéntico en los 12 valores probados) | -- |
| 5 (hist., malo) | 38/42%/-9.8% | sin efecto (idéntico) | -- |
| 6 (hist.) | 34/47%/+8.5% | sin efecto (idéntico) | -- |

Patrón limpio y nuevo: a diferencia de TODAS las palancas anteriores,
`min_session_size` (o su equivalente, excluir sesiones de tamaño 10) mejora
los 3 splits recientes SIN empeorar ninguno de los 3 históricos -- ahí el
filtro no corta absolutamente nada (mismos picks exactos, n y ROI idénticos
en los 12 valores de la grilla). Ningún valor cruza el listón de 20% salvo
Split3 (que ya lo cruzaba de cerca antes).

**Combo con `min_matches_played` (para ver si complementa la palanca más
fuerte conocida)**: resultado clave -- `min_session_size` es **totalmente
redundante** con `min_matches_played=4`. Con `min_matches_played=4` fijo,
variar `min_session_size` entre 0/12/15 da resultados IDÉNTICOS byte a byte
en los 6 splits. Explicación: una sesión de tamaño 10 casi nunca genera
candidatos donde ambos jugadores ya jugaron 4+ partidos previos dentro de
esa misma sesión, así que `min_matches_played=4` ya filtra implícitamente
lo mismo que `min_session_size≥12` filtra explícitamente.

**Conclusión**: no pasa el listón de 20% en los 6 splits (Split2 se queda en
+0.9%, muy lejos), y no es una señal nueva independiente -- es un proxy
parcial de `min_matches_played`, que ya se sabe que no basta por sí solo.
Se descarta como candidato definitivo (no se promueve), pero se documenta
en detalle por ser el primer caso de toda la sesión donde una palanca mejora
varios splits SIN perjudicar a ninguno de los otros (aunque sea porque no
los toca). Código queda activo en `replay.py`/`params.py` (default
0/1e9 = no-op).

## Palanca nueva: `min/max_career_win_rate` -- porcentaje de victorias en la CARRERA completa

Con la cola de teorías simples agotada, se implementó un factor
genuinamente nuevo: el **porcentaje de victorias** (no solo volumen, que ya
cubre `min_career_matches`) acumulado por cada jugador desde el inicio del
warmup, snapshot al INICIO de cada sesión (mismo patrón sin look-ahead que
`career_played`). Requirió un contador nuevo `career_wins` en `replay.py`
que persiste entre sesiones igual que `career_played`/Elo. Jugador sin
partidos de carrera previos = win rate 0.0 (misma convención que
`min_avg_games_won` con `played=0`). Test de regresión nuevo con dos
sesiones (una que construye el career record, otra con el candidato -- para
que el snapshot "sin look-ahead" tenga algo que capturar). Suite completa
43/43 en verde.

### Dirección `min_career_win_rate` (exigir un mínimo de victorias en carrera a AMBOS jugadores)

Barrido `[0, 0.3, 0.35, 0.4, 0.45, 0.5]` contra los 6 splits:

| Split | Baseline test | Mejor valor | Mejor test |
|---|---|---|---|
| 1 | 126/46%/+7.9% | 0.4 | 86/49%/**+17.1%** |
| 2 | 106/43%/-2.9% | 0.5 | 34/53%/**+13.3%** |
| 3 | 46/50%/+11.1% | 0.45 | 25/56%/**+24.7%** (cruza 20%) |
| 4 (hist.) | 22/50%/+14.5% | 0.4 | 20/50%/**+15.0%** (n al límite) |
| 5 (hist., malo) | 38/42%/-9.8% | 0.35 | 26/50%/**+6.4%** (primera vez POSITIVO con n>20) |
| 6 (hist.) | 34/47%/+8.5% | 0.35 (=baseline, sin efecto ahí) / 0.4 empeora a +5.4% | -- |

**Con un valor único fijo (`min_career_win_rate=0.3`) en los 6 splits a la
vez** (la prueba real de generalización, no el mejor-por-split):

| Split | Baseline | Con 0.3 | Dirección |
|---|---|---|---|
| 1 | +7.9% (n=126) | **+10.6%** (n=118) | mejora |
| 2 | -2.9% (n=106) | **-0.4%** (n=99) | mejora |
| 3 | +11.1% (n=46) | +8.5% (n=43) | empeora levemente |
| 4 | +14.5% (n=22) | +14.5% (n=22) | sin cambio (filtro no corta nada aquí) |
| 5 | -9.8% (n=38) | **-7.7%** (n=30) | mejora |
| 6 | +8.5% (n=34) | +8.5% (n=34) | sin cambio |

**Es el patrón más limpio de toda la sesión**: 3 splits mejoran, 2 quedan
exactamente igual (el filtro no encuentra nada que cortar ahí), y solo 1
(Split3) empeora, y de forma leve (-2.6pp, con solo 3 picks menos de
diferencia) -- nunca se hunde ningún split, a diferencia de CUALQUIER otra
palanca probada hasta ahora (`elo_scale=500`, `min_career_matches`, franja
horaria, `min_matches_played=4` con Split6 cayendo a -13.1%, etc.), que
siempre tenían al menos un split que se invertía con fuerza en la dirección
contraria.

### Dirección `max_career_win_rate` (excluir jugadores con récord de carrera muy dominante)

Barrido `[1.0, 0.7, 0.65, 0.6, 0.55]` contra los 6 splits -- dirección
distinta (limitar el techo en vez del suelo):

| Split | Mejor valor | Mejor test |
|---|---|---|
| 1 | 0.55 | 62/48%/**+13.2%** |
| 2 | ningún tope ayuda -- baseline (1.0) es el mejor | -2.9% |
| 3 | 0.55 | 30/53%/**+15.8%** |
| 4 | sin efecto por encima de 0.6 | +14.5% |
| 5 | 0.65 | 28/46%/**-0.7%** (mejor que -9.8%, aún negativo) |
| 6 | 0.55 | 15/53%/**+17.3%** (n al límite del piso) |

Dirección más irregular que `min_career_win_rate`: mejora Split1/3/6 con
fuerza pero **empeora Split2 con cualquier tope**, y Split4/5 necesitan
valores distintos entre sí. Se probó también la banda combinada (`min` y
`max` a la vez, grid `min∈[0,0.25,0.3]`×`max∈[1.0,0.6,0.65,0.7]`): ninguna
banda combinada supera a `min_career_win_rate=0.3` solo (sin tope) en
limpieza -- combinar ambos lados vuelve a introducir el mismo patrón mixto
que ya se vio con otras palancas, perdiendo la propiedad de "nunca empeora
con fuerza" que hace especial a la dirección `min` sola.

### Combo con `min_matches_played=4`

Igual que con `min_session_size`: combinar no rescata nada. Con
`min_matches_played=4` fijo, `min_career_win_rate>0` no cambia Split6
(sigue en -13.1%, el mismo obstáculo de siempre) y Split4/5 se quedan sin
n suficiente en casi todas las combinaciones. La mejora de
`min_career_win_rate=0.3` y la de `min_matches_played=4` no se refuerzan.

### Conclusión y siguiente paso

`min_career_win_rate=0.3` (solo, sin tope superior) **no pasa el listón de
20% en los 6 splits a la vez** -- Split2 (-0.4%), Split4 (+14.5%) y Split5
(-7.7%) se quedan lejos. Pero por la regla del protocolo ("consistencia muy
fuerte entre splits sin llegar al listón individual -> reportar en detalle,
nunca descartar en silencio ni promover"), esta es la palanca que mejor
cumple esa condición de toda la sesión hasta ahora: mejora 3 splits, no
toca 2, y solo roza a la baja 1 (leve, sigue positivo). Se reporta al
usuario en detalle. No se promueve. Código queda activo en
`replay.py`/`params.py` (`min_career_win_rate=0.0`/`max_career_win_rate=1.0`
= no-op, no toca nada existente).

Candidato para seguir explorando: afinar el umbral óptimo (¿0.25? ¿0.28?)
cuando haya más días de datos, y probar esta palanca combinada con
`min_avg_games_won` (dominio EN SESIÓN) ya que miden cosas relacionadas
pero distintas -- volumen de carrera completa vs. forma reciente dentro de
la sesión -- y ninguna de las dos por separado ha mostrado nunca un split
que se hunda con fuerza como sí pasa con `elo_scale`, franja horaria o
`min_matches_played`.

## Cola de teorías nuevas (actualizada 2026-08-23)

- [ ] Afinar `min_career_win_rate` en el rango 0.20-0.35 con más granularidad cuando haya más días de datos (Split4/Split5 tienen n bajo justo en ese rango).
- [ ] Combinar `min_career_win_rate=0.3` con `min_avg_games_won` (forma en sesión) -- ninguna de las dos por separado hunde ningún split, ver si juntas sí cruzan el listón sin introducir el patrón de "un split se invierte con fuerza".
- [ ] `min_session_size` queda confirmado como redundante con `min_matches_played` -- no seguir esta línea salvo que aparezcan sesiones de tamaños nuevos con más historial.
- [ ] Explorar factores basados en cuotas de la línea de referencia vs. cierre (si el dato de movimiento de línea llega a estar disponible).
- [ ] Revisar por qué el puntero de estrategia activa cambió a `candidata_1` a mitad de esta sesión -- confirmar con el usuario si fue intencional antes de que el scanner en vivo siga usándola. **Actualización**: el usuario confirma que no lo tocó él. Verificado en el código: `save_active_params` (lo único que escribe `meta.active_strategy_params`) solo se invoca desde `cli.py promote`, que requiere ejecutarse explícitamente -- esta sesión nunca lo corrió (solo `status` y `sweep`, que solo escriben en la tabla `experiments`). El cambio vino de fuera de esta sesión (otro proceso con acceso a la misma Turso -- dashboard web u otra sesión concurrente). Sigue sin explicación confirmada; el scanner en vivo sigue usando `candidata_1` mientras tanto.

## `min_career_matches` re-barrida SOLA (sin `min_matches_played=4`) -- el candidato más fuerte de toda la sesión (2026-08-23)

El barrido original de `min_career_matches` (sección de arriba, "Palanca nueva: `min_career_matches`") se hizo con `min_matches_played=4` fijo, y era ANTERIOR al fix del bug de orden de sesiones -- nunca se había re-confirmado sola, con el motor corregido y contra los 6 splits vigentes. Se re-barrió `[0,10,15,20,25,30]` sola (sin combinar con nada) contra los 6 splits:

| Split | Baseline (0) | Mejor valor | Mejor test |
|---|---|---|---|
| 1 | 126/46%/+7.9% | 15 | 112/48%/**+12.5%** |
| 2 | 106/43%/-2.9% | 15 | 97/44%/**-0.6%** |
| 3 | 46/50%/+11.1% | 0 (cualquier valor >0 lo baja un poco) | -- |
| 4 (hist.) | 22/50%/+14.5% | 20 | 21/48%/+9.5% (peor) |
| 5 (hist., malo) | 38/42%/-9.8% | **20** | 22/55%/**+18.5%** (¡primera vez positivo con n>20!) |
| 6 (hist.) | 34/47%/+8.5% | 20 | 32/47%/+5.9% (peor) |

**Split5 con `min_career_matches=20` es el resultado más importante de toda la sesión hasta ahora**: es el periodo históricamente peor (siempre negativo, en TODAS las palancas probadas hasta ahora), y por primera vez cruza a positivo con volumen razonable (n=22, por encima del piso de 15-20) -- no es un n=5-10 de ruido puro.

### Combo `min_career_matches=15` + `min_career_win_rate=0.3`

Se probó si combinar esta palanca con la mejor encontrada la ronda anterior (`min_career_win_rate=0.3`) se refuerza. Resultado: **sí, y de forma excepcionalmente limpia**. Con un valor único fijo para cada parámetro, comparado contra el baseline puro en los 6 splits:

| Split | Baseline | `min_career_matches=15` sola | + `min_career_win_rate=0.3` |
|---|---|---|---|
| 1 | +7.9% (n=126) | +12.5% (n=112) | **+13.5%** (n=111) |
| 2 | -2.9% (n=106) | -0.6% (n=97) | **+0.4%** (n=94) |
| 3 | +11.1% (n=46) | +9.1% (n=41) | +9.1% (n=41) *(igual)* |
| 4 (hist.) | +14.5% (n=22) | +14.5% (n=22) | +14.5% (n=22) *(igual)* |
| 5 (hist., malo) | -9.8% (n=38) | +8.6% (n=24) | **+12.3%** (n=21) |
| 6 (hist.) | +8.5% (n=34) | +2.7% (n=33) | +2.7% (n=33) *(igual)* |

**Es la primera vez en TODA la sesión que una palanca (o combinación) mejora o iguala al baseline en los 6 splits simultáneamente, sin excepción** -- nunca empeora con fuerza en ninguno. El peor caso es Split6, que baja de +8.5% a +2.7% (una caída moderada, nunca se invierte a negativo). Comparado con cualquier otra palanca de la sesión (`min_matches_played=4` con Split6 cayendo a -13.1%, `elo_scale=500` hundiendo Split2, franja horaria con direcciones opuestas entre Split2/Split3, etc.), esto es cualitativamente distinto: ninguna caída fuerte, y una mejora dramática en el peor periodo histórico (Split5).

### Variantes descartadas para no perder la limpieza del resultado

- **`max_career_win_rate` (tope, en vez de suelo) combinado con `min_career_matches`**: reintroduce el patrón de siempre -- `min_career_matches=15,max_career_win_rate=0.55` da Split1 +17.8%, Split3 +16.5%, Split6 +17.3% (muy fuerte), pero Split2 se hunde a **-11.0%** y Split4/Split5 se quedan sin n suficiente. Descartada: vuelve a introducir el "un split se invierte con fuerza" que la combinación con suelo (`min_career_win_rate`) evita.
- **`min_avg_games_won` combinado con `min_career_matches=15`**: empeora Split1/2/4/6 de forma monótona según sube el umbral (aunque mejora Split3/5). Mismo patrón mixto de siempre. Descartada.

### Conclusión

`min_career_matches=15` + `min_career_win_rate=0.3` **sigue sin pasar el listón de ROI>=20% en los 6 splits a la vez** -- Split2 (+0.4%) y Split6 (+2.7%) son ahora el obstáculo real y claro (ya no es "casi todos menos uno", es estos dos concretamente los que se quedan muy lejos de 20% pase lo que pase). Pero es, con diferencia, **el hallazgo más limpio y consistente de toda la búsqueda**: mejora 3 splits con fuerza (incluido el histórico peor, por primera vez), iguala 2, y solo roza a la baja 1 sin invertirlo. Se reporta en detalle al usuario. No se promueve -- no cumple el listón completo.

Este combo queda como el **nuevo "mejor candidato aún sin validar"** de la bitácora, reemplazando a `min_matches_played=4` (que crashea Split6) y a `min_career_win_rate=0.3` solo (que este combo mejora en todos los splits sin excepción). Próximo paso natural: seguir la búsqueda de factores que expliquen específicamente por qué Split2 y Split6 se resisten a mejorar con cualquier palanca probada hasta ahora (9+ palancas distintas), en vez de seguir afinando esta combinación (riesgo de sobreajuste a los 4 splits que sí responden).

**Actualización (más abajo, misma sesión)**: este combo quedó SUPERADO por
`min_career_matches=15` + `min_career_win_rate=0.3` + `fb_min_model=0.58` +
`min_market_gap=0.02` (ver sección "`fb_min_model` re-barrida en serio"),
que resuelve Split2 y deja los 6 splits en positivo -- solo Split6 sigue
sin resolverse. Ese combo posterior es el candidato de referencia actual.

## Palanca nueva: día de la semana calendario -- `min/max_weekday` (2026-08-23)

Factor genuinamente nuevo, nunca tocado hasta ahora: día de la semana del
partido (`date.weekday()`, 0=lunes..6=domingo -- calendario, sin
look-ahead). Código + test de regresión (45/45 en verde). Barrido contra
Split2 y Split6 (los dos obstáculos del combo `min_career_matches=15` +
`min_career_win_rate=0.3`) usando ese combo como base:

- **Split2** (2026-08-10 lunes → 08-16 domingo): restringir a
  `max_weekday=1` (solo lunes+martes) dispara el resultado a
  **29/52%/+20.8%** -- ¡cruza el listón!
- **Split6** (2024-10-20 domingo → 10-26 sábado): restringir a
  `max_weekday=3` (lunes-jueves) dispara a **18/56%/+29.0%** -- también
  cruza el listón.

A primera vista, parecía el hallazgo que faltaba. Pero al confirmar el
mismo filtro (`max_weekday=1` y `max_weekday=3`) contra los OTROS 4 splits,
se repite el patrón de siempre: **Split1 empeora** con cualquier recorte de
`max_weekday` (+13.5% → +11.1% en max=1, cayendo a +1.5% en max=4),
**Split4 y Split5 pierden n** por debajo del piso en cuanto se recorta.
Split3 mejora ligeramente pero ya son solo 3 días (lunes-miércoles) de por
sí.

**Problema metodológico de fondo, no solo "otro patrón mixto"**: con
splits de 7 días, cada día de la semana aparece **como mucho una vez** en
la ventana de test. Un filtro `max_weekday=1` en un split de 7 días no
está promediando sobre "los lunes y martes en general" -- está
literalmente seleccionando 2 fechas concretas de las 7 disponibles. La
mejora en Split2/Split6 es indistinguible de sobreajustar a qué días en
particular tuvieron buena racha esa semana concreta, no evidencia de que
"lunes y martes" sean estructuralmente mejores. A diferencia de
`min_hour_of_day` (que promedia sobre MUCHOS partidos de cada franja
horaria dentro de cada split) o `min_career_matches` (que aplica por
candidato, no por fecha), `min/max_weekday` no tiene suficiente
replicación dentro de un split corto para ser una prueba honesta.

**Descartada, con esta advertencia metodológica anotada explícitamente**:
no repetir este patrón de "recortar a un subconjunto de fechas dentro de
un split de 7 días" como prueba de una palanca nueva -- necesitaría splits
mucho más largos (semanas/meses) para que el día de la semana tenga
réplicas suficientes por split. Código queda en el repo como parámetro
opt-in (default 0/6 = no-op).

## Análisis estadístico: ¿es Split2/Split6 una señal real, o ruido de muestreo? (2026-08-23)

Antes de seguir apilando filtros sobre el mejor candidato (`min_career_matches=15`
+ `min_career_win_rate=0.3`) para intentar "arreglar" Split2 y Split6, se hizo
un diagnóstico directo en vez de seguir buscando a ciegas.

**Paso 1 -- ¿son los picks de Split2/Split6 de peor calidad?** Se comparó la
cuota media, edge y EV de los picks del combo en los 6 splits:

| Split | n | hit real | cuota media | edge medio | breakeven (1/cuota) |
|---|---|---|---|---|---|
| 1 | 111 | 48.6% | 2.28 | 0.210 | 45.3% |
| 2 | 94 | 44.7% | 2.27 | 0.199 | 44.9% |
| 3 | 41 | 48.8% | 2.30 | 0.207 | 44.9% |
| 4 | 22 | 50.0% | 2.34 | 0.220 | 43.8% |
| 5 | 21 | 52.4% | 2.26 | 0.208 | 44.7% |
| 6 | 33 | 45.5% | 2.33 | 0.216 | 44.1% |

**No hay diferencia real en la calidad de los picks seleccionados** -- cuota
media, edge y EV son prácticamente idénticos en los 6 splits (todos
alrededor de cuota ~2.3, breakeven ~44-45%). El modelo está igual de
"seguro" de sus picks en todos los periodos. La diferencia entre splits
está solo en el HIT RATE REALIZADO.

**Paso 2 -- test de homogeneidad (chi-cuadrado) entre los 6 hit rates
observados.** Bajo la hipótesis de que las 6 muestras vienen de una única
tasa de acierto real (~47.5%, la pooled), con solo ruido binomial de
muestreo por el tamaño de cada split:

```
Split1: n=111 hit=48.6% z=+0.24
Split2: n=94  hit=44.7% z=-0.55
Split3: n=41  hit=48.8% z=+0.16
Split4: n=22  hit=50.0% z=+0.23
Split5: n=21  hit=52.4% z=+0.45
Split6: n=33  hit=45.5% z=-0.24

chi2 = 0.70 (df=5), p-valor ~= 0.98
```

Ningún split se desvía siquiera 1 desviación estándar del pool (todos
`|z|<0.6`). Un chi2 tan bajo como 0.70 con 5 grados de libertad es
compatible con ruido puro de sobra (p=0.98 -- lo esperable si NO hay
diferencia real es un chi2 así de bajo o más el 98% de las veces).
**No hay evidencia estadística de que Split2 y Split6 sean periodos
estructuralmente distintos** de Split1/3/4/5 -- la variación observada en
ROI split a split es exactamente lo que se esperaría de puro ruido de
muestreo con ventanas de 20-110 picks, no de una diferencia real de señal.

**Implicación importante**: seguir buscando una palanca que "arregle"
Split2/Split6 específicamente corre el riesgo de estar cazando ruido en
esos dos splits concretos (sobreajuste), no encontrando una señal real que
los distinga de los otros cuatro. Cualquier filtro que mejore Split2/Split6
de forma aislada sin mecanismo causal claro debería tratarse con mucha
sospecha -- que es justo lo que se vio con `min_weekday` (mejoraba ambos
recortando a fechas concretas, pero empeoraba Split1/4/5).

**Paso 3 -- ROI pooled y su significancia real.** Con los 322 picks de test
de los 6 splits juntos (combo `min_career_matches=15` + `min_career_win_rate=0.3`):

```
n=322, hit=47.5%, ROI pooled = +7.97%, pnl total = +25.68u
Test t sobre pnl por pick: media=+0.0797u, sd=1.179, t=+1.21
```

**t=1.21 NO es estadísticamente significativo** (hace falta t>~1.65 a una
cola para el 95%). El ROI pooled +7.97% es alentador -- mejor que el
+5.28%/+3.9% del baseline puro visto antes en esta bitácora -- pero con
n=322 la muestra sigue siendo demasiado pequeña para poder afirmar con
confianza que hay un edge real y no una racha. Este es exactamente el
motivo honesto por el que ningún split individual (con n=20-110 cada uno)
puede llegar de forma fiable al listón de 20% incluso si la estrategia
tuviera un edge real y modesto: la varianza semana a semana a estos
tamaños de muestra es simplemente demasiado alta.

**Conclusión de este análisis**: la prioridad para la siguiente ronda no
debería ser seguir cazando palancas que "arreglen" splits concretos --
probablemente no hay nada que arreglar, es ruido. La prioridad real es
**acumular más días de datos** (el backfill histórico sigue siendo la
única vía honesta para que n crezca lo suficiente y esta pregunta se
pueda responder con confianza), y seguir vigilando si el ROI pooled del
mejor candidato se mantiene positivo según la muestra vaya creciendo.

## Balance de la sesión (2026-08-23) y estado de la búsqueda

Después de esta ronda (min_session_size descartado y redundante,
min/max_career_win_rate, min_career_matches re-barrida sola, el combo
min_career_matches+win_rate como mejor candidato limpio, min/max_weekday
descartado por motivo metodológico, `min_market_gap` apilado sobre el
mejor combo, y el análisis estadístico de homogeneidad entre splits), el
estado sigue siendo: **ningún candidato pasa ROI>=20% Y n adecuado en los
6 splits simultáneamente**. El mejor candidato reportado
(`min_career_matches=15` + `min_career_win_rate=0.3`, opcionalmente +
`min_market_gap=0.02`) es el más consistente de toda la búsqueda pero se
queda corto en Split2 (+0.4%/-0.6%) y Split6 (+2.7%/+5.9%).

Pero el hallazgo más importante de esta ronda no es una palanca más: es
que el análisis estadístico (chi2 p=0.98) muestra que la diferencia entre
splits "buenos" y "malos" es indistinguible de ruido de muestreo puro dado
el tamaño de cada ventana (20-110 picks). El ROI pooled del mejor
candidato sobre los 6 splits juntos (n=322) es +7.97%, direccionalmente
positivo pero aún sin significancia estadística (t=1.21). La lectura
honesta: no hay evidencia de que la estrategia "falle" en periodos
concretos, ni tampoco evidencia suficiente todavía de que el edge sea
real y no suerte -- hace falta más n. La búsqueda de palancas nuevas que
"arreglen" splits concretos tiene rendimientos decrecientes y riesgo de
sobreajuste creciente (look-elsewhere effect); la vía más honesta para
seguir es acumular más días de datos (backfill) y volver a evaluar el
mismo candidato con splits más largos/más numerosos, en vez de seguir
apilando filtros sobre una muestra que ya es demasiado pequeña para
diferenciar señal de ruido con confianza.

## 🔎 Corrección importante: `Interwetten` (la línea "de referencia") nunca tiene cuotas -- todo el pipeline corre 100% por el camino `SI_FALLBACK` (2026-08-23)

Al investigar por qué `min_model`/`min_edge`/`min_ev` salieron "inertes" en
varias rondas anteriores (Grid A/B/C, sección "Ronda 20% + mejorar hit
rate"), se encontró la causa raíz: `config.BOOKS` define `Interwetten`
como la casa "de referencia" (`is_fallback=False`), pero en **toda** la
tabla `raw_odds` de producción (21,349 filas reales) **no hay ni una sola
fila con `is_fallback=0`** -- Interwetten nunca devuelve cuota para esta
liga vía BetsAPI. Confirmado también con los picks generados: el 100% de
las señales accionables de cualquier combo probado en esta sesión son
`SI_FALLBACK`, nunca `SI` (verificado con `Counter(p.signal for p in ...)`).

Esto **explica por completo** por qué `min_model`, `min_edge`, `min_ev`
(los umbrales del camino "estándar", `not is_fallback and standard`)
nunca movieron nada en ningún sweep de esta sesión ni de sesiones
anteriores -- ese camino de código es **inalcanzable** con los datos
actuales, sin importar qué tan bajo o alto se pongan esos tres umbrales.
Los umbrales que sí gobiernan la señal real son `fb_min_model`,
`fb_min_edge`, `fb_min_ev` (el camino `SI_FALLBACK`), que hasta ahora solo
se habían tocado una vez, en la ronda "Grid B" (`fb_min_model` en
[0.55, 0.99] combinado con `min_matches_played=4`), con la conclusión
-- ahora vista como **incorrecta o mal interpretada** -- de que "el pool
actual no está usando casas de respaldo en absoluto". Dado que TODO pick
posible pasa por `SI_FALLBACK`, esa conclusión no podía ser cierta; lo que
probablemente ocurrió es que, con `min_matches_played=4` ya muy filtrado,
ningún pick sobreviviente tenía `model` por debajo de 0.99 en ese momento
concreto, no que el camino fallback estuviera desactivado.

**No es un bug que haya que arreglar aquí** (arreglar por qué Interwetten
no devuelve cuota requeriría tocar `collect.py`/BetsAPI, fuera de alcance
explícito de esta sesión) -- es un hecho del pipeline de datos a tener en
cuenta: cualquier sweep futuro de `min_model`/`min_edge`/`min_ev` sin
`fb_min_*` es, con los datos de hoy, un sweep de un camino de código
muerto.

## `fb_min_model` re-barrida en serio -- nuevo mejor candidato de la sesión (2026-08-23)

Con la causa raíz identificada, se barrió `fb_min_model` (el umbral real
que gobierna la señal) en un rango fino `[0.55-0.65]` sobre el mejor
combo conocido (`min_career_matches=15` + `min_career_win_rate=0.3`),
contra los 6 splits:

| Split | Base (`fb_min_model=0.55`) | `fb_min_model=0.58` |
|---|---|---|
| 1 | +13.5% (n=111) | +11.1% (n=86) |
| 2 | +0.4% (n=94) | +13.1% (n=68) |
| 3 | +9.1% (n=41) | +3.8% (n=28) |
| 4 | +14.5% (n=22) | +19.2% (n=18) |
| 5 | +12.3% (n=21) | **+25.7%** (n=17, cruza el listón) |
| 6 | +2.7% (n=33) | +3.4% (n=24) |

`fb_min_model=0.58` sube Split2, Split4 y Split5 con fuerza (Split5 ya
cruza 20%) a cambio de bajar algo Split1 y Split3 -- **pero ningún split
se vuelve negativo**, algo que no había pasado con ninguna otra palanca de
esta ronda salvo la combinación career_matches+win_rate.

### + `min_market_gap=0.02` -- combina y cierra la brecha en Split1/Split3

Apilando `min_market_gap=0.02` (que en la ronda anterior ya ayudaba
específicamente a Split1/Split3 sin tocar los demás) sobre
`fb_min_model=0.58`:

| Split | n | hit | ROI test |
|---|---|---|---|
| 1 | 79 | 48.1% | **+13.9%** |
| 2 | 67 | 49.3% | **+12.1%** |
| 3 | 26 | 50.0% | **+11.8%** |
| 4 | 18 | 55.6% | **+19.2%** (al borde del listón) |
| 5 | 17 | 58.8% | **+25.7%** (cruza el listón) |
| 6 | 24 | 45.8% | +3.4% |

**Los 6 splits quedan en positivo, sin excepción** -- por primera vez en
toda la sesión (y probablemente en todo el proyecto). Cinco de los seis ya
están en doble dígito (11.8% a 25.7%), dos cruzan o rozan el listón de
20%. El único punto débil real es **Split6, atascado en +3.4%** pase lo
que pase con esta combinación -- es el mismo obstáculo aislado que ya se
identificó antes (ningún ajuste de `fb_min_model` lo llevó nunca por
encima de +7.9% en ningún valor probado).

### Significancia estadística del combo completo

Con los 231 picks de test pooled de los 6 splits
(`min_career_matches=15` + `min_career_win_rate=0.3` + `fb_min_model=0.58`
+ `min_market_gap=0.02`):

```
n=231, hit=49.8%, ROI pooled = +13.33%, pnl total = +30.79u
t-test sobre pnl por pick: mean=+0.133u, sd=1.187, t=+1.71
```

Mejora clara respecto al combo anterior (n=322, ROI +7.97%, t=1.21):
**t=1.71 ya supera el umbral de significancia al 95% a una cola**
(~1.65), aunque no llega al 95% a dos colas (~1.96). Es la evidencia más
fuerte de toda la sesión de que hay un edge real, aunque la muestra
(n=231) sigue sin ser lo bastante grande para una confianza completa.

### Estado: sigue sin pasar el listón completo, pero es el candidato definitivo de esta ronda

`min_career_matches=15` + `min_career_win_rate=0.3` + `fb_min_model=0.58`
+ `min_market_gap=0.02` **no pasa ROI>=20% en los 6 splits a la vez**
-- Split6 (+3.4%) es ahora el único bloqueo real y aislado (los otros 5
están todos en +11.8% o más). No se promueve. Pero es, con mucha
diferencia, el mejor candidato de todo el proyecto hasta la fecha:

- Ningún split negativo (primera vez).
- 5 de 6 en doble dígito.
- 2 de 6 ya cruzan o rozan el listón individual.
- Significancia estadística del pooled mejorando (t=1.21 → t=1.71).

Se reporta al usuario en detalle. Próximo paso natural si se sigue esta
línea: entender por qué Split6 específicamente se resiste incluso aquí
(dado el análisis de homogeneidad de arriba, lo más probable es que sea
varianza de muestra, no señal) -- y, sobre todo, **acumular más días de
datos** para que la pregunta se pueda zanjar con confianza real en vez de
seguir afinando umbrales sobre una muestra de 15-30 picks por split.

### Intentos adicionales de rescatar Split6 específicamente -- todos fallidos

Sobre el combo completo (`min_career_matches=15` + `min_career_win_rate=0.3`
+ `fb_min_model=0.58` + `min_market_gap=0.02`), se probó:

- `fb_min_edge` [0.10-0.20] × `fb_min_ev` [0.08-0.16]: `fb_min_ev` inerte
  en todo el rango (mismo patrón "no muerde" visto con `min_ev` antes).
  `fb_min_edge` alto EMPEORA Split6 (+3.4% → -2.5% en 0.20), no lo mejora.
- `elo_scale` [300-600]: `elo_scale=450` es el único valor que mejora
  Split6 (+3.4% → +7.9%, la mejor cifra vista ahí en toda la sesión), pero
  a costa de volver **negativo** a Split3 (+3.8% → -5.0%) y bajar
  Split1/Split2 -- reintroduce exactamente el patrón de trade-off que el
  combo actual (con `elo_scale=400`, el default) había logrado evitar por
  primera vez. Descartado: preferible mantener los 6 splits en positivo
  que ganar ~4pp en Split6 a costa de perder esa propiedad.

Con esto se han probado, solos o en combinación, absolutamente todos los
parámetros de `StrategyParams` contra Split6 (18 palancas distintas en
total contando esta sesión y las anteriores). Ninguno lo lleva por encima
de +8% en ningún valor, con o sin efectos secundarios en otros splits.
Combinado con el análisis de homogeneidad (chi2 p=0.98), la conclusión más
honesta es que Split6 no tiene una causa identificable y accionable con
los datos actuales -- probablemente es varianza de muestra de una ventana
de 7 días, no una palanca pendiente de descubrir. Se cierra esta línea de
búsqueda específica (rendimientos decrecientes, riesgo de sobreajuste) y
se prioriza acumular más datos sobre seguir iterando parámetros.
