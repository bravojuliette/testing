# PRE-REGISTRO: respaldar al LÍDER de paliza tras el Q1 en ligas chicas

Commiteado el 2026-08-31, con la hipótesis nacida de un ESPEJO POST-HOC
(declarado como tal en veredicto_chicas.py) y por tanto EN CUARENTENA hasta
este veredicto. Los datos que la juzgarán (septiembre 2026) no existen aún.

## Hipótesis
En ligas chicas (todas las ligas reales salvo NBA/WNBA/Euroliga/NCAA, sin
videojuegos ni 3x3), respaldar al equipo que gana por **≥12** tras el Q1,
al ganador (moneyline) en vivo, tiene ROI>0. Evidencia origen: +4.3%
(t=1.93, n=304, cuota media 1.25), positivo en ambas mitades de agosto y
robusto a captura; espejo exacto de la remontada a −45%.

## Procedimiento (idéntico al de origen, fijado ya)
- Datos nuevos: partidos de ligas chicas del 1 al 21 de septiembre de 2026
  (collect-chicas), serie 18_1 con marcador.
- Momento: entradas ML con suma ss == P1, ventana [inicio+8, inicio+80min],
  cuotas [1.01, 30]; captura última entrada, sensibilidad primera.
- Selección: |margen tras Q1| ≥ 12; se respalda al líder (lado del feed,
  inmune a orientación); gana si ese lado gana el partido.
- Puerta del favorito 58-78% en la muestra nueva; si falla, NO CONCLUYENTE.

## Criterio (inamovible)
- CONFIRMADA: ROI > 0 y t ≥ 2 con n ≥ 100, robusto a ambas capturas.
- NO CONCLUYENTE: n < 100.
- REFUTADA: el resto. Sin rescates por subgrupos, umbral fijo en 12.

## Aviso económico ya conocido
Cuota media ~1.25: aun confirmada, es una estrategia de favoritos cortos en
vivo (aciertos ~84%+ necesarios, límites bajos en ligas chicas, y BWin debe
cotizar el mercado en el momento). La confirmación estadística es la
condición necesaria, no la suficiente, para jugarla con dinero.
