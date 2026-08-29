"""Reglas 'de forma' intra-partido (idea del usuario, 2026-08-29):
¿el REPARTO de puntos entre cuartos predice la segunda mitad?

RESULTADO (3318 partidos NBA/WNBA/Euroliga con cuartos y cierre):

benchmark H2 = -0.9 + 0.482*linea + 0.037*H1, sd(residuo) 11.8
  -> el coeficiente de H1 es +0.04: una primera mitad caliente NO anuncia
     una segunda igual; el partido vuelve casi por completo a lo que decia
     la linea. (Coherente con cuartos.py: la reversion manda.)

Residuo medio de la 2a mitad por regla (0 = la casa al descanso ya lo sabe):
  Q1<Q2 (partido subiendo)          +0.28 pts  t=+0.92
  Q1<Q2 por 8+                      +0.61 pts  t=+1.36
  Q1>Q2 (bajando)                   -0.11 pts  t=-0.38
  Q1>Q2 por 8+                      -0.40 pts  t=-0.98
  1a mitad +8 sobre linea/2         +0.14 pts  t=+0.34
  1a mitad -8 bajo linea/2          +0.06 pts  t=+0.14
  igualado al descanso (<=3)        +0.10 pts  t=+0.25
  paliza al descanso (>=15)         +0.58 pts  t=+1.20

Ninguna regla de forma llega a t=2, y las mayores valen ~0.6 puntos sobre
un residuo de sd 11.8: aunque fueran reales, 0.6 puntos no pagan el margen
de un mercado de mitades. La direccion de la regla del usuario es correcta
(subiendo -> +0.28) pero su tamaño es ~20x menor de lo necesario.
"""
