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

---

## CORRECCION (2026-09-03, mismo dia): el RESULTADO de abajo era INVALIDO
Lo que sigue se publico primero como "REFUTADA (sin potencia)" con n=447 y
ROI -2.51%. **Ese numero estaba mal y la conclusion no se sostenia**, por un
bug mio que se descubrio horas despues al investigar otro test.

El bug: este script tomaba el par de Pinnacle (`over_odds`, `under_odds`) como
(local, visitante) **sin alinearlo**. Pero el orden del par cambia por liga: en
NCAAB Pinnacle va INVERTIDA respecto a Bet365 (97,1% de consistencia) y en
NBA/WNBA/Euroliga va alineada. O sea que **todas las probabilidades justas de
Pinnacle en NCAAB estaban del reves**, y con ellas las "ventajas" que
seleccionaban las apuestas. Sintoma que lo delato: el acierto de Pinnacle al
elegir ganador salia 50,79%, cuando alineada correctamente es 68,12%.
Arreglo en `bball/analysis/alineacion.py`.

### RESULTADO CORREGIDO: NO CONCLUYENTE por muestra
Con la alineacion correcta, las ventajas positivas casi desaparecen -- que es
lo esperable: Bet365 (4,24% de margen) rara vez supera el valor justo de una
casa mas barata, y las que antes lo "superaban" en NCAAB eran probabilidades
invertidas.

| celda (gap <= 600s) | n antes (mal) | n ahora | veredicto |
|---|---|---|---|
| e >= 0% | 447 | **261** | n<300 -> NO CONCLUYENTE |
| e >= 1% | 360 | 164 | n<300 |
| e >= 2% | 327 | 123 | n<300 |
| e >= 3% | 292 | 87 | n<300 |

Sin filtro de frescura: -12,50% (n=513). Busqueda/reserva sigue cambiando de
signo (+8,28% / **-22,44%**).

**Por el criterio pre-registrado (n >= 300), la celda que decide se queda en
NO CONCLUYENTE, no en REFUTADA.** La diferencia importa: no se ha demostrado
que el metodo falle, solo que con esta muestra no se puede ver. Lo unico que
sigue en pie sin depender de la potencia es que el cambio de signo entre
mitades no muestra ni rastro de señal estable.

El desglose por liga cae a NBA n=136 (+13,25%), NCAA n=36, WNBA n=23, Euroliga
n=66. **Sigue sin rescatarse nada**: n<300, t<2 y subgrupos no declarados.

Lo de abajo se conserva tal cual se publico, tachado por esta correccion, para
que quede el rastro de lo que se afirmo y por que estaba mal.

---

## RESULTADO ORIGINAL (INVALIDO -- alineacion rota; conservado como registro)

3.321 partidos con Bet365 y Pinnacle al kickoff; 1.954 con desfase <= 600s.
Reproducible: `python3 bball/analysis/pinnacle_referencia.py`

### La celda que decide (gap <= 600s)
| umbral | n | ROI | t |
|---|---|---|---|
| e >= 0% | 447 | **-2.51%** | -0.34 |
| e >= 1% | 360 | -1.26% | -0.15 |
| e >= 2% | 327 | -4.67% | -0.52 |
| e >= 3% | 292 | (n<300) | |

Negativa en todos los umbrales y sin significacion en ninguno. Ademas:

- **Cambia de signo entre busqueda y reserva**, que es criterio explicito de
  refutacion: +8.28% en busqueda (n=125) contra **-6.69% en reserva** (n=322).
  Es justo para lo que existe el corte.
- **El placebo 2 la iguala o la bate.** Elegir el lado a cara o cruz sobre los
  mismos 1.954 partidos da -1.89%, -3.32% y -3.50% segun semilla. El real
  (-2.51%) esta dentro de ese rango: **seleccionar por ventaja contra Pinnacle
  no aporta nada sobre una moneda.**
- Sin filtro de frescura todo se hunde a -9% / -12% (t hasta -2.9), y el
  placebo con Interwetten hace lo mismo (-12% a -15%). Coherente con lo ya
  sabido: comparar precios con 11 horas de desfase no mide ventaja, mide
  ranciedad, y aqui la mide con el signo contrario.

### Lo que NO se va a hacer con esto
El desglose por liga da NBA **+13.25%** (n=136, t=+0.85) y NCAA +6.13% (n=222,
t=+0.58). Es exactamente la clase de celda que en otro proyecto se convertiria
en "sistema NBA con +13% de ROI". Aqui no: n < 300, t < 2, subgrupo no
declarado en el pre-registro. **No se rescata.** Queda escrito para que se vea
que se miro y se dejo pasar.

### Honestidad sobre la potencia (declarada de antemano, y peor de lo previsto)
El pre-registro estimo el ROI minimo detectable en ~4,5% suponiendo n=1.970.
La realidad es peor: **solo 447 de los 1.954 partidos (23%) tienen ventaja
positiva**, porque con un margen del 4.2% Bet365 rara vez supera el valor justo
de Pinnacle. Con n=447 el minimo detectable a t=2 sube a **~9,5%**, y un metodo
de referencia sharp que funcione rinde tipicamente 1-3%.

Por tanto, lo honesto: **REFUTADA por criterio**, pero el resultado tiene poco
contenido informativo. Lo que se puede afirmar es "no hay un efecto de +9,5% o
mas", no "el metodo no funciona". Lo que si queda demostrado con firmeza, y no
depende de la potencia, es que **la seleccion no bate a una moneda** (placebo
2) y que **cambia de signo entre mitades**: no hay ni rastro de señal, solo
falta de muestra para cerrar el caso del todo.

### Como se cerraria de verdad (CORREGIDO tras comprobarlo)
La primera version de esta seccion decia que bastaba con cosechar el historico
de Pinnacle via `/v2/event/odds?source=pinnacle` para emparejar al segundo.
**Es falso y estaba comprobado en el propio repo**: `sources/betsapi.py` deja
escrito desde el 2026-09-01 que **`pinnacle` devuelve PARAM_INVALID** en ese
endpoint. No hay historico de Pinnacle que cosechar. Se corrige aqui en vez de
dejar escrito un plan que no existe.

Lo que si es posible, y probablemente mejor:
- **`betfair`** SI es una fuente valida del endpoint y devuelve serie propia con
  `add_time`. Es un EXCHANGE, o sea la referencia de valor justo mas limpia que
  existe (precio sin margen de casa, solo comision). Como referencia sharp es
  superior a Pinnacle, no un sustituto peor.
- **`sbobet`** tambien es fuente valida, y aparecia en el 8.6% de los mejores
  precios del feed.

El test correcto seria entonces: cosechar `bet365` y `betfair` sobre los mismos
partidos, emparejar por `add_time` con tolerancia de segundos (no de snapshots
capturados por separado) y repetir esta mecanica con Betfair como valor justo.
Eso elimina de raiz el problema de frescura que aqui obliga a tirar el 77% de
la muestra.

**Bloqueo real para hacerlo:** esta sesion no tiene `BETSAPI_TOKEN` en el
entorno, asi que no puede cosechar nada nuevo. Requiere ejecutarlo donde el
token exista (el `.env` local del usuario o el secret de GitHub Actions), con
`python3 -m bball.cli cosecha-src --sources bet365,betfair`. Queda como la
unica accion medida y concreta que puede dar potencia a este frente.
