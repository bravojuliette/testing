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

## Añadido (2026-08-30, antes de que llegue el dato): REMONTADAS

A petición del usuario, la batería incluye también el test de remontadas de
`remontadas_q1.py` (local / favorito perdiendo ≥8 tras el Q1, comprado al
ganador en vivo; umbral secundario ≥12; robustez primera/última entrada).
Adaptación declarada para ligas chicas:
- Orientación desconocida por liga: se asume orden real (como Euroliga) y
  se valida con la PUERTA del favorito de cierre (58-78%) en el bloque
  pooled y en cada liga con n≥100. Si la puerta falla en pooled, se prueba
  el mapeo invertido; si ninguno la pasa, el test de ganador se ABORTA en
  ese bloque (los totales no se ven afectados).
- Criterios idénticos: ROI>0, t≥2, n≥100, robustez de captura.

## Añadido 2 (2026-08-30, antes de que el dato esté completo): BARRIDO POR COMPETICIÓN

A petición del usuario ("¿y si lo haces solo por competición?"): el barrido
masivo del vivo (barrido_vivo.py, malla gruesa) se corre también sobre las
ligas chicas CON LA COMPETICIÓN COMO DIMENSIÓN (cada liga por separado,
nunca mezclada). Declarado ya:
- Split búsqueda/reserva por fecha DENTRO de los ~60 días (primera mitad /
  segunda mitad del rango).
- Con miles de celdas, el azar garantiza t≈4 en la mejor: solo cuenta el
  doble filtro (ROI>0 y t≥2 en AMBAS mitades, n≥50 por mitad), y cualquier
  superviviente queda en cuarentena hasta réplica en datos posteriores
  (la recolección continua del scanner los irá trayendo).
- Aviso de potencia declarado: una liga de 100-300 partidos solo puede
  revelar ventajas ≥15-20%. Es el tamaño de ventaja que interesa aquí.

## Compromiso

Si el pooled da β≈0 y las patas negativas, la teoría de la línea viva mal
puesta queda refutada TAMBIÉN en ligas chicas y este frente se cierra del
todo — sin rescates por subgrupos más allá de los bloques aquí declarados.
