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

---

## VEREDICTO (2026-09-28): NO CONCLUYENTE por muestra

`python3 bball/analysis/veredicto_pendiente_wnba.py`

| dato | valor |
|---|---|
| partidos WNBA terminados desde 2026-09-01 | 16 |
| apostables al cierre (kickoff, Bet365/Betway/BWin) | **11** |
| minimo escrito en el pre-registro | 60 |
| pendiente | +0.6453 |
| t | +1.37 |
| sesgo medio (final - linea) | -0.95 |

**n=11 contra un minimo de 60: se dispara la rama "NO CONCLUYENTE" del
criterio**, escrita y firmada antes de mirar. La pendiente sale ademas con el
signo CONTRARIO al de la hipotesis (+0.65), pero con 11 partidos eso no es
informacion: es ruido, y no se va a contar como refutacion por la puerta de
atras cuando el criterio dice otra cosa.

### Por que la muestra fue 11 y no los 60-80 previstos
El punto 4 de los "motivos para dudar" acerto en la direccion y se quedo
corto en la magnitud. Lo que paso, medido en los logs de recoleccion:

- La temporada regular de WNBA acabo el **31-ago**: del 1 al 16 de septiembre
  la API devuelve CERO partidos, dia a dia (runs del 7-sep y del 14-sep, que
  terminaron en exito consultando esos dias uno por uno). No es un agujero de
  datos, es que no se jugo.
- Los playoffs dieron 16 partidos entre el 17 y el 21 de septiembre.
- De esos 16, solo 11 tienen linea de cierre en las tres casas del
  pre-registro (Bet365 11, Betway 0, BWin 0). El orden de casas estaba
  congelado y no se amplia ahora para ganar n: eso seria mover el
  procedimiento despues de ver el resultado.

Aun completando el cuadro de playoffs entero, el techo eran ~25 partidos.
**El pre-registro era irrealizable desde el dia en que se escribio** y no se
supo hasta contar los partidos: se registro creyendo que quedaban 60-80, y
quedaban 16. Queda escrito como error de planificacion, no de analisis.

### Y ademas la recoleccion se corto
El collect del 28-sep falla con **HTTP 403 PERMISSION_DENIED** de BetsAPI en
`/v3/events/ended` (`"Check Coverage on betsapi.com/mm/pricing_table"`) en el
primer dia no cacheado, el 22-sep. Reproducido dos veces (runs 36401275542
intentos 1 y 2), asi que no es un fallo pasajero: es la cobertura de la
cuenta. Los datos de WNBA se quedan congelados en el 21-sep de forma
definitiva mientras eso no se arregle. Da igual para este veredicto -- 25 <
60 igual que 11 < 60 -- pero no da igual para lo que venga despues.
