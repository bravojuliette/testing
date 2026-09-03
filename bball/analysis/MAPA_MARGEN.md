# MAPA DE MARGEN — cuanto cobra cada casa, y por tanto cuanto hay que batir

Medicion pura (2026-09-03): overround = 1/cuota_A + 1/cuota_B - 1 sobre las
cuotas reales de las casas legales en España. NO calcula ningun ROI, asi que
no necesita pre-registro. Sirve para dirigir la busqueda con un numero en vez
de con una corazonada.

| mercado | margen (mediana) |
|---|---|
| **Bet365 moneyline** | **4.18% (WNBA) - 4.27% (NBA)** |
| Bet365 totales | 4.77% (identico en las 4 ligas) |
| Betway moneyline | 5.59-5.62% |
| Betway totales | 5.86% |
| BWin moneyline | 5.65-7.03% |
| BWin totales | 6.11-6.95% |

El margen es notablemente ESTABLE por casa y mercado, no por liga: Bet365
cobra lo mismo en NCAAB que en NBA. La liga no cambia el precio; la casa si.

## LA BARRERA: 4.2 puntos
Cualquier sistema debe encontrar mas de **4.2 puntos** de ventaja real para
dar dinero en la casa mas barata. Ese es el listón economico, y es un numero,
no una opinion.

## Donde estamos respecto a esa barrera (medido, no estimado)
| medicion | valor | lectura |
|---|---|---|
| line shopping (mejor vs peor precio) | 8.4 pts | la mayor palanca medida, pero ver abajo |
| localia real (vs placebo) | 9 pts | ya esta en el precio |
| movimiento de linea (seguir vs contrariar) | 7 pts | ya esta en el precio |
| descanso / back-to-back (vs placebo) | ~0 pts | ni siquiera bate al azar |

**Las señales predictivas medidas valen 7-9 puntos y estan TODAS dentro del
precio.** Buscar mas señales de ese tipo es el camino que ya ha fallado siete
veces. Lo unico que llegaba a rozar el cero era mecanico (coger el mejor
precio), y ese frente esta cerrado desde hoy.

## ACTUALIZACION 2026-09-03: el margen NO es una constante unica, pero casi
Dos precisiones medidas hoy que cambian donde puede vivir un sistema:

**1. El margen de Bet365 no varia entre partidos.** Distribucion del overround
en el moneyline de apertura: p10 3.80%, mediana 4.24%, p90 4.62%. El rango
entero son 0.8 puntos. **No existe un subconjunto de partidos "baratos" que
filtrar**, asi que esa idea queda descartada sin gastar un test. En handicap
(18_2) es todavia mas rigido: p10 4.73%, mediana 4.77%, p90 4.77% -- un precio
fijo. Y Bet365 solo publica UNA linea de total por partido en estos datos
(nada de escalera de lineas alternativas), asi que tampoco hay incoherencias
internas de la propia casa que explotar.

**2. Pero el coste EFECTIVO si varia por cuota, y mucho.** El sesgo
favorito-longshot no reparte el margen por igual entre los dos lados. Coste
real de apostar al favorito en Bet365 (apertura, 4 ligas, n=9.039):

| cuota | n | ROI | t |
|---|---|---|---|
| **1.01-1.10** | 952 | **-1.03%** | -1.29 |
| 1.10-1.20 | 1178 | -3.29% | -2.73 |
| 1.20-1.30 | 1117 | -4.26% | -2.71 |
| 1.30-1.40 | 1066 | -4.42% | -2.36 |
| 1.40-1.60 | 1920 | -4.60% | -2.82 |
| 1.60-2.00 | 2770 | -5.51% | -3.33 |
| 3.00-5.00 (NCAAB) | 1301 | -11.93% | -2.71 |
| 5.00-20.0 (NCAAB) | 1414 | -23.02% | -3.53 |

**La barrera real no es 4.2 puntos en todas partes: es ~1 punto por debajo de
cuota 1.10 y 4-5 puntos a partir de 1.20.** Esa primera fila es la unica
esquina del baloncesto pre-partido donde el precio deja sitio, y son el 10% de
los partidos. (Cuidado: -1.03% con t=-1.29 es indistinguible de cero, no es
"casi rentable"; es "no medible con esta muestra".)

## Consecuencia para donde buscar
1. **El line shopping esta cerrado para España** (ver
   `PREREGISTRO_cuantas_casas.md`). No por falta de cuentas: porque las casas
   españolas son homogeneas. Bet365 da el mejor precio el 67.6% de las veces
   entre las 4 con licencia y cobertura, y sus margenes van de 4.21% (Bet365) a
   9.76% (Interwetten). Sobre los mismos partidos, 4 cuentas españolas dan
   -1.27% y 4 cuentas sharp (no jugables) dan +2.24%: lo que movia la curva no
   era el numero de casas, era CUALES.
2. El -0.45% que este mapa citaba antes como "a medio punto del equilibrio" era
   un artefacto de muestra (n=1.240, solo los partidos donde Bet365 y BWin
   coinciden). Sobre partidos comparables ese par da -1.54%. Corregido.
3. Queda un solo hueco pre-partido acotado: **cuota < 1.10**. Necesita una
   señal de ~2 puntos, y tiene un problema economico propio: a cuota 1.08 se
   arriesgan 100 para ganar 8.

## ACTUALIZACION 2026-09-03 (2): las ligas chicas son MAS CARAS, no mas blandas
Medicion pura de precio sobre la apertura del moneyline en `bball_chicas.db`
(2.741 partidos de ~40 ligas menores, reconstruida desde `bball_odds_hist`):

**margen mediano 7.47%** (p10 6.56%, p90 8.70%) -- casi el DOBLE que el 4.24%
de NBA/NCAAB/WNBA/Euroleague.

| liga | n | margen mediano |
|---|---|---|
| NBA Summer League | 94 | 4.16% |
| Brazil LDB U22 | 51 | 7.08% |
| FIBA World Cup Qualification | 109 | 7.14% |
| U20 European Championship | 117 | 7.28% |
| Chile LNB | 70 | 7.44% |
| Uruguay Liga de Ascenso | 105 | 7.47% |
| Mexico LNBP | 100 | 7.79% |
| Australia NBL1 South | 59 | 7.96% |

La intuicion habitual ("en ligas chicas la casa sabe menos, ahi esta el
dinero") es correcta sobre el CONOCIMIENTO y falsa sobre el PRECIO, y el
precio es lo que se paga: la casa se cubre de su propia ignorancia cobrando
mas. Para ganar dinero en una liga chica no basta con saber mas que Bet365:
hay que saber **7.5 puntos** mas, contra 4.2 en las ligas grandes. Es el sitio
mas dificil, no el mas facil.

Unica excepcion medida: NBA Summer League (4.16%), que Bet365 cotiza como liga
grande. n=94, insuficiente para nada por si solo, pero es la unica puerta de
las chicas que no esta tapiada por el precio.

**Consecuencia: el frente de ligas chicas pre-partido queda descartado por
precio, sin gastar un test de ROI.**

## ACTUALIZACION 2026-09-03 (3): BET365 YA ES DE LAS CASAS MAS BARATAS DEL FEED
Ranking completo de margen en el moneyline, las 27 casas del feed con n>=300
(mediana del overround; ordenado de mas barata a mas cara):

| # | casa | n | p10 | mediana | legal ES |
|---|---|---|---|---|---|
| 1 | PinnacleSports | 18053 | 2.85% | **3.86%** | |
| 2 | Everygame | 17078 | 3.21% | 4.10% | |
| **3** | **Bet365** | 13810 | 3.80% | **4.24%** | **SI** |
| 4 | YSB88 | 15661 | 3.81% | 4.44% | |
| 6 | DraftKings | 8758 | 4.20% | 4.50% | |
| 8 | WilliamHill | 3334 | 3.70% | 4.91% | SI |
| 13 | SBOBET | 17775 | 4.03% | 5.49% | |
| 14 | Betway | 885 | 4.71% | 5.62% | SI |
| 16 | BWin | 8610 | 5.33% | 6.03% | SI |
| 19 | Betsson | 16720 | 4.11% | 7.01% | SI |
| 22 | Interwetten | 19834 | 5.49% | 7.99% | SI |
| 27 | Macauslot | 1422 | 8.33% | 11.81% | |

**Bet365 es la 3a mas barata de 27**, y solo la superan dos casas que no son
legales en España. Esto no es un detalle: es la explicacion estructural de por
que ha fallado TODO lo probado en este proyecto.

El esquema clasico de este negocio es *casa blanda contra referencia sharp*:
se apuesta en una casa cara y lenta usando una barata y rapida como valor
justo. Aqui esa figura **no se puede montar**, y por dos motivos a la vez:

1. **No hay casa blanda que explotar.** La unica casa jugable desde España que
   merece la pena es Bet365, y ya esta en el extremo sharp del mercado. Las
   otras legales (BWin 6.03%, Betsson 7.01%, Interwetten 7.99%) son mas caras,
   asi que apostar en ellas es peor, no mejor.
2. **Casi no hay referencia mas sharp con la que batirla.** Solo Pinnacle
   (3.86%) y Everygame (4.10%) son mas baratas, y la diferencia con Bet365 son
   0.4 y 0.1 puntos. Con un hueco tan pequeño, Bet365 rara vez ofrece precio
   por encima del valor justo de la sharp: medido, **solo en el 23% de los
   partidos** (447 de 1.954, ver `PREREGISTRO_pinnacle_referencia.md`), y eso
   deja el test sin potencia.

**Consecuencia, y es la conclusion mas importante de toda la busqueda:** el
apostante español no se enfrenta a una casa blanda con una referencia sharp
enfrente. Se enfrenta a una de las casas mas eficientes del mercado, sin nada
mejor con lo que compararla. Cualquier sistema pre-partido tendria que salir de
informacion propia sobre baloncesto, no de la estructura del mercado -- y ese
es un liston completamente distinto, mucho mas alto, y del que este proyecto no
tiene ninguna evidencia de estar cerca.
