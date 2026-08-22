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

## Probado y descartado (ronda 20%+hit rate)

| Teoría | Resultado |
|---|---|
| `min_model` 0.55/0.60/0.65 (vs 0.52) | Sin efecto: resultados idénticos en los 5 splits. El filtro no muerde en ese rango. |
| `min_odds_underdog` 1.3/1.5/1.8 (vs 1.0) | Sin efecto: ningún pick aceptado tiene cuota underdog < 1.3. |
| `fb_min_model=0.99` (desactivar señales de casas de respaldo) | Sin efecto: el pool actual no genera señales `SI_FALLBACK` en estos 5 splits. |

## Cola de teorías nuevas

- [ ] min_market_gap (siempre 0.005) -- nunca barrido.
- [ ] Filtro por franja horaria / posición dentro de la sesión (partidos tempranos vs tardíos) -- requiere código nuevo en replay.py, aún no implementado.
- [ ] Filtro por volumen histórico TOTAL del jugador a lo largo de todo el warmup (distinto de min_matches_played, que solo mira dentro de la sesión actual) -- aún no implementado.
- [ ] min_edge / min_ev barridos en rango más fino (0.04-0.15) para ver si ahí sí hay una palanca real, ya que min_model no la tiene.
- [ ] Cuando haya más días de datos: repetir todo lo anterior contra splits nuevos, no solo los de siempre.

## Cómo evaluar cada teoría

1. Sweep walk-forward en los splits vigentes, `min_test_samples` >= 15-20 por split.
2. Leer el leaderboard COMPLETO (no solo top-15 si el grid es grande -- usar grids pequeños y enfocados, no de 100+ combos, para poder ver todo).
3. Para cada combo candidata: ¿ROI >= 30% Y n >= 15-20 en LOS TRES splits? Si algún split falla ese doble criterio, descartar y anotar en "Probado y descartado".
4. Si algo pasa: verificar volumen (picks/día), y SOLO ENTONCES avisar al usuario con la evidencia completa.
5. Actualizar esta bitácora siempre, pase o no pase.
