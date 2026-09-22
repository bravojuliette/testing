# Pre-registro: la pendiente de linea alta en WNBA

**Escrito el 2026-08-29, contra partidos que NO existen todavia** (los de
WNBA desde el 2026-09-01: final de temporada regular y playoffs). Aprobado
por el usuario.

## De donde sale

La radiografia comparada de ligas (diferencias_ligas.py, commit previo a
este) mostro la pendiente de (final - linea de cierre) sobre (linea):

| liga | n | pendiente | t |
|---|---|---|---|
| NBA | 1679 | -0.007 | -0.14 |
| NCAAB | 3571 | -0.066 | -2.28 |
| **WNBA** | 925 | **-0.100** | -1.16 |
| Euroliga | 716 | -0.045 | -0.42 |

## Motivos para dudar, listados antes de ver nada

1. **La misma hipotesis acaba de morir en NCAAB**: busqueda -0.081 (t=-2.42),
   reserva feb-mar -0.027 (t=-0.45). El patron "se desvanece fuera de
   muestra" es exactamente lo que hace el ruido.
2. La celda WNBA se eligio POR ser la mas negativa de una tabla de 4: eso
   es seleccion post-hoc de manual.
3. t=-1.16 de partida ni siquiera es señal dentro de muestra.
4. La muestra de comprobacion sera pequeña (~60-80 partidos hasta el final
   de los playoffs): potencia baja, y se declara de antemano.

Probabilidad honesta de confirmacion: baja. Se registra porque los datos
llegan gratis y porque asi se cierra el ultimo cabo suelto por liga.

## Hipotesis

> En los partidos de WNBA con fecha >= 2026-09-01 (temporada regular
> restante y playoffs completos), la pendiente de la regresion de
> (total final - linea de cierre) sobre (linea de cierre) es negativa.

## Procedimiento (fijado)

- Linea de cierre: snapshot `kickoff`, primera casa entre Bet365, Betway,
  BWin, en ese orden.
- Minimos cuadrados sin recortes ni ponderar, todos los partidos apostables.
- Sin subgrupos, sin umbral de linea, sin excluir playoffs ni nada elegido
  despues.

## Criterio de decision (fijado)

- **CONFIRMADA** si pendiente < 0 **y** t <= -2.
- **REFUTADA** en cualquier otro caso.
- **NO CONCLUYENTE** si hay menos de **60** partidos apostables al cierre.

Dado el n esperado, "REFUTADA" aqui significara "sin efecto del tamaño
grande"; un efecto pequeño real quedaria indetectable y NO se reinterpretara
como confirmacion.

## Compromiso

El de siempre, con el historial delante: WNBA underdogs (invalidado por
bug de datos), situacionales (2 refutadas), linea alta NCAAB (refutada).
Se reporta lo que salga y no se rescata nada con subgrupos.
