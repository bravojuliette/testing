# Pre-registro: underdogs de tramo medio en WNBA

**Escrito el 2026-08-28, ANTES de recolectar los datos con los que se va a
comprobar.** Ese es el punto: la hipotesis, el criterio de exito y el
procedimiento quedan fijados aqui para que el resultado no se pueda
reinterpretar despues.

## De donde sale

En la calibracion por tramo de cuota sobre los datos que ya teniamos
(temporadas 2024-25 y 2025-26 de NBA, WNBA y Euroliga, 2183 apuestas
potenciales a underdog con cuota de cierre real) aparecio esto:

| Tramo de cuota | n | Gana real | Implicita | ROI |
|---|---|---|---|---|
| 2.0 - 2.5 | 588 | 45.1% | 45.3% | -0.0% |
| 2.5 - 3.5 | 728 | 37.0% | 34.9% | +5.7% |
| 3.5 - 5.0 | 420 | 26.0% | 24.9% | +5.1% |
| 5.0 - 8.0 | 262 | 14.1% | 16.7% | -16.2% |
| > 8.0 | 106 | 4.7% | 10.3% | -55.2% |

El tramo 2.5-5.0 da +5.5% (n=1148) sin filtro alguno. Al partirlo por liga,
el efecto NO es general:

| Liga | n | ROI | t |
|---|---|---|---|
| NBA | 684 | +2.7% | 0.45 |
| Euroliga | 323 | -2.3% | -0.29 |
| **WNBA** | **141** | **+37.2%** | **2.61** |

Todo el ROI viene de WNBA, con una muestra pequeña (141) y la mitad
reciente apoyada en solo 20 apuestas. Hipotesis plausible del porque: la
WNBA mueve mucho menos dinero que la NBA, las casas le dedican menos
atencion y su linea podria estar peor ajustada. Hipotesis alternativa igual
de plausible: es suerte.

## Hipotesis a comprobar (una sola, sin variantes)

> Apostar **todos** los underdogs de WNBA cuya cuota de cierre este entre
> 2.5 y 5.0, sin ningun filtro adicional, da ROI positivo.

## Datos de comprobacion

Temporadas **2022, 2023 y 2024 de WNBA**, que a fecha de hoy NO estan en la
base y NUNCA se han mirado. Se recolectan despues de escribir esto.
Rango: 2022-04-01 a 2024-10-31.

## Procedimiento (fijado de antemano)

- Mercado: ganador (18_1), snapshot `kickoff` (cuota de cierre real).
- Casa: la primera disponible entre Bet365, Betway, BWin (mismo criterio
  que en el analisis original).
- Underdog = el equipo con cuota MAYOR que la de su rival. Una apuesta por
  partido como maximo.
- Se exige historial de >=10 partidos previos de ambos equipos, igual que
  en el analisis original.
- Stake plano de 1 unidad. Sin filtros, sin barrido de umbrales, sin
  eleccion de subgrupos: se apuesta el tramo entero.

## Criterio de decision (fijado de antemano)

- **CONFIRMADA** si ROI > 0 **y** t >= 2 sobre esos datos nuevos.
- **REFUTADA** en cualquier otro caso, incluido ROI positivo con t < 2.
- Si salen menos de 80 apuestas, se declara **NO CONCLUYENTE** por muestra
  insuficiente (no se rebaja el liston para salvarla).

## Controles (para descartar que sea un artefacto general)

Sobre esos mismos datos nuevos se reporta tambien, sin que afecte al
veredicto principal:

- El mismo tramo 2.5-5.0 en NBA y Euroliga de las temporadas nuevas que
  entren, si entra alguna: debe seguir cerca de cero.
- Los tramos >5.0 en WNBA: deben seguir claramente negativos (sesgo
  favorito-underdog), o algo va mal en la extraccion de datos.

## Compromiso

Se reporta el resultado tal cual salga. Si sale refutada, no se buscan
subgrupos dentro de los datos nuevos para rescatarla: eso convertiria la
reserva en otra ventana de busqueda y anularia el valor de este documento.
