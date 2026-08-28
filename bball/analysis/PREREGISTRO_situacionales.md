# Pre-registro: factores situacionales de calendario -> OVER

**Escrito el 2026-08-28, ANTES de analizar los datos de NCAAB con los que se
va a comprobar.** En el momento de escribir esto la recoleccion de NCAAB
esta en curso (861 partidos de diciembre 2025, sin `reparse-kickoff`
aplicado todavia) y NO se ha mirado ningun resultado suyo. Este documento
fija las hipotesis, el procedimiento y el criterio de decision para que el
resultado no se pueda reinterpretar despues.

## De donde sale

Sobre los 3021 partidos con cierre real (NBA, WNBA, Euroliga; temporadas
2024-25 y 2025-26), medido en el commit `db588a8`, ANTES de que entrara
ningun partido de NCAAB en la base:

| Estrategia | n | Cuota | Acierto | ROI | t | Beneficio | Peor racha | Drawdown |
|---|---|---|---|---|---|---|---|---|
| Altitud -> over | 101 | 1.91 | 61.0% | +16.1% | 1.75 | +16.3u | 5 | 5.1u |
| Viaje largo -> over | 109 | 1.91 | 61.5% | +17.1% | 1.92 | +18.6u | 4 | 5.4u |
| Las dos juntas | 202 | 1.91 | 60.2% | +14.6% | 2.24 | +29.6u | 7 | 7.1u |

Base fisica medida (desviacion del total final respecto a la linea de
cierre, en puntos):

| Grupo | desviacion media | % over |
|---|---|---|
| Todos los partidos | +0.80 | ~50% |
| Partido en altitud | **+5.54** | 61.0% |
| Visitante en viaje >=4 | **+1.33** | 61.5% |

**Motivos para dudar (por los que se hace este test):**

1. t = 1.75 y t = 1.92 individualmente estan POR DEBAJO del liston de t>=2.
2. El t = 2.24 conjunto sale de juntar dos efectos que ya habia visto por
   separado; juntarlos despues de verlos no es una prediccion, es un ajuste.
3. Altitud es solo NBA: n=101 sobre **dos equipos** (Denver y Utah). Podria
   ser estilo de juego de esas dos plantillas, no la altitud.
4. Llegue a esto mirando los datos. Necesita datos frescos, no los mismos.

## Hipotesis a comprobar (dos, fijadas aqui, sin variantes)

> **H1 (altitud).** Cuando el equipo LOCAL juega en un pabellon a >=1300 m
> de altitud, apostar **over** a la linea principal de cierre da ROI
> positivo.

> **H2 (viaje largo).** Cuando el equipo VISITANTE llega encadenando **>=4
> partidos consecutivos como visitante**, apostar **over** a la linea
> principal de cierre da ROI positivo.

Cada una se juzga por separado con su propio criterio. El conjunto de las
dos se reporta como dato, pero NO puede rescatar a ninguna de las dos: si
H1 y H2 salen refutadas por separado, el conjunto no las salva.

## Datos de comprobacion

Los partidos de **NCAAB** (y WNCAAB si llega a haber volumen) que se estan
recolectando ahora y que no participaron en ningun analisis previo.

NCAAB es un test especialmente exigente para H1: en la NBA la altitud son
dos equipos; en NCAAB hay decenas de universidades de montaña, muchas de
ellas a mas altura que Denver.

## Lista de equipos de altitud (CERRADA AQUI, antes de ver resultados)

Criterio: altitud de la ciudad del pabellon **>= 1300 m** (el suelo de la
pareja NBA que genero la hipotesis: Denver ~1609 m, Salt Lake City ~1300 m).
Altitudes tomadas de la ciudad sede, no del resultado de ningun partido.

**NBA:** DEN Nuggets, UTA Jazz.

**NCAAB — nombres ya presentes en la base:**
Adams State (Alamosa, 2299), Air Force (Colorado Springs, 2073), BYU (Provo,
1387), Colorado (Boulder, 1655), Colorado Christian (Lakewood, 1730),
Colorado Mesa (Grand Junction, 1400), Colorado School of Mines (Golden,
1730), Colorado State Pueblo (1430), Colorado-Colorado Springs (1900),
Denver (1609), Fort Lewis (Durango, 2012), Idaho St (Pocatello, 1370),
Metropolitan State (Denver, 1609), Montana State (Bozeman, 1468), Nevada
(Reno, 1373), New Mexico (Albuquerque, 1580), New Mexico Highlands (Las
Vegas NM, 1950), Northern Arizona (Flagstaff, 2106), Northern Colorado
(Greeley, 1443), Regis (Denver, 1609), Southern Utah (Cedar City, 1770),
Utah (Salt Lake City, 1400), Utah State (Logan, 1382), Utah Valley (Orem,
1387), Weber State (Ogden, 1310), Western Colorado (Gunnison, 2347),
Wyoming (Laramie, 2194).

**NCAAB — nombres aun no vistos en la base, pre-comprometidos por si
aparecen al terminar la recoleccion:**
Colorado State (Fort Collins, 1525), Colorado College (1839), Northern New
Mexico (Espanola, 1740), Western New Mexico (Silver City, 1800), Trinidad
State (1836), Otero (La Junta, 1250 -> NO, queda fuera), Lamar CC (1130 ->
NO, queda fuera).

**Explicitamente EXCLUIDOS por estar por debajo de 1300 m** (para que no
haya tentacion de meterlos despues si el resultado sale flojo):
Utah Tech (850), Idaho (790), Boise State (820), Montana (978), New Mexico
State (1190), Eastern New Mexico (1220), UTEP (1140), South Dakota Mines
(1030), Black Hills State (1100), Chadron State (1050), South Dakota (390).

Cualquier equipo cuyo nombre no aparezca en las listas de altitud de arriba
cuenta como **NO altitud**. No se añaden nombres despues de ver resultados.

## Procedimiento (fijado de antemano)

- Linea y cuota: snapshot `kickoff` (cierre real), **primera casa
  disponible** entre Bet365, Betway, BWin — en ese orden, sin elegir la
  mejor de las tres.
- Se apuesta **over a la linea principal**, no a peldaños alternativos.
- Se exige historial de **>=10 partidos previos** de ambos equipos, igual
  que en el analisis original.
- Viaje = partidos consecutivos como visitante contados hacia atras dentro
  de la temporada, usando solo partidos anteriores. Sin look-ahead.
- Stake plano de 1 unidad. Push (total = linea) cuenta como 0.
- Sin filtros adicionales, sin barrido de umbrales (ni el 1300 m ni el
  viaje >=4 se mueven), sin elegir liga ni periodo despues de ver los datos.

## Criterio de decision (fijado de antemano)

Para cada hipotesis por separado:

- **CONFIRMADA** si ROI > 0 **y** t >= 2 sobre los datos nuevos.
- **REFUTADA** en cualquier otro caso, incluido ROI positivo con t < 2.
- **NO CONCLUYENTE** si salen menos de **100 apuestas** para esa hipotesis.
  Con menos de eso no se rebaja el liston: se declara insuficiente y punto.

## Controles

Sobre los mismos datos nuevos, sin que afecten al veredicto principal:

- **Control fisico de H1.** La desviacion media respecto a la linea en
  partidos de altitud deberia reproducir algo parecido a **+5.54 puntos**.
  Si el ROI sale positivo pero la desviacion fisica NO aparece, es señal de
  que lo que hay es ruido y no un efecto de altitud.
- **Control fisico de H2.** Idem con **+1.33 puntos**.
- **Gradiente de altitud.** Si el efecto es real deberia ser mayor en los
  pabellones mas altos (>=1800 m) que en la franja 1300-1800 m. Es un
  control, no un filtro: no se usa para redefinir el umbral.
- **Gradiente de viaje.** Idem: viaje >=6 deberia ser al menos tan bueno
  como viaje >=4.
- **Placebo.** Local en viaje (no aplica) y visitante de altitud jugando
  fuera: no deberian mostrar nada.

## Compromiso

Se reporta lo que salga. Si sale refutada, **no se buscan subgrupos**
(liga, periodo, umbral de altitud distinto, longitud de viaje distinta,
peldaño alternativo) para rescatarla: eso convertiria estos datos en otra
ventana de busqueda y anularia el valor de este documento.

Precedente: el pre-registro de underdogs WNBA
(`PREREGISTRO_wnba_underdogs.md`) salio refutado con t = -2.10 y la celda
de control con +39.9% de ROI **no se investigo**. Aqui se aplica la misma
disciplina.
