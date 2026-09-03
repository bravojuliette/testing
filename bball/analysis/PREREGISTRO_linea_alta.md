# Pre-registro: la linea alta se pasa de frenada (NCAAB)

**Escrito el 2026-08-29, ANTES de que existan los datos de comprobacion.**
La recoleccion de NCAAB va por el 31 de enero de 2026. **Febrero y marzo aun
se estan descargando y no los ha visto nadie.** Ese es el conjunto de
reserva. Este documento se commitea antes de que lleguen.

## De donde sale

Explorando NCAAB de noviembre 2025 a enero 2026 (2669 partidos apostables al
cierre) aparecio esto: cuanto mas alta es la linea de totales, mas se queda
el partido por debajo de ella.

| tramo de linea | n | media (final - linea) |
|---|---|---|
| 130-140 | 418 | +1.08 |
| 140-150 | 993 | +0.99 |
| 150-160 | 814 | +0.73 |
| 160-165 | 221 | +0.50 |
| 165-170 | 116 | **-1.60** |
| 170-175 | 41 | **-4.15** |
| >=175 | 24 | **-4.67** |

Como UNA sola pendiente (regresion de la desviacion contra la linea), por liga:

| liga | n | pendiente | t |
|---|---|---|---|
| **NCAAB** | 2676 | **-0.0805** | **-2.42** |
| NBA | 1679 | -0.0068 | -0.14 |
| WNBA | 925 | -0.1004 | -1.16 |
| Euroliga | 716 | -0.0450 | -0.42 |

Mecanismo propuesto: una linea muy alta lo es porque los dos equipos vienen
anotando mucho en pocos partidos. Parte de eso es ruido y revierte. En un
mercado con dinero listo la casa lo corrige; en uno ignorado, no. Que la NBA
-- el mercado mas liquido -- sea justo la liga con pendiente cero es
coherente con esa historia.

**Motivos para dudar, listados antes de ver la reserva:**

1. Encontre esto mirando ~20 casillas. A t>=2 se espera 1 falso positivo
   cada 20 casillas por puro azar.
2. Mes a mes el filtro de linea>=165 da: nov +22.2%, **dic -19.9%**, ene
   +22.8%. Un mes de tres en contra.
3. La coherencia entre ligas es sugerente, no probatoria: WNBA y Euroliga
   van en el mismo sentido pero ninguna llega a t=2.
4. El umbral 165 lo elegi DESPUES de ver la tabla. Por eso la prueba
   principal es la pendiente, que no depende de ningun umbral.
5. Aunque sea real, el efecto es fino: la pendiente implica ~5 puntos
   porcentuales de acierto en las lineas extremas, que a cuota 1.91 deja un
   ROI de un digito bajo. El margen de NCAAB es del 5.7%, mas gordo que el
   de la NBA. Puede ser cierto y aun asi no dar dinero.

## Hipotesis (dos, en este orden de importancia)

> **H1 (mecanismo, prueba principal).** En los partidos de NCAAB de
> **febrero y marzo de 2026**, la pendiente de la regresion de
> (total final - linea de cierre) contra (linea de cierre) es **negativa**.

Es la prueba principal porque usa TODOS los partidos de la reserva (no una
franja), no depende de ningun umbral elegido a posteriori, y mide el efecto
fisico y no el ROI, que tiene mucha mas varianza.

> **H2 (apostable, secundaria).** Apostar **under** cuando la linea de
> cierre es **>= 165** da ROI positivo en esa misma reserva.

H2 puede fallar aunque H1 acierte: el efecto puede ser real y no llegar para
cubrir el margen. Ese resultado (H1 si, H2 no) se reportara tal cual, como
"efecto real pero no monetizable", NO como exito.

## Procedimiento (fijado de antemano)

- Solo NCAAB, solo partidos con fecha **>= 2026-02-01**.
- Linea y cuota: snapshot `kickoff` (cierre real), **primera casa
  disponible** entre Bet365, Betway, BWin, en ese orden. Sin elegir la mejor.
- H1: minimos cuadrados de (final - linea) sobre (linea), sin recortar
  extremos, sin ponderar, sobre todos los partidos apostables.
- H2: stake plano de 1 unidad, under a la linea principal. Push = 0.
- Sin filtros adicionales, sin mover el umbral de 165, sin barrer peldaños
  alternativos, sin elegir casa ni subperiodo despues de ver nada.

## Criterio de decision (fijado de antemano)

- **H1 CONFIRMADA** si la pendiente es negativa **y** t <= -2.
  REFUTADA en cualquier otro caso. NO CONCLUYENTE si hay menos de 500
  partidos en la reserva.
- **H2 CONFIRMADA** si ROI > 0 **y** t >= 2. REFUTADA en cualquier otro
  caso. NO CONCLUYENTE si hay menos de 100 apuestas.

## Controles (no cambian el veredicto)

- La pendiente por tramos deberia reproducir el gradiente monotono, no solo
  el numero global.
- La franja baja (<130) NO deberia mostrar el efecto invertido con fuerza:
  en busqueda dio +0.50, practicamente nada. Si en la reserva las lineas
  bajas se disparan al alza, el mecanismo de reversion queda reforzado; si
  no aparece, queda como esta.
- Volumen: en busqueda, linea>=165 fue el 6.7% de los partidos (~7 picks al
  dia con el calendario de NCAAB). Se reporta el volumen real de la reserva.

## Compromiso

Si H1 sale refutada, **no se buscan subgrupos, ni otro umbral, ni otra
liga, ni otro periodo** para rescatarla. Si sale confirmada pero H2 no, se
dice que el efecto existe y no da dinero, que es una conclusion distinta de
"funciona".

Precedente en este repo: `PREREGISTRO_wnba_underdogs.md` (refutada, t=-2.10,
y la celda de control con +39.9% NO se investigo) y
`PREREGISTRO_situacionales.md` (las dos hipotesis refutadas, y la casilla
placebo con +13.8% NO se persiguio).
