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
