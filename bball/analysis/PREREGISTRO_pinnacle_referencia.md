# PRE-REGISTRO: Bet365 contra la referencia sharp (Pinnacle), apostando en Bet365

Escrito y commiteado el 2026-09-03 ANTES de calcular ningun ROI de este
documento. El timestamp del commit es la prueba.

## Que es y por que no se ha probado hasta ahora
Es el metodo clasico del sector: una casa sharp (Pinnacle) fija el precio justo;
una casa blanda pero jugable (Bet365) se desvia; se apuesta EN LA BLANDA cuando
su precio supera el valor justo de la sharp. No exige predecir baloncesto. Exige
que Pinnacle tenga razon mas a menudo que Bet365, que es un liston mucho mas
bajo.

Este proyecto ya probo algo que se le PARECE y salio artefacto
(`PREREGISTRO_outlier_consenso.md`), pero era otra cosa: alli se apostaba EN la
casa desviada (rancia, y encima no jugable desde España) hacia el consenso, en
totales. Aqui se apuesta en Bet365, que es la casa que el usuario puede usar de
verdad, en moneyline.

La razon de que no se probara antes es de datos, y hoy se ha medido:
**en la apertura, el desfase de captura entre Bet365 y Pinnacle es de 40.712
segundos de mediana (11,3 horas)**. Comparar aperturas es comparar un precio de
hoy con uno de ayer: exactamente el artefacto que mato el test de outlier. Pero
al KICKOFF el desfase es de **444 segundos de mediana** (p25 175s), y hay 1.970
partidos con desfase <= 600s y 584 con <= 120s. Por primera vez la comparacion
es honesta.

## Universo (fijado aqui)
- Partidos completados, sin empate, con moneyline (18_1) al snapshot **kickoff**
  de Bet365 **y** de PinnacleSports. Ligas: NBA, NCAAB, WNBA, Euroleague.
- Se apuesta **a la cuota de kickoff de Bet365** y solo a esa: es la unica que
  el usuario puede tomar y la unica contemporanea de la señal.
- Orientacion NCAAB via `orientacion.py`; en 'swap' se reetiqueta el SLOT,
  jamas se intercambia el marcador.

## Procedimiento
1. Probabilidad justa de Pinnacle, metodo **proporcional fijado aqui** (sin
   comparar metodos despues): q(X) = (1/o_pin(X)) / (1/o_pin(A) + 1/o_pin(B)).
   Margen medido de Pinnacle: mediana 3.86% (p10 2.85%).
2. Ventaja del lado X en Bet365: **e(X) = q(X) * o_365(X) - 1**.
3. Se apuesta al lado con e(X) mayor, si supera el umbral.
4. Escalera de umbrales declarada: **e >= 0%, 1%, 2%, 3%**. Si el mecanismo es
   real el ROI debe crecer con el umbral, o al menos no invertirse.

## CONTROL DE FRESCURA -- PRIMARIO, no secundario
La leccion del test de outlier se aplica de antemano, no como sensibilidad
posterior:
- **La celda que decide es desfase de captura <= 600 s** (n=1.970 partidos).
- Se reportan tambien <= 120 s (n=584) y sin filtro (n=3.373), pero **la version
  sin filtro NO puede confirmar nada**: si solo funciona con desfases grandes,
  es precio rancio y se declara ARTEFACTO, no ventaja.

## PLACEBOS declarados
1. **Referencia blanda:** repetir todo usando Interwetten (margen 9.76%) como
   referencia en vez de Pinnacle. Si apostar contra el valor justo de una casa
   cara funciona igual de bien, lo que se mide no es la sharpness de Pinnacle
   sino reversion a la media, y se declara REFUTADA.
2. **Lado al azar:** elegir el lado por moneda (3 semillas: 1,2,3) sobre los
   mismos partidos y umbrales. El real debe batirlo claramente.

## Criterios de decision
- **CONFIRMADA** una celda: ROI > 0 **y** t >= 2 **y** n >= 300, mismo signo en
  busqueda y reserva (corte por mediana de fecha), **con el filtro de frescura
  <= 600s aplicado**, escalera no invertida y ambos placebos peores.
- **NO CONCLUYENTE**: n < 300.
- **REFUTADA**: todo lo demas, incluido ROI positivo con t < 2.

## POTENCIA DECLARADA DE ANTEMANO (para no vender un fracaso como veredicto)
Con n = 1.970 apuestas a cuotas en torno a 2.0 (desviacion tipica ~1.0 por
apuesta), el ROI minimo detectable a t=2 es de **~4,5%**. Un metodo de
referencia sharp que funcione de verdad rinde tipicamente 1-3%. Es decir:
**esta muestra puede no tener potencia para verlo aunque exista.**
Por tanto, si sale REFUTADA, lo que se podra decir honestamente es "no hay
efecto lo bastante grande para verse con 1.970 apuestas", NO "el metodo no
funciona". Si sale un ROI positivo pero con t < 2, se declara REFUTADA igual
(el criterio es el criterio) pero se reportara como candidata a repetir con mas
datos, que se pueden cosechar: el endpoint por casa da 22 meses hacia atras.
