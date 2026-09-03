# PRE-REGISTRO: ¿cuantas casas hacen falta para cruzar el cero?

Escrito el 2026-09-03 ANTES de calcular estos ROI. Extension declarada de
PREREGISTRO_mejor_precio.md, que dejo el mejor precio de 2 casas legales en
-0.45% (t=-0.36) sobre favoritos cortos -- a medio punto del equilibrio.

## La pregunta
Con las 22 casas del feed (no solo las 3 legales), el mejor precio de N casas
es monotono creciente en N. Se traza la curva ROI(N) para N = 2,3,4,6,8,12,22
sobre NCAAB moneyline de apertura, por cubos de cuota.
- Si la curva cruza el cero en algun N, ese N es el numero de cuentas que
  haria falta, y la pregunta pasa a ser si existen N casas legales en España.
- **Si NO cruza el cero ni con las 22, el line shopping queda descartado
  definitivamente** y no hay que buscar mas casas: no es cuestion de cuentas.

## Por que esto es una COTA SUPERIOR (y por eso decide)
Las capturas de distintas casas distan 19.4h de mediana. El maximo sobre una
ventana ancha solo puede ser IGUAL O MEJOR que un maximo simultaneo real.
Ademas se toma el maximo sobre casas que el usuario no puede usar. Luego:
- curva que no cruza el cero -> el line shopping REAL tampoco lo cruza.
  Conclusion firme, y negativa.
- curva que si cruza -> NO demuestra nada por si sola; solo dice donde
  mirar, y exigiria capturas simultaneas para confirmarlo.

## Criterio
No hay "CONFIRMADA" posible en este test, por lo dicho arriba: es un
descarte. Solo tiene dos salidas: **DESCARTADO** (no cruza) o **ABIERTO con
N** (cruza en N, y queda pendiente de verificacion con capturas simultaneas).
Se exige n >= 300 por celda para leerla.

## HALLAZGO DE INTEGRIDAD encontrado al correrlo (y que invalidaba la primera pasada)
La primera pasada dio numeros absurdos (-80% en cuotas cortas, **+242%** en
largas). No era un hallazgo: **las casas no guardan el par del moneyline en el
mismo orden**. Alineando cada casa contra Bet365 SOLO POR PRECIOS (nunca por
resultados): **16 de 19 casas estan invertidas**, con consistencia del 95-99%
--  es convencion por casa, no ruido. Duelbits 96.9%, CloudBet 97.1%, Coral y
Ladbrokes 99.3%, Pinnacle 97.1%... Alineadas, la sanidad cuadra: el favorito
gana el 70.3% (n=75.766).

Nota: `PREREGISTRO_mejor_precio.md` uso solo Bet365 y BWin, que estan
alineadas entre si (BWin invertida el 4.6%), asi que aquel resultado SI era
sano. Pero cualquier analisis futuro entre casas en este dataset debe alinear
primero o producira ROIs de tres cifras que no existen.

## RESULTADO: ABIERTO con N ~ 4
Mejor precio de N casas, NCAAB moneyline de apertura:

| N | [1.01,1.40) | [1.40,2.20) | [2.20,20) |
|---|---|---|---|
| 1 | -2.91% | -5.68% | -18.93% |
| 2 | -1.59% | -3.59% | -10.63% |
| 3 | -0.48% | -2.22% | -5.60% |
| **4** | **+0.01%** | -1.00% | -3.12% |
| 6 | +0.79% | +0.50% | -0.43% |
| 8 | +1.69% | +0.23% | +4.05% |
| 12 | **+3.06% (t=+2.9)** | +2.42% | +5.83% (t=+2.1) |

La curva es monotona y cruza el cero en **N=4** para cuotas cortas.

**NO es una confirmacion, y el pre-registro lo dejo dicho de antemano:** es
una cota superior (capturas a 19.4h de mediana = maximo sobre el TIEMPO, y
casas que el usuario no puede usar). Lo que hace es convertir la pregunta
"¿hay sistema?" en una pregunta concreta y verificable:

**¿existen 6 o mas casas LEGALES EN ESPAÑA cotizando el mismo partido de
baloncesto, y se pueden capturar sus precios simultaneamente?**

Con las 3 del proyecto (y nunca mas de 2 a la vez en el mismo partido) la
respuesta medida es que no se llega: 2 casas dan -1.59% y 3 dan -0.48%.
