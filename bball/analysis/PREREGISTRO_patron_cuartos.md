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
