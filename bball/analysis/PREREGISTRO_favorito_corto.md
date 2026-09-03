# PRE-REGISTRO: el favorito corto, donde el margen casi no existe

Escrito y commiteado el 2026-09-03 ANTES de calcular ningun ROI de este
documento. El timestamp del commit es la prueba.

## Por que aqui, y por que ahora (todo esto ya esta medido, no es corazonada)
Los frentes cerrados dejaron dos numeros que juntos cambian la estrategia:

1. **El margen de Bet365 es practicamente una constante.** Medido hoy sobre
   NCAAB/NBA/WNBA en el moneyline de apertura: p10 = 3.80%, mediana = 4.24%,
   p90 = 4.62%. No hay un subconjunto de partidos "baratos" que filtrar: el
   rango entero son 0.8 puntos. Ese filtro queda descartado sin gastar test.
2. **Pero el coste EFECTIVO no es 4.2 puntos en todos los lados.** El sesgo
   favorito-longshot devuelve casi todo el margen en el lado corto y lo
   concentra en el largo. Ya medido: en NBA/Euro/WNBA el favorito de
   implicita 0.90-0.95 cuesta **-0.2%** (`calibracion_ganador.py`); en NCAAB
   el cubo 1.01-1.20 cuesta **-1.94%** y el 3.00-5.00 cuesta -11.9%
   (`PREREGISTRO_ncaa_prepartido.md`).

De ahi el cambio de planteamiento que motiva este pre-registro. Hasta hoy
buscabamos una señal que batiera 4.2 puntos, y **ninguna señal medida en este
proyecto llega a eso** (line shopping 8.4 pts, localia 9 pts, movimiento de
linea 7 pts: todas dentro del precio, ver `MAPA_MARGEN.md`). En el favorito
corto la barrera no es 4.2: es **1-2 puntos**. Una señal mediocre, que seria
inutil en cualquier otro lado, ahi puede cruzar el cero.

Esto no es un rescate por subgrupo: el subgrupo esta elegido por una razon
estructural medida de antemano (donde vive el margen), no por su ROI.

## Universo (fijado aqui)
- Casa: **Bet365 unicamente** (legal en España, la mas barata de las 4 con
  licencia y la que da el mejor precio el 67.6% de las veces entre ellas --
  ver `PREREGISTRO_cuantas_casas.md`). Sin line shopping: ese frente esta
  cerrado.
- Mercado: moneyline (18_1), partidos completados, sin empates.
- **FAVORITO CORTO = cuota Bet365 < 1.40.** El umbral se fija AQUI. Escalera
  declarada para dosis-respuesta: <1.20, <1.30, <1.40, <1.55.
- Ligas: NBA, NCAAB, WNBA, Euroleague. El bloque primario es el **POOLED**
  (por potencia); el desglose por liga se reporta siempre, pero una liga
  suelta NO rescata un pooled refutado.
- Orientacion local/visitante: en NBA/WNBA/Euroleague el par de Bet365 esta
  verificado hoy (local gana 55.0/53.9/62.8%, favorito acierta 67.7/69.1/
  63.1%). En NCAAB se aplica `orientacion.py` y los partidos 'swap' se
  corrigen **reetiquetando el slot, JAMAS intercambiando el marcador** (esa
  confusion fabrico un +25% falso; queda como aviso permanente).

## H1 -- DESCANSO. El favorito corto descansado contra el rival cansado.
Mecanismo: la fatiga de calendario es real y medible, y la casa solo puede
precificarla a medias porque mover la linea de un favorito muy corto es caro
en un mercado de dos vias. No exige saber mas de baloncesto: exige que un
dato publico del calendario no este entero en el precio.

- Descanso de un equipo = dias desde su partido anterior (de `bball_games`,
  solo fechas: ni cuotas ni resultados). Back-to-back = 1 dia.
- Diferencial D = descanso(favorito) - descanso(underdog), truncado a [-3,3].
- Celda principal declarada: **D >= 2** (favorito claramente mas fresco).
  Celda de contraste: **D <= -2**. Se apuesta al favorito a la cuota de
  APERTURA de Bet365.
- Dosis-respuesta declarada: el ROI debe ser monotono no decreciente en D
  sobre {-2,-1,0,+1,+2}. Si el ROI de D>=2 es positivo pero el de D<=-2 es
  aun mejor, el mecanismo esta refutado aunque la celda sea rentable.
- **PLACEBO obligatorio:** se recalcula todo con los descansos REASIGNADOS AL
  AZAR entre partidos (3 semillas fijadas: 1, 2, 3). Si el placebo iguala o
  supera al real, es reversion a la media y se declara REFUTADA aunque el
  real sea rentable.

## H2 -- MOVIMIENTO. Seguir o contrariar al mercado en el favorito corto.
Mecanismo: el movimiento de apertura a kickoff es informacion agregada. En
totales ya salio refutado; en el favorito corto no se ha probado, y es donde
el margen deja sitio.

- Solo partidos con apertura Y kickoff de Bet365 (n disponible: 1840 favoritos
  cortos pooled). Movimiento M = cuota_apertura - cuota_kickoff del favorito
  (M > 0 = se acorto, el mercado fue hacia el).
- **Se apuesta a la cuota de KICKOFF**, nunca a la de apertura: la señal solo
  se conoce despues de que ocurra el movimiento, y apostar al precio viejo
  seria cobrar un precio que ya no existia. Este es exactamente el artefacto
  que mato `PREREGISTRO_outlier_consenso.md` y no se va a repetir.
- Dos patas declaradas: SEGUIR (apostar al favorito si M > 0) y CONTRARIAR
  (apostar al underdog si M > 0). Umbral primario |M| >= 0.02; escalera 0.05.

## Criterios de decision (los de siempre, sin excepciones)
- **CONFIRMADA** una celda: ROI > 0 **y** t >= 2 **y** n >= 300, **mismo
  signo en busqueda y reserva** (corte por la mediana de fecha del pooled),
  dosis-respuesta no invertida y, en H1, placebo peor que el real.
- **NO CONCLUYENTE**: n < 300.
- **REFUTADA**: todo lo demas, incluido ROI positivo con t < 2.
- Nada de rescates por subgrupos no declarados aqui. Las celdas, umbrales,
  ligas y semillas de este documento son la lista completa.

## Aviso economico declarado de antemano
Aun CONFIRMADA, un ROI de +1 o +2% en el favorito corto es fragil: la
varianza por apuesta a cuota 1.25 es alta en relacion al margen, hacen falta
miles de apuestas para distinguirlo de cero, y Bet365 limita cuentas que
ganan. Se reportara el drawdown esperado junto al ROI, no solo el ROI.

---

## RESULTADO (2026-09-03, corrido tal cual). H1 y H2 REFUTADAS.
9.039 partidos con moneyline de apertura de Bet365 en las 4 ligas; 4.349
favoritos cortos (<1.40). Reproducible: `python3 bball/analysis/favorito_corto.py`

### H1 (descanso) -- REFUTADA por tres motivos independientes
| D = descanso(fav) − descanso(dog) | n | ROI | t |
|---|---|---|---|
| D <= -2 (favorito MAS cansado) | 422 | **-0.86%** | -0.40 |
| D = -1 | 638 | -7.48% | -3.76 |
| D = 0 | 2014 | -3.70% | -3.46 |
| D = +1 | 736 | -1.41% | -0.83 |
| **D >= +2 (celda principal)** | 450 | **-2.72%** | -1.27 |

1. **La celda principal pierde** (-2.72%, t=-1.27): no cruza el cero.
2. **La dosis-respuesta esta INVERTIDA**, que era criterio explicito de
   refutacion: la celda de contraste D<=-2 (-0.86%) es MEJOR que la celda del
   mecanismo D>=+2 (-2.72%). El favorito mas cansado sale mejor parado que el
   mas fresco. Sea lo que sea, no es fatiga.
3. **El placebo la iguala.** Descansos reasignados al azar: -1.80% (semilla 1),
   -6.34% (2), -5.05% (3). La semilla 1 BATE al real. La dispersion del placebo
   (4.5 puntos entre semillas con el mismo n=450) mide exactamente cuanto ruido
   hay aqui: mas que cualquier efecto que estuvieramos buscando.

Ni por liga (NCAA n=293: -1.79%) ni por umbral de cuota (<1.20: -3.13%;
<1.30: -1.79%) aparece nada. Sin rescates, como se comprometio.

### H2 (movimiento) -- REFUTADA, y las dos patas a la vez
1.894 favoritos cortos con apertura y kickoff, apostando a la cuota de kickoff:

| pata (umbral 0.02) | n | ROI | t |
|---|---|---|---|
| SEGUIR (el fav se acorto -> al fav) | 790 | -4.06% | -2.25 |
| CONTRARIAR (se acorto -> al dog) | 790 | -8.03% | -1.20 |
| el fav se alargo -> al fav | 430 | -4.23% | -1.71 |

Con umbral 0.05, SEGUIR mejora a -1.31% (n=451, t=-0.54) pero sigue sin cruzar
el cero, y CONTRARIAR se hunde a -14.97%. En busqueda/reserva, SEGUIR cambia a
peor (-2.90% / -5.56%). Nada.

### CORRECCION DE LA PREMISA DE ESTE PRE-REGISTRO (lo mas util que sale de aqui)
El documento decia arriba que la barrera en el favorito corto es "1-2 puntos".
**Medido ahora en el mismo dataset y con la misma casa, eso solo es cierto por
debajo de cuota 1.10**, no por debajo de 1.40:

| cuota Bet365 (apertura) | n | ROI del favorito | t |
|---|---|---|---|
| **1.01-1.10** | 952 | **-1.03%** | -1.29 |
| 1.10-1.20 | 1178 | -3.29% | -2.73 |
| 1.20-1.30 | 1117 | -4.26% | -2.71 |
| 1.30-1.40 | 1066 | -4.42% | -2.36 |
| 1.40-1.60 | 1920 | -4.60% | -2.82 |
| 1.60-2.00 | 2770 | -5.51% | -3.33 |

El -0.2% de `calibracion_ganador.py` era la implicita 0.90-0.95, o sea cuota
1.05-1.11: coincide con la primera fila y con nada mas. El sesgo
favorito-longshot **no** devuelve el margen en todo el lado corto; lo devuelve
en una esquina estrecha. Poner el corte en 1.40 metio en la muestra tres cubos
al -4% que diluyen la esquina barata, y por eso la linea base pooled sale
-3.31%. El error es mio y estaba en el pre-registro; se deja escrito.

**Consecuencia para lo que venga despues:** la unica celda del baloncesto
pre-partido donde el precio deja sitio es **cuota < 1.10, coste ~1 punto**, y
son el 10% de los partidos (952 de 9.039). Cualquier busqueda futura de sistema
pre-partido tiene que vivir ahi o batir 4+ puntos, y lo segundo no lo ha
conseguido nada medido en este proyecto. Ademas esa esquina tiene un problema
economico propio: a cuota 1.08 hay que arriesgar 100 para ganar 8, asi que un
+1% de ROI son ganancias minusculas frente a un drawdown de varias unidades.
