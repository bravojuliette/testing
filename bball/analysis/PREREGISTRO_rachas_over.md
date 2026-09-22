# Pre-registro: rachas de OVER en ambos equipos -> under profundo

**Escrito el 2026-08-28, ANTES de recolectar los datos nuevos con los que se
va a comprobar.** El usuario señalo el problema correctamente: la señal
aparece en solo 61 partidos. Se amplia la muestra con ligas y temporadas
que hoy NO estan en la base, y se fija aqui el criterio para que el
resultado no se pueda reinterpretar despues.

## De donde sale

Sobre los 3021 partidos actuales (NBA, WNBA, Euroliga, temporadas 2024-25
y 2025-26), el acierto del under a la linea principal de cierre:

| Grupo | n | Acierto under |
|---|---|---|
| Todos | 3021 | 48.9% |
| Ambos equipos vienen de >=1 overs | 871 | 48.2% |
| Ambos equipos vienen de >=2 overs | 228 | 52.4% |
| **Ambos equipos vienen de >=3 overs** | **61** | **60.7%** |

Y en la escalera de Bwin con >=3 overs, el peldaño +6 (cuota 1.50) da
70.5% de acierto frente al 66.7% que necesita.

Racha = partidos consecutivos del equipo, hacia atras, en los que el total
quedo por encima de la linea de cierre de AQUEL partido.

**Motivo para dudar (por lo que se hace este test)**: n=61, y al partirlo
por periodo y liga se rompe -- 2025-26 da -29.9% (n=16) frente a +28.8%
(n=45) en el periodo anterior; NBA +32.0% (n=34) frente a Euroliga -49.0%
(n=11). Puede ser reversion a la media real o puede ser ruido.

## Hipotesis a comprobar (una sola, sin variantes)

> Cuando AMBOS equipos llegan con una racha de **>=3 overs**, apostar
> **under en el peldaño +6** (linea de cierre + 6, cuota 1.50 de la
> escalera de Bwin) da ROI positivo.

## Datos de comprobacion

Partidos que hoy NO estan en la base:
- Temporadas anteriores de NBA y Euroliga (2022-23 y 2023-24).
- Ligas de baloncesto adicionales que cubra BetsAPI y que hoy no
  recolectamos, elegidas por volumen ANTES de mirar ningun resultado.

## Procedimiento (fijado de antemano)

- Linea y cuota: snapshot `kickoff` (cierre real), primera casa disponible
  entre Bet365, Betway, BWin.
- Racha U/O calculada solo con partidos anteriores del propio equipo, sobre
  la linea de cierre de cada uno. Sin look-ahead.
- Se exige historial de >=10 partidos previos de ambos equipos (igual que
  en el analisis original).
- Peldaño +6 a cuota 1.50 fija. Stake plano de 1 unidad.
- Sin filtros adicionales, sin barrido de umbrales, sin elegir liga ni
  periodo despues de ver los datos.

## Criterio de decision (fijado de antemano)

- **CONFIRMADA** si ROI > 0 **y** t >= 2 sobre los datos nuevos.
- **REFUTADA** en cualquier otro caso, incluido ROI positivo con t < 2.
- **NO CONCLUYENTE** si salen menos de 100 apuestas (con menos de eso no se
  rebaja el liston: se declara insuficiente y punto).

## Controles

Sobre los mismos datos nuevos, sin que afecte al veredicto principal:
- El gradiente completo (>=1, >=2, >=3 overs): deberia reproducirse el
  ascenso 48% -> 52% -> 60% si el efecto es real.
- El espejo (ambos >=3 unders -> under) debe seguir siendo malo, como en
  los datos actuales (44.7% de acierto con >=2 unders).

## Compromiso

Se reporta lo que salga. Si sale refutada, no se buscan subgrupos (liga,
periodo, peldaño distinto) para rescatarla: eso convertiria estos datos en
otra ventana de busqueda y anularia el valor de este documento.
