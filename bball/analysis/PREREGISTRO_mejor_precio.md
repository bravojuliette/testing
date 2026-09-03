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
