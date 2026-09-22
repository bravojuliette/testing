# PRE-REGISTRO: NCAAB PRE-PARTIDO (favorito-longshot y local infravalorado)

Escrito el 2026-09-03 ANTES de calcular un solo ROI sobre estos datos.
Peticion del usuario: nada en vivo, solo pre-partido.

## Por que NCAAB y por que ahora
Es la liga grande que nunca ha pasado la bateria con datos limpios: 10.733
partidos con marcador (temporada 2025-11 a 2026-03), 8.822 con linea de
total y 22 casas. Los intentos previos murieron por un bug de orientacion
(ENMIENDA 2 de PREREGISTRO_situacionales.md) que dejo aquellos veredictos
ANULADOS -- no refutados. Ahora hay 9.060 estadios reales para resolverlo.

## HALLAZGO DE INTEGRIDAD, fijado antes de cualquier test (y es una trampa)
El feed mezcla dos fuentes y en ~la mitad de los partidos las etiquetas
local/visitante estan invertidas: `bball_games` con cuotas da un 44.4% de
victorias del "local" guardado. Resuelto por estadio modal
(`bball/backtest/orientacion.py`, que solo usa geografia, ni resultados ni
cuotas): 4.221 'ok', 4.232 'swap', 563 neutrales, 1.717 sin dato. Corregido,
el local REAL gana el **63.0%** (n=6.816), justo lo esperable en D1.

**PERO las cuotas NO estan desalineadas del marcador.** Medido sobre casas
legales y moneyline de apertura, el favorito por cuotas gana:

| estado | n | tal cual | invirtiendo el marcador |
|---|---|---|---|
| swap | 6.083 | **72.3%** | 27.7% |
| neutral | 747 | 69.6% | 69.6% |
| sin_dato | 1.399 | 68.5% | 68.5% |

Es decir: los huecos `home_*`/`away_*` son consistentes entre marcador y
cuotas; lo unico erroneo es la ETIQUETA de quien juega en casa.

**REGLA (y aviso a sesiones futuras):** en un partido 'swap' se reetiqueta
que hueco es el local, NUNCA se intercambia el marcador. Intercambiarlo
rompe la alineacion con las cuotas y fabrica un +25% falso apostando al
no-favorito. Los tests de cuotas-contra-resultado (favorito/underdog,
totales) NO necesitan la correccion; solo la necesitan los que preguntan
quien esta fisicamente en casa.

## H1 -- SESGO FAVORITO-LONGSHOT (no necesita orientacion)
Los favoritos ganan el 72.3% en la muestra. La pregunta es si el precio lo
recoge. Se agrupan las apuestas de moneyline de APERTURA en casa legal
(Bet365/Betway/BWin, la primera disponible por ese orden) en cubos de cuota:
[1.01-1.20), [1.20-1.40), [1.40-1.70), [1.70-2.20), [2.20-3.00),
[3.00-5.00), [5.00-20.0]. Para cada cubo se calcula el ROI de respaldar
SIEMPRE ese lado.
- **CONFIRMADA** una celda con ROI > 0, t >= 2, n >= 300, MISMO signo en
  busqueda y reserva (corte por mediana de fecha) y monotonia no invertida
  (si el sesgo es real, el ROI debe ordenarse con la cuota, no saltar).
- REFUTADA el resto. NO CONCLUYENTE si n < 300.

## H2 -- EL LOCAL COMO NO-FAVORITO (si necesita orientacion)
Clasico documentado: el mercado infravalora al local debil. Se respalda al
equipo que (a) es el local REAL segun estadio y (b) es no-favorito por
cuotas de apertura en casa legal. Solo partidos 'ok' o 'swap' (los
'neutral' y 'sin_dato' quedan fuera por no poder afirmar quien es local).
- Mismos criterios que H1: ROI > 0, t >= 2, n >= 300, mismo signo en ambas
  mitades. REFUTADA el resto.

## Controles obligatorios
1. **Placebo de orientacion:** repetir H2 con la etiqueta de local asignada
   AL AZAR. Si el placebo iguala a H2, no hay efecto de localia.
2. **Cubo de cuota emparejado:** H2 debe superar al ROI del cubo de cuota
   correspondiente en H1. Si no, lo que mide es sesgo de precio, no localia.
3. Se reporta la cuota media y el n de cada celda; una celda que solo vive
   en cuotas >5.00 se declara sospechosa de ruido de cola.

## Compromiso
Si H1 y H2 salen refutadas, no se buscan subgrupos, ni otro umbral de cuota,
ni otra ventana de fechas para rescatarlas. La contaminacion declarada en la
ENMIENDA 2 de situacionales (la pista de +13.8% en la fila que resulto ser
la H1 verdadera de altitud) NO se usa aqui: la altitud no se testea en este
pre-registro precisamente por estar contaminada.

## RESULTADO (2026-09-03, corrido tal cual)
5.510 partidos con moneyline de apertura en casa legal; corte 2026-01-16.

### H1 -- REFUTADA. Y es el sesgo favorito-longshot de manual.
| cuota | n | ROI | t |
|---|---|---|---|
| 1.01-1.20 | 1621 | -1.94% | -2.44 |
| 1.20-1.40 | 1152 | -1.52% | -0.94 |
| 1.40-1.70 | 1581 | -3.34% | -1.79 |
| 1.70-2.20 | 2017 | -4.33% | -2.04 |
| 2.20-3.00 | 1681 | -4.08% | -1.37 |
| 3.00-5.00 | 1301 | **-11.93%** | -2.71 |
| 5.00-20.0 | 1414 | **-23.02%** | -3.53 |

Ningun cubo es rentable y el deterioro es monotono con la cuota. Es el
sesgo favorito-longshot clasico, y de los grandes: el margen efectivo pasa
del 2% en cuotas cortas al 23% en las largas. **No es explotable** (para
cobrarlo habria que LAYAR, y no hay exchange legal en España), pero deja una
regla negativa solida y bien medida: en NCAAB, ninguna cuota por encima de
3.00 merece dinero, jamas.

### H2 -- REFUTADA, con un dato util dentro.
Local real NO favorito: n=1151, ROI **-10.63%**, t=-2.58, y cambia de signo
entre mitades (-16.1% / -5.6%).
Placebo con localia AL AZAR (3 semillas): -19.35%, -18.95%, -20.20%.

**La localia es real:** el REAL bate al placebo por ~9 puntos de ROI, asi
que saber quien juega en casa vale dinero de verdad. Lo que no alcanza es a
superar el precio: el local no-favorito cotiza en cuotas largas, y ahi el
margen de la casa (H1) se come la ventaja entera. El mercado de NCAAB
**si** paga la localia; lo que no perdona es el precio del no-favorito.

**Veredicto: las dos REFUTADAS.** Sin rescates por subgrupos, tal como se
comprometio. El frente de moneyline pre-partido en NCAAB queda cerrado.
