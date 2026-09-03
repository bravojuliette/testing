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

---

# RESULTADO (2026-08-28, tras recolectar los datos)

Recolectadas las temporadas 2022, 2023 y 2024 de WNBA: **764 partidos
nuevos** que no estaban en la base cuando se escribio la hipotesis.

## Veredicto: **REFUTADA**

    n=367   cuota media=3.33   acierto=26.2%   ROI=-15.9%   t=-2.10

No cumple el criterio fijado (ROI>0 y t>=2). La muestra supera con creces
el minimo de 80, asi que el resultado es concluyente, no un "no sabemos".

El t=-2.10 es notable: no solo no gana, sino que **pierde de forma
estadisticamente significativa**. A cuota media 3.33 el punto de equilibrio
esta en acertar 30.0%; se acerto el 26.2%.

Por año (informativo, no altera el veredicto): las tres temporadas
apuntan en la misma direccion, sin ninguna que rescate la idea.

| año | n | acierto | ROI | t |
|---|---|---|---|---|
| 2022 | 107 | 27.1% | -13.4% | -0.94 |
| 2023 | 122 | 27.9% | -10.6% | -0.80 |
| 2024 | 138 | 23.9% | -22.5% | -1.87 |

## Por que la hipotesis parecia buena y no lo era

El +37.2% que la origino (WNBA, n=141) venia en buena parte de la
temporada 2026, que DESPUES se descubrio corrupta en origen: BetsAPI
cambia el orden local/visitante a mitad de la temporada 2026 de WNBA (ver
config.UNRELIABLE_ORIENTATION). Al excluir ese tramo, el mismo tramo de
cuota 2.5-5.0 sobre datos limpios ya daba -0.1% en vez de +6.2%.

Es decir: la hipotesis nacio de un artefacto de datos, y los datos limpios
la refutan. El pre-registro hizo su trabajo -- fijar el criterio ANTES
impidio reinterpretar el resultado a posteriori.

## Controles

    cuota 1.0-2.5:  n=171  ROI  +4.7%   (esperado ~0: OK)
    cuota 5.0-8.0:  n= 92  ROI +39.9%   (esperado negativo: NO se cumple)
    cuota 8.0-99:   n= 64  ROI -38.3%   (esperado muy negativo: OK)

El tramo 5.0-8.0 sale positivo con n=92, contra lo esperado. A esas cuotas
bastan 3-4 aciertos afortunados para dar la vuelta al ROI; sobre el
historico completo y limpio ese mismo tramo da -24.7% con t=-3.14, que es
la lectura fiable. No se investiga mas: el pre-registro prohibe
expresamente buscar subgrupos que rescaten la idea.

## Conclusion

Los underdogs de WNBA en el tramo 2.5-5.0 no son rentables. La unica
regularidad solida que queda en el mercado de ganador sigue siendo el
sesgo favorito-underdog en las cuotas largas (>5.0), que es una senal de
que NO apostar ahi, no de una oportunidad.
