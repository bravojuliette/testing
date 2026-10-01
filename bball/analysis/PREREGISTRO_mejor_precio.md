# PRE-REGISTRO: MEJOR PRECIO entre casas legales (NCAAB, pre-partido)

Escrito el 2026-09-03 ANTES de calcular ningun ROI de esta hipotesis.

## Por que esta y no otra: la señala mi propia medicion, no una corazonada
De los dos frentes ya refutados hoy queda un hecho: el margen de NCAAB es de
solo **~1.9% en cuotas cortas** (cubo 1.01-1.20) y el cubo 1.20-1.40 dio
-1.52% con t=-0.94, indistinguible de cero. Y la mirada previa DECLARADA
(solo disponibilidad y dispersion, ningun ROI) da:

- 2.849 partidos con **>=2 casas legales** cotizando moneyline de apertura.
  Con las 3 a la vez: **0**.
- Dispersion de cuota entre casas para el MISMO lado: mediana **7.54%**,
  p75 15.79%, p90 29.55%. En cuotas <1.40: mediana 3.58%, p90 11.94%.

Una dispersion mediana del 7.5% es MAYOR que el margen. Si esa dispersion
fuera elegible, coger el mejor precio cambiaria el signo. Eso es line
shopping, que es como gana dinero un profesional: sin predecir nada.

## H1 -- MEJOR PRECIO
Por evento con >=2 casas legales (Bet365/Betway/BWin) cotizando moneyline de
apertura, para cada lado se toma la MEJOR cuota disponible y se respalda ese
lado. Se reporta por cubos de cuota (los mismos de
PREREGISTRO_ncaa_prepartido.md) y en conjunto.
- CONFIRMADA: ROI > 0, t >= 2, n >= 300, mismo signo en busqueda y reserva.
- REFUTADA el resto. NO CONCLUYENTE si n < 300.

## EL CONTROL QUE DECIDE: contemporaneidad de las capturas
Este es exactamente el artefacto que mato el barrido de agosto: si la
"apertura" de una casa es de 40h antes del partido y la de la otra de 3h,
el maximo de las dos NO es un precio que pudieras elegir en ningun momento;
es un maximo sobre el TIEMPO, no sobre el mercado.
- Se reporta la diferencia de `captured_at` entre las dos casas (mediana y
  p90) ANTES de leer ningun ROI.
- Se repite H1 exigiendo que las capturas disten <= 3600s y <= 600s.
- **Si el ROI solo es positivo con capturas separadas y se cae al exigirlas
  contemporaneas, es ARTEFACTO y se declara REFUTADA**, por bonito que sea
  el numero grande.

## Controles adicionales
1. **Peor precio:** el mismo test tomando la PEOR cuota. La diferencia
   mejor-peor mide cuanto vale el line shopping; si mejor y peor salen los
   dos positivos, hay un error de contabilidad y se anula.
2. **Casa unica:** ROI de cada casa por separado sobre la misma muestra, para
   ver si el efecto es de "elegir" o simplemente de que una casa paga mas.
   Si una sola casa ya es positiva, entonces no es line shopping: es esa
   casa, y hay que preguntarse por que (y sospechar).

## Compromiso
Si sale refutada, se cierra tambien este frente y NO se prueba con otras
combinaciones de casas, otros mercados ni otras ligas para rescatarla.

## RESULTADO (2026-09-03, corrido tal cual)
2.719 partidos con >=2 casas legales; corte 2026-01-17.

### El control de contemporaneidad, leido ANTES del ROI
Diferencia de captura entre las dos casas: **mediana 19.4 HORAS**, p90 25.4h,
max 88h. Partidos con capturas a <=3600s: **3**. A <=600s: **0**.
Es decir: el "mejor precio" de esta muestra es un maximo sobre el TIEMPO, no
sobre el mercado. Con contemporaneidad exigida quedan n=6 apuestas: nada.

### H1 -- REFUTADA (y ni siquiera hace falta el control)
| celda | n | ROI | t |
|---|---|---|---|
| MEJOR precio, todo | 5393 | -3.66% | -2.02 |
| MEJOR, cuota 1.01-1.40 | 1240 | -0.45% | -0.36 |
| MEJOR, cuota 1.40-2.20 | 1790 | -1.27% | -0.62 |
| MEJOR, cuota 2.20-3.00 | 930 | +0.14% | +0.03 |
| MEJOR, cuota 3.00-20.0 | 1430 | -11.71% | -2.07 |

Ninguna celda pasa el liston: la mejor (2.20-3.00) da +0.14% con t=0.03, que
es ruido puro, y cambia de signo entre mitades.

### Y el argumento que cierra el frente del todo
El maximo sobre 19 horas es una **COTA SUPERIOR** de lo que daria el line
shopping real: cuanto mas ancha la ventana temporal, mas dispersion hay que
exprimir. Un maximo verdaderamente simultaneo solo puede ser IGUAL O PEOR.
Como la cota superior ya es -3.66%, el line shopping entre Bet365 y BWin en
el moneyline de NCAAB **no puede ser rentable**. No es "no concluyente por
falta de capturas simultaneas": es imposible, y no hace falta recolectar
nada para saberlo.

### Lo que si queda medido, y es el mayor efecto del proyecto
MEJOR precio -3.66% frente a PEOR precio -12.05%: **el line shopping vale
8.4 puntos de ROI**. Es la mayor palanca medida en todo el trabajo, mayor
que la localia (9 pts) o el movimiento de linea (7 pts). Por casas sueltas:
Bet365 -6.92%, BWin -8.79%.
No alcanza aqui porque el margen base es demasiado grueso, pero fija el sitio
donde mirar: **mercados donde el margen base sea fino**, no mercados donde
creamos saber mas que la casa.

**Veredicto: REFUTADA.** Frente cerrado, sin probar otras combinaciones de
casas, mercados ni ligas, tal como se comprometio.
