# VEREDICTO: la busqueda de sistema PRE-PARTIDO, cerrada y con el numero

Consolidado el 2026-09-03. Recoge el estado de todos los frentes pre-partido
probados y, sobre todo, **por que fallan todos**, que es lo unico que se puede
reutilizar. Cada frente tiene su pre-registro con criterios fijados ANTES de
mirar, y el commit que lo prueba.

## Respuesta corta
**No hay sistema rentable pre-partido con los datos de este proyecto.** Y no es
"todavia no lo hemos encontrado": esta medido por que, y el motivo es
estructural, no de esfuerzo.

## Las dos mediciones que lo explican todo

**1. La casa que se puede usar ya es de las mas eficientes del mercado.**
Ranking de margen del moneyline, 27 casas del feed: Bet365 es la **3a mas
barata (4.24%)**, solo superada por Pinnacle (3.86%) y Everygame (4.10%),
ninguna legal en España. Las otras legales son peores: BWin 6.03%, Betsson
7.01%, Interwetten 7.99%.

El esquema clasico del sector -- apostar en casa blanda usando una sharp como
valor justo -- **no se puede montar por ninguno de los dos lados**: no hay casa
blanda jugable que explotar, y casi no hay referencia mas sharp con la que
batirla (0.4 puntos de hueco contra Pinnacle).

**2. El mercado sabe 4,55 puntos mas que un modelo honesto.**
Elo propio, walk-forward, 7.162 partidos: acierta el **63,75%** de los
ganadores (t=+24, o sea que predice de verdad). El mercado acierta el
**68,30%**. Esos 4,55 puntos hay que recuperarlos ANTES de empezar a pagar el
4,2% de margen.

## El mapa de la barrera (medido, no estimado)
| cuota Bet365 (apertura) | n | coste real de apostar al favorito |
|---|---|---|
| 1.01-1.10 | 952 | **-1.03%** |
| 1.10-1.20 | 1178 | -3.29% |
| 1.20-1.40 | 2183 | -4.3% |
| 1.60-2.00 | 2770 | -5.51% |
| 3.00-5.00 | 1301 | -11.93% |
| 5.00-20.0 | 1414 | -23.02% |
| handicap (18_2) | 13871 | 4.77% fijo (p10 4.73, p90 4.77) |
| ligas chicas (moneyline) | 2741 | 7.47% mediano |

La unica esquina barata es **cuota < 1.10**, y el propio test del modelo
descubrio por que no sirve: solo 141 de 6.482 apuestas del modelo caen ahi.
**Donde el precio es barato es justo donde es mas dificil tener razon contra la
casa**, porque el mercado esta muy bien calibrado sobre favoritos claros.

## Frentes cerrados
| frente | veredicto | por que |
|---|---|---|
| Line shopping entre casas legales | DESCARTADO | Casas españolas homogeneas. Bet365 da el mejor precio el 67.6% de las veces. Mismos partidos: 4 cuentas españolas -1.27%, 4 sharp +2.24%. No es cuestion de abrir cuentas |
| Curva ROI(N) con 22 casas | ABIERTO pero inejecutable | Cruza el cero en N~8, pero solo porque muestrea casas no jugables |
| Outlier contra consenso | ARTEFACTO | Solo funciona con snapshots rancios (gap ~20 min) |
| Bet365 contra Pinnacle | REFUTADA (sin potencia) | No bate a una moneda; cambia de signo entre mitades. Solo 447/1954 con ventaja positiva |
| Sesgo favorito-longshot | REFUTADO | Existe y es de manual, pero para cobrarlo habria que layar |
| Localia | REFUTADO | Real bate al placebo por 9 pts: es real y ya esta en el precio |
| Movimiento de linea (totales y ML) | REFUTADO | Ambas patas negativas |
| Descanso / back-to-back | REFUTADO | Dosis-respuesta invertida; el placebo lo bate |
| Filtro por margen del partido | DESCARTADO sin test | El margen no varia (p10 3.80%, p90 4.62%) |
| Lineas alternativas de totales | NO EXISTE | Bet365 publica una sola linea por partido |
| Handicap | DESCARTADO sin test | Precio fijo 4.77% y sin sesgo que devuelva nada |
| Ligas chicas | DESCARTADO por precio | 7.47% de margen: el sitio mas caro, no el mas blando |
| Modelo propio (Elo) | REFUTADO | Escalera invertida; el placebo lo iguala |

## Que cambiaria la respuesta (y que no)
**NO la cambia:** mas estadistica sobre estos mismos datos. Se han probado 13
frentes con pre-registro; el patron esta establecido y seguir probando
variantes sobre el mismo dataset solo aumenta la probabilidad de un falso
positivo.

**SI podria cambiarla:**
1. **Datos que la casa tiene y nosotros no**: lesiones, minutos, rotaciones,
   alineaciones confirmadas. Ahi estan los 4,55 puntos de acierto que faltan.
   Es la unica via medida que ataca el problema real.
2. **Cosecha emparejada al segundo** (`bet365` + `betfair` via
   `/v2/event/odds`, que trae `add_time` real). Daria potencia al test de
   referencia sharp, hoy limitado a 447 apuestas utiles. Ojo: `pinnacle` NO es
   fuente valida de ese endpoint (PARAM_INVALID).
3. **Euroleague**, como direccion y no como sistema: es la unica liga donde el
   modelo propio queda a **0,32 puntos** del mercado (63.09% vs 63.41%) frente
   a 4-9 puntos en las demas. No se ha calculado su ROI a proposito: seria un
   subgrupo no declarado con n=615.

## Lo que NO se ha hecho, y consta
En el camino aparecieron celdas que en otro proyecto se habrian publicado como
sistemas: +242% (bug de orden del par), +13,2% en outlier NBA (precio rancio),
+13,25% en NBA contra Pinnacle (n=136, t=0.85, subgrupo no declarado), +8,28%
en la mitad de busqueda del mismo test. **Ninguna se ha rescatado**, y cada una
queda escrita en su pre-registro para que se vea que se miro y se dejo pasar.
