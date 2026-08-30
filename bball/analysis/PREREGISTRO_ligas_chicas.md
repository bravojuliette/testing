# PRE-REGISTRO: sobre-reacción de la línea viva en LIGAS CHICAS

Commiteado el 2026-08-30, **antes de que exista un solo dato**: la
recolección (60 días de todas las ligas reales de basket salvo
NBA/WNBA/Euroliga/NCAA, sin videojuegos ni 3x3) se lanza en este mismo
commit y correrá durante la noche.

## Por qué

El veredicto de las ligas grandes (sobre_reaccion_q1/cortes) fue: línea
viva bien calibrada en Q1/Q2/Q3, ninguna dirección con ROI. Las ligas
chicas quedaron explícitamente fuera y son el único territorio no refutado
de la teoría del usuario: el scanner en vivo midió allí dispersiones entre
casas de 35-84 puntos (mediana 12 en juego), y sus modelos en vivo tienen
menos supervisión.

## Procedimiento (idéntico al de ligas grandes, fijado ya)

Los mismos tests de `sobre_reaccion_q1.py`, con dos adaptaciones declaradas:
1. **Línea de cierre**: primera casa disponible en el orden (Bet365,
   Betway, BWin); si ninguna cotiza, mediana de las casas con snapshot
   kickoff (las ligas chicas tienen menos cobertura de esas tres).
2. **Agrupación**: bloque POOLED de todas las ligas chicas (el test
   principal) + bloques por liga con n≥100 (informativos).

Criterios (los de siempre): β<0 con t≤−2 = sobre-reacción confirmada;
β>0 con t≥2 = sub-reacción; patas apostables CONFIRMADAS solo con ROI>0,
t≥2, n≥100 a cuotas reales. Regla ZOMBI aplicable a cualquier análisis de
dispersión que se derive. El sesgo de anticipación descubierto en Q2/Q3
(última-entrada) obliga a usar la MISMA captura del Q1 original y a
reportar además la versión primera-entrada como control de sensibilidad:
si el signo del resultado depende del extremo elegido, NO hay señal.

## Compromiso

Si el pooled da β≈0 y las patas negativas, la teoría de la línea viva mal
puesta queda refutada TAMBIÉN en ligas chicas y este frente se cierra del
todo — sin rescates por subgrupos más allá de los bloques aquí declarados.
