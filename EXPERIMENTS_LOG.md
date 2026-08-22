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
