# PRE-REGISTRO: LEAD-LAG entre casas (quién mueve primero, quién copia)

Commiteado el 2026-08-31, **a ciegas**: las lecturas de Turso están
bloqueadas por cuota, así que `bball_live_snapshots` -- la única tabla del
proyecto con series por CASA y timestamp propio -- no se puede leer todavía.
Este documento y el código quedan fijados ANTES de ver un solo dato. Es el
caso ideal del método: no hay forma de que el criterio se contamine.

## Por qué esta teoría, y por qué ahora
El test `outlier_consenso` (hoy) produjo +13-18% con t=6 y resultó ser un
ARTEFACTO de snapshots viejos. Pero su control de frescura dejó un residuo
informativo: con líneas frescas, apostar CONTRA la casa que se desvía
pierde -25/-30% en Euroliga. Traducción: **la casa que se mueve primero
suele tener razón**. Si eso es cierto, el dinero no está en corregir a la
desviada — está en copiar a la que lidera, en las casas que aún no han
reaccionado. Es el mecanismo clásico del profesional y no requiere predecir
baloncesto.

## Por qué NO se puede testear con los datos históricos (medido hoy)
- `bball_odds_hist` (serie con `add_time`) NO tiene columna `book`: es
  fuente única (Bet365 por defecto de BetsAPI). Sin dimensión de casa no
  hay lead-lag posible.
- `bball_odds` (multi-casa) solo tiene 3 snapshots por casa
  (start/kickoff/end) y **no están sincronizados**: la dispersión de
  `captured_at` DENTRO de una misma etiqueta es de mediana 1933 min (32h)
  en 'start', 1317 min (22h) en 'kickoff' y 374 min (6h) en 'end'. Comparar
  casas dentro de un snapshot es exactamente el artefacto que ya nos mordió.
- `bball_live_snapshots` (scanner en vivo) SÍ sirve: una fila por
  (evento, pasada, casa) con `captured_at` propio y marcador `ss`. Es la
  tabla que este test usa, y solo esa.

## Medidor descriptivo (parte 1, sin apostar nada)
Para cada (evento, casa) se reconstruye la serie de líneas por pasada.
- MOVIMIENTO = cambio de `line` de una casa entre dos pasadas consecutivas.
- EVENTO DE CONSENSO = una mayoría de casas (>=60% de las que cotizan ese
  partido) mueve su línea en la misma dirección dentro de una ventana de
  600s.
- Para cada evento de consenso: quién movió PRIMERO y cuántos segundos
  tardó cada una de las demás.
- Salida: ranking de casas por (a) veces que lideran, (b) retraso mediano
  cuando no lideran. Puramente descriptivo.

## Test apostable (parte 2)
OPORTUNIDAD: en la pasada t, una casa LÍDER (definida SOLO con la mitad de
búsqueda, nunca con la de reserva) ya movió su línea a L_new, y una casa
REZAGADA sigue mostrando L_old con |L_new - L_old| >= UMBRAL.
Apuesta: en la rezagada, en la dirección del movimiento del líder
(líder sube la línea -> OVER en la rezagada; baja -> UNDER), a las cuotas
de la rezagada en ESA pasada. Liquidación contra el total final del partido.
Umbral primario: 1.5 puntos. Escalera declarada: 1.5 / 2.5 / 4.

## Guardas de realismo (declaradas ahora, no después)
1. **Frescura**: la fila de la rezagada debe venir de la MISMA pasada del
   scanner que la del líder (mismo `captured_at`). Sin esto repetiríamos
   el artefacto de `outlier_consenso` literalmente.
2. **Regla ZOMBI** (norma del proyecto, ya fijada en `live/q1.py`): una
   casa cuya línea no cambia >= 2 veces dentro de ese partido no cuenta
   como rezagada -- una cuota congelada no es un precio apostable.
3. Cuotas en [1.01, 20]; push (total final == línea) excluido.
4. Una apuesta por (evento, casa rezagada, dirección): sin repetir la misma
   oportunidad en pasadas consecutivas mientras el hueco siga abierto.

## Enmienda 1 (2026-08-31, ANTES de ver dato real: descubierta validando
## el codigo contra fixtures sinteticas)

Al probar el medidor contra una base sintetica NULA (casas que mueven con
lead-lag pero cuya direccion NO predice el total final), el test daba
**+3.9%**. Motivo: tal como estaba escrito, mezcla dos efectos distintos:
1. "el lider esta informado" (lead-lag, lo que buscamos), y
2. "la linea rezagada esta lejos del centro y revierte" (reversion a la
   media, que NO es informacion y en un mercado real ya esta cobrada).

Se añade por tanto un CONTROL PLACEBO obligatorio: repetir el test exacto
asignando el papel de "lider" AL AZAR entre las casas activas. Validado
contra ambas fixtures:
- fixture CON señal: REAL +23.7% (t=9.7) vs PLACEBO +10.1% (t=3.6) -> el
  real supera claramente al placebo: hay lead-lag de verdad.
- fixture NULA: REAL +3.9% (t=1.5) vs PLACEBO +8.9% (t=3.1) -> el real NO
  supera al placebo: correctamente declarado "sin lead-lag".

## Enmienda 2 (2026-08-31, ANTES de ver dato real): SOLO FOTOS PRE-PARTIDO

El usuario desconfió de las "dispersiones de ~20 puntos entre casas en vivo"
que yo había citado como materia prima de esta teoría. Tenía razón, y era un
fallo de recolección, no una discrepancia real entre casas.

**Causa (en `bball/live/q1.py`)**: en un partido EN JUEGO el scanner toma la
línea viva del endpoint de historial (casa sintética `__hist__`), pero para
TODAS las demás casas usa el campo `end` del endpoint de RESUMEN, que **no se
refresca durante el partido** — limitación ya documentada en ese mismo
archivo el 2026-08-30 y olvidada al interpretar las fotos.

**Prueba (logs del run 33423107614, 31-ago):** siguiendo un mismo partido
pasada a pasada, el mínimo del rango queda CONGELADO mientras el marcador
avanza:
- evento 12179345: mínimo fijo en **157.0** durante 4 pasadas (35 min)
  mientras el marcador va de 118 a 165 puntos; la mediana sí se mueve
  (167.8 → 171.5 → 171.5 → 173.0).
- evento 13047658: mínimo fijo en **145.5** de 18 a 81 puntos (y 145.5 encaja
  con los totales PRE-PARTIDO de esa liga: partidos hermanos en 144.5 y 147.0).
- evento 12179331: mínimo fijo en **173.5** de 47 a 131 puntos.

Es decir: la "dispersión en vivo" era la línea viva comparada contra líneas de
apertura congeladas. Tercera aparición hoy de la misma enfermedad (precios
viejos disfrazados de actuales), tras el artefacto de `outlier_consenso`.

**Corrección declarada**: el test se restringe a las fotos PRE-PARTIDO
(`ss` vacío), donde el resumen SÍ refresca entre pasadas — verificado en los
mismos logs (evento 12336445: mediana 174.2 → 174.0 → 174.4 → 174.5 → 176.2
→ 176.5, con el rango cambiando de casa en casa). Las filas de casa en juego
quedan EXCLUIDAS por inservibles. Esto convierte el test en lead-lag
PRE-PARTIDO (escala de minutos-horas), no en vivo (escala de segundos): sigue
siendo el mecanismo clásico del sector, pero hay que llamarlo por su nombre.

Re-validado con las fixtures regeneradas como pre-partido: CON señal REAL
+23.7% (t=9.7) vs PLACEBO +10.1%; NULA REAL +3.9% vs PLACEBO +8.9%. El
instrumento sigue discriminando.

**Pendiente aparte (no bloquea este test)**: medir lead-lag EN VIVO exigiría
cambiar la recolección para traer la serie histórica por casa, no el resumen.
Queda anotado como limitación conocida, no como algo ya resuelto.

## Criterios (los de siempre, MAS el placebo)
- CONFIRMADA: ROI > 0, t >= 2, n >= 100, mismo signo en búsqueda y reserva
  (split por fecha), dosis-respuesta no invertida en la escalera de umbral,
  **y ROI del test REAL claramente superior al del PLACEBO** (si el placebo
  iguala al real, es reversion a la media y se declara REFUTADA aunque el
  ROI sea positivo).
- NO CONCLUYENTE: n < 100 (probable al principio: el scanner lleva poco).
- REFUTADA: el resto. La identidad de las casas líderes se fija con la
  mitad de búsqueda; si en reserva el líder es otro, eso YA es un fallo
  del mecanismo y se reporta como tal.

## Aviso económico anticipado
Aunque confirme: esto exige cuenta en la casa rezagada, estar mirando en
ese minuto, y que la casa no limite. El scanner puede detectarlo, pero la
ejecución es manual y con ventana de segundos a minutos. No es un sistema
pasivo.

## RESULTADO (2026-09-01, al desbloquearse Turso): NO CONCLUYENTE por falta de potencia

Corrido tal cual, con la ENMIENDA 2 sin relajar (solo fotos PRE-PARTIDO).

**Antes hubo que tapar un agujero:** el volcado de Turso revelo que NINGUNO de
los 126 partidos fotografiados por el scanner tenia fila en bball_games. El
scanner fotografia todas las ligas; `collect` solo baja resultados de las tres
grandes por league_id. Es decir, tres dias de fotos sin un solo marcador con
el que liquidar: el test daba n=0 por eso, no por el mercado. Se anadio
`resultados-fotos` (/v1/event/view, 10 ids por llamada) y quedaron 73 partidos
liquidables.

**Con marcadores, el test SIGUE sin poder concluir, y ahora se sabe por que:**
- 1052 series (partido, casa) pre-partido con resultado, mediana de 16 pasadas.
- Pero mediana de **1 solo cambio de linea por serie**; media 1.20; el **49%
  no cambia NUNCA** en toda la ventana pre-partido.
- Solo el 30% pasa la regla ZOMBI (>=2 cambios) -> quedan 28 de 73 partidos
  con >=3 casas vivas.
- El disparador exige ademas que >=60% de las casas se muevan en la MISMA
  direccion dentro de 600s. Con ~1 cambio por casa repartido en horas, esa
  coincidencia no se da: **0 eventos de consenso detectados, n=0 en las tres
  celdas REAL.**

El PLACEBO si tiene muestra (n=550/288/71) y pierde -5.7% / -10.8% / -19.0%
(t=-1.46/-2.00/-1.78): apostar la linea rezagada hacia una direccion al azar
paga el margen y poco mas. Es un dato de control, no una estrategia.

**Veredicto: NO CONCLUYENTE.** Y no se arregla con mas fotos: el problema es
la RESOLUCION. Una foto cada 10 minutos no puede ver quien se movio primero
cuando cada casa mueve una vez en toda la tarde. Haria falta muestreo de
segundos, que ningun cron de Actions puede dar.

**La via correcta ya existe y esta construida:** `/v2/event/odds?source=` (ver
cosecha-src) devuelve TODOS los cambios reales de cada casa con su propio
add_time, pre-partido incluido -- los sondeos muestran series que abarcan
101.558 minutos, o sea 70 dias antes del partido. Eso sustituye las fotos de
10 minutos por el registro real de cambios, y ademas es retroactivo. Este
frente se retoma ahi, con el pre-registro de PREREGISTRO_lead_lag_vivo.md,
que ya contempla los controles de simetria, placebo, cadencia y gap puro.

Consecuencia operativa: el scanner en vivo queda RETIRADO (rutina de relevo
desactivada el 2026-09-01). No solo era redundante con la cosecha -- llevaba
tres dias produciendo fotos inservibles por falta de marcador, y su resolucion
es insuficiente para lo unico que pretendia medir.
