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
