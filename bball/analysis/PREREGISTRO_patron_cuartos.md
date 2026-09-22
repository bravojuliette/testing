# PRE-REGISTRO: patrón de resultados por cuarto (Q1-Q3) y el ganador del partido

Commiteado el 2026-08-31, antes de correr el test. No hace falta esperar a
datos futuros (a diferencia de `PREREGISTRO_lider_chicas.md`): usa el
histórico ya recolectado de NBA/Euroleague con split búsqueda/reserva por
fecha, el mismo mecanismo anti-mirada-al-pasado que ya usan
`sobre_reaccion_q1.py` y `barrido_vivo.py`.

## Hipótesis del usuario (2026-08-31)
"Si un equipo pierde el Q1 y luego gana el Q2 y el Q3, aunque quede
igualado a puntos, ganará el partido" -- y sospecha específicamente que la
ventaja, si existe, está en apostar por el **underdog** en esta situación
(no por el favorito).

## Hallazgo previo a declarar el procedimiento: BUG-TRAP en las claves del JSON
Antes de programar nada se verificó la estructura de `raw_json.scores` con
muestras al azar de las 3 ligas grandes. Resultado, verificado contra las
columnas `home_score`/`away_score` (que SÍ sé que están ya normalizadas a
home/away real, per el fix de `remontadas_q1.py`):
- clave `"3"` = MARCADOR DE MEDIO TIEMPO acumulado (Q1+Q2), no es el Q3.
- clave `"4"` = Q3 real.
- clave `"5"` = Q4 real.
- clave `"6"` = prórroga, si la hay.
- clave `"7"` = final, coincide con `home_score+away_score` en el 99%+ de
  la muestra (los pocos casos sin clave "3" tenían la prórroga en "6" y
  igual cuadraban sumando 1+2+4+5(+6) = final).

Si se hubiera usado ingenuamente `sc["1"],sc["2"],sc["3"],sc["4"]` como
Q1-Q4, el "Q3" habría sido en realidad el marcador acumulado al descanso y
el "Q4" habría sido el Q3 real -- exactamente el tipo de bug de orientación
que ya mordió a `remontadas_q1.py` una vez. Se documenta el fix aquí para
que no se repita en otro script.

## Procedimiento
- Ligas: NBA y Euroleague (WNBA excluida, mismo motivo que en
  `remontadas_q1.py`: su orden de feed se invierte a mitad de 2026).
- Orientación: `raw_json.scores` viene en orden CRUDO del feed (home/away
  del feed, invertido en ligas AWAY_FIRST); se aplica el mismo flag
  `invertida` que ya usa `remontadas_q1.py` a CADA cuarto, no solo al Q1.
- Por equipo y partido: resultado de Q1/Q2/Q3 = W (anotó más ese cuarto),
  L (menos), o descartado si empate exacto en el cuarto (raro; sin rescate).
- PATRÓN = terna ordenada (Q1,Q2,Q3) de W/L para el equipo foco: 8
  combinaciones posibles.
- Margen tras Q3 = marcador acumulado real (Q1+Q2+Q3, claves 1+2+4) del
  lado del equipo foco.
- Momento de compra: entrada de moneyline en vivo (serie histórica) con
  `suma_ss(ss)` == esa suma acumulada real, ventana [inicio+35min,
  inicio+150min] (más ancha que la de Q1 en `remontadas_q1.py` porque el
  Q3 real cae más tarde en el reloj de pared, con descansos incluidos),
  cuotas ambas en [1.01,30]. Captura PRIMARIA = última entrada del tramo,
  SENSIBILIDAD = primera (regla estándar del proyecto: si el signo cambia
  entre capturas, no hay señal).
- Puerta de validación: favorito de cierre gana 58-78% en la muestra usada
  (mismo gate que `remontadas_q1.py`); si falla, veredicto abortado en esa
  liga.
- Favorito/underdog: se clasifica según la cuota de cierre del equipo foco
  (favorito = cuota de cierre menor que la del rival).

## Test PRIMARIO (la hipótesis exacta del usuario)
Patrón L-W-W, |margen tras Q3| <= 3 (umbral primario) y <= 5 (secundario
informativo) -> comprar el moneyline en vivo de ese equipo. Se reporta
partido en dos: favorito y underdog, porque el usuario sospecha
específicamente que el underdog es donde puede haber ROI.

CRITERIO (el de siempre): CONFIRMADA con ROI > 0, t >= 2, n >= 100,
robusto a ambas capturas, coherente en NBA y Euroliga. NO CONCLUYENTE si
n < 100. REFUTADA el resto. Sin rescates de subgrupo fuera de
favorito/underdog, que está declarado de antemano.

## Test SECUNDARIO (exploratorio, ya que se recorre el espacio)
Barrido de los 8 patrones x 2 buckets de margen tras Q3 (empatado <=5 /
no empatado >5) x liga x favorito/underdog x lado (el equipo del patrón
gana el ML) = 128 celdas. Split búsqueda/reserva por fecha (corte en la
mediana de fechas de cada liga, calculada solo con datos ya existentes,
sin mirar al resultado). Doble filtro ROI>0 y t>=2 en AMBAS mitades,
n>=50 por mitad -- mismo protocolo que `barrido_vivo.py`. Cualquier
superviviente queda en CUARENTENA hasta réplica con datos futuros (no se
apuesta directo aunque sobreviva el doble filtro, por la misma lógica que
ya dejó en cuarentena al candidato de ligas chicas: una celda que
sobrevive un barrido de 128 sigue siendo compatible con azar sin réplica
independiente).

## Compromiso
Si el test primario no confirma (t<2 o n<100) y el secundario no produce
supervivientes del doble filtro, la idea de "patrón de cuartos predice
ganador" queda REFUTADA para NBA/Euroliga con los datos disponibles, sin
rescates adicionales más allá de lo aquí declarado.

## Añadido (2026-08-31, a petición del usuario, declarado ANTES de correrlo): TODOS los puntos de decisión

El barrido original solo compra tras el Q3. Se completa el espacio con los
otros dos momentos de compra:
- **Tras Q1**: patrón de 1 letra (W/L), entrada ML con `suma_ss == P1`,
  ventana [inicio+8min, inicio+80min] (la misma de `remontadas_q1.py`).
- **Tras Q2**: patrón de 2 letras (WW/WL/LW/LL), `suma_ss == P1+P2`,
  ventana [inicio+20min, inicio+110min].
- **Tras Q3**: el ya corrido (8 patrones, ventana [35,150min]).

Mismos estados de margen (empatado ±5 / delante >5 / detrás <-5, medidos
en el punto de compra), mismo fav/underdog por cuota de cierre, mismas dos
ligas. Espacio total: (2+4+8)×3×2×2 = 168 celdas (menos las imposibles:
tras Q1 el patrón y el margen están acoplados). Mismo doble filtro
búsqueda/reserva (mediana de fecha por liga), ROI>0 y t>=2 en AMBAS
mitades con n>=50 por mitad; supervivientes a CUARENTENA, nunca a apostar
directo. Con ~100+ celdas con potencia el azar espera ~2-3 candidatas en
búsqueda y ~0.1-0.3 supervivientes espurios del doble filtro.

## RESULTADO (2026-08-31, corrido tal cual)

Puertas de favorito PASAN en ambas ligas (NBA 63.1%, Euroleague 61.9%);
n=2933 partidos con Q1-Q3 completo y ML vivo capturado tras el Q3.

**Primario (patrón L-W-W del usuario):** REFUTADO en las 4 celdas
declaradas, robusto a ambas capturas. La sospecha específica del usuario
-- ROI del lado underdog -- sale en dirección CONTRARIA: NBA underdog
-12,3%/-11,0% (t=-0,84/-0,94), Euroleague underdog -1,9%/-14,5% (t<1,0).
El favorito con este patrón tampoco muestra nada (t<0,3 en ambas ligas).

**Secundario (barrido de los 8 patrones):** 20/128 celdas con potencia.
1 candidata en búsqueda, exactamente lo que predice el azar (~0,5
esperadas); muere en reserva. 0 supervivientes del doble filtro. Un caso
tentador (NBA/LWL/tied/dog: +47,1% t=+2,36 en RESERVA) no cuenta porque
su búsqueda no pasó el listón (t=+0,63) -- se deja constancia para que
quede claro que no se descartó mirando para otro lado.

**Veredicto: REFUTADA.** Ni el patrón exacto del usuario ni ninguno de
los otros 7 sobrevive el doble filtro en NBA/Euroliga. Frente cerrado.

## RESULTADO del Añadido (2026-08-31, corrido tal cual)

Barrido completo en los 3 puntos de decisión: 110 celdas con n>=30, 50
con potencia (n>=50 por mitad). Candidatas en búsqueda: 1
(NBA/Q3/WWW/delante/fav, +4.1% t=+6.2 en búsqueda) — el azar esperaba
~1.2 — y muere en reserva (-0.2%). **0 SUPERVIVIENTES del doble filtro.**

Notas de la tabla completa (sin rescatar nada, solo para dejar el mapa):
- Tras Q1 y tras Q2 no aparece NADA nuevo: el paisaje es el margen de la
  casa (-2% a -8%) salpicado del desastre ya conocido de comprar
  remontadas (comprar al que va detrás: -20% a -40% por todas partes).
- Las celdas positivas sueltas (NBA/Q2/LL/detras/fav +13.4% t=1.1;
  WL/detras/dog +24-37% t~1 en ambas ligas; LWL/tied/dog +31.8% t=2.05
  solo-en-reserva) tienen todas t<2 en búsqueda: exactamente la cosecha
  que el azar promete con 50 celdas. Ninguna califica ni para cuarentena
  según el criterio declarado (t>=2 en AMBAS mitades).

**Veredicto del añadido: REFUTADO también con todos los puntos de
decisión.** El espacio completo de patrones de cuartos (2+4+8 patrones x
3 estados x fav/dog x 2 ligas x 3 momentos de compra) no contiene ninguna
regla explotable con los datos disponibles. Frente cerrado del todo.
