# PRE-REGISTRO: un modelo propio (Elo) contra el precio de Bet365

Escrito y commiteado el 2026-09-03 ANTES de calcular ningun ROI de este
documento. El timestamp del commit es la prueba.

## Por que este test, y por que es el ULTIMO de su clase
Toda la busqueda hasta ahora ha atacado la ESTRUCTURA DEL MERCADO: comparar
casas entre si (line shopping, outlier contra consenso, Bet365 contra
Pinnacle) o explotar sesgos del precio (favorito-longshot, movimiento de
linea, descanso). Todo ha fallado, y `MAPA_MARGEN.md` explica por que con un
solo dato: **Bet365 es la 3a casa mas barata de las 27 del feed** (4.24%), solo
superada por Pinnacle y Everygame, ninguna legal en España. No hay casa blanda
que explotar ni referencia sharp con la que batirla.

Queda una sola categoria sin probar: **informacion propia sobre baloncesto**.
Es decir, no intentar arbitrar el mercado sino predecir el partido mejor que
el mercado en algun rincon. Es un liston mucho mas alto y este pre-registro lo
dice antes de mirar.

## La idea, y como se junta con lo unico que quedaba vivo
Se combinan los dos hallazgos del dia:
- El modelo da la SEÑAL (donde discrepa del mercado).
- La EJECUCION va donde el precio es mas barato: la esquina de **cuota < 1.10,
  cuyo coste medido es -1.03%** frente al -4.3% del resto y al 4.77% fijo del
  handicap. Una señal mediocre no sirve de nada al 4.77%, pero al 1% si.

## El modelo (TODOS los parametros fijados AQUI, sin busqueda posterior)
Elo clasico, por liga y por separado, recorrido en orden de fecha
(walk-forward estricto: la prediccion de un partido solo usa partidos
ANTERIORES a su fecha; nunca resultados futuros).
- Rating inicial: **1500** para todo equipo nuevo.
- **K = 20**.
- Ventaja de campo: **+100 puntos Elo** al local.
- Probabilidad del local: `p = 1 / (1 + 10^(-(Rh - Ra + 100)/400))`.
- Actualizacion por victoria/derrota (sin margen de victoria: menos piezas
  moviles, menos sitio donde sobreajustar).
- Se exige que **ambos equipos tengan >= 10 partidos previos**; si no, el
  partido no se apuesta.
- Orientacion NCAAB con `orientacion.py`: en 'swap' se reetiqueta el SLOT,
  jamas se intercambia el marcador.

## Procedimiento
1. Probabilidad justa del mercado: de-vig proporcional de la apertura de
   Bet365 (mismo metodo que en `PREREGISTRO_pinnacle_referencia.md`).
2. Ventaja del modelo en cada lado: `e(X) = p_elo(X) * cuota_365(X) - 1`.
3. Se apuesta al lado de mayor ventaja si supera el umbral.
   Umbrales declarados: **e >= 0%, 2%, 5%, 10%**.
4. Bloques declarados: (A) todos los partidos; (B) **solo cuota < 1.10**;
   (C) solo cuota < 1.20. El bloque que motiva el test es el B.

## PUERTA DE SANIDAD (declarada de antemano, y es lo primero que se mira)
Antes de leer ningun ROI se comprueba que el modelo **prediga algo**:
- Acierto del Elo al elegir ganador, contra el 50% de una moneda, con t >= 2.
- Y se reporta al lado el acierto del MERCADO sobre los mismos partidos.

**Si el Elo no bate a la moneda, todo lo de abajo carece de sentido y el
resultado se declara NO CONCLUYENTE por modelo inutil, NO "refutado".**
Confundir "mi modelo es malo" con "el mercado es eficiente" seria la trampa
mas facil de este test, y queda cerrada aqui.

## PLACEBO
Barajar los ratings finales entre equipos (3 semillas: 1, 2, 3) y repetir. Si
el placebo iguala al real, lo que se mide es ruido.

## Criterios de decision
- **CONFIRMADA** una celda: ROI > 0, t >= 2, n >= 300, mismo signo en busqueda
  y reserva (corte por mediana de fecha), escalera de umbrales no invertida y
  placebo peor.
- **NO CONCLUYENTE**: n < 300, o puerta de sanidad no superada.
- **REFUTADA**: el resto, incluido ROI positivo con t < 2.

## EXPECTATIVA DECLARADA ANTES DE MIRAR (para no vender el fracaso ni el exito)
Un Elo construido solo con marcadores y fechas **no sabe** de lesiones,
descansos, rotaciones ni alineaciones, y el mercado si. Lo esperable es que el
mercado gane con claridad y que las celdas donde el Elo "ve ventaja" sean
simplemente donde el Elo se equivoca -- y entonces el ROI sera **peor** cuanto
mayor el umbral, no mejor. Esa escalera invertida es el resultado que espero.

Si sale asi, la conclusion honesta NO sera "no hay sistema posible", sino algo
mas util y mas acotado: **que el listón no esta en el margen sino en la
informacion**, y que para competir haria falta datos que este proyecto no
tiene (lesiones, minutos, alineaciones confirmadas), no mas estadistica sobre
los datos que ya tiene.
