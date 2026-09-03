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
