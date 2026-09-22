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

---

## RESULTADO (2026-09-22, corrido tal cual): REFUTADA
Datos nuevos recolectados hoy: ligas chicas del 1 al 21 de septiembre de 2026
en tres tramos (1.594 partidos, 113 ligas, 1.002 con ML de cierre y entrada
viva de Q1). Reproducible:
`python3 bball/analysis/veredicto_lider_chicas.py --db data_local/bball_chicas_sep.db`

### La puerta declarada SE SUPERA, asi que el criterio decide de verdad
Favorito de cierre gana **67,4%** (exigido 58-78%): PASA. No hay escapatoria
por "muestra rara".

### La celda pre-registrada
| | n | ROI | t | acierto | cuota media |
|---|---|---|---|---|---|
| **lider >= 12, captura ULTIMA (primaria)** | 106 | **-2,66%** | -0,74 | 89% | 1,13 |
| lider >= 12, captura PRIMERA (sensibilidad) | 106 | -2,45% | -0,67 | 89% | 1,13 |
| lider >= 8 (referencia, no decide) | 309 | -1,98% | -0,66 | 83% | 1,24 |

**VEREDICTO: REFUTADA.** ROI negativo y t muy lejos de 2, con n=106 por encima
del minimo de 100, asi que **no** es un "no concluyente por muestra".

Matiz importante para no confundir el motivo: **las dos capturas coinciden**
(-2,66% y -2,45%). Esto NO es una dependencia de captura como la que tumbo la
sobre-reaccion; es sencillamente una celda negativa y estable. (El script
decia "no robusta a captura" en este caso; se corrigio el mensaje, que
inducia a error cuando ambas capturas van en el mismo sentido.)

### Que le paso al +4,3% del origen
El candidato venia de un espejo post-hoc sobre agosto: +4,3% con t=1,93 y
n=304. En septiembre, con el mismo umbral fijo y el mismo procedimiento, sale
-2,66%. La diferencia de 7 puntos entre una muestra y la siguiente, con
t=1,93 en la primera, es exactamente lo que se espera de **ruido que parecia
señal**: por eso el candidato nacio en cuarentena y por eso la confirmacion
se hizo contra datos que no existian cuando se formulo la hipotesis.

La mecanica que lo hacia atractivo (espejo del -45% de la remontada) sigue
siendo cierta en su mitad negativa: comprar remontadas en ligas chicas es
catastrofico. Pero **lo contrario no es automaticamente rentable**: el mercado
cobra bien al lider, y a cuota media 1,13 hace falta acertar el 88,5% para
empatar. Se acerto el 89%... y aun asi el ROI sale negativo, porque el margen
se come ese margen de sobra.

**El ultimo candidato positivo del proyecto queda cerrado.** No quedan
hipotesis en cuarentena salvo el hueco de bwin (confirmacion el 1-oct).
