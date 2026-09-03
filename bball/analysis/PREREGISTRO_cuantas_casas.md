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
