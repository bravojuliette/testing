# PRE-REGISTRO: NCAAB TOTALES pre-partido (sesgo O/U y movimiento intra-casa)

Escrito el 2026-09-03, DESPUES de refutar el moneyline (PREREGISTRO_ncaa_
prepartido.md) y ANTES de calcular un solo ROI sobre totales. Solo
pre-partido, por peticion del usuario.

## Por que este frente
Los totales son INMUNES al bug de orientacion de NCAAB (el over/under no
depende de quien juega en casa), asi que aqui no hay que corregir nada. Y
hay dos snapshots REALES DE LA MISMA CASA: `start` y `kickoff`. Eso permite
medir el movimiento de linea sin el artefacto que mato el barrido de agosto,
donde se comparaba la apertura de una casa con el cierre de OTRA y se
apostaba un precio que ya no existia.

## H1 -- SESGO OVER/UNDER al precio de apertura
Respaldar siempre OVER, y siempre UNDER, a la linea y cuotas de APERTURA de
la casa legal (Bet365/Betway/BWin, primera disponible en ese orden).
Push (total final == linea) excluido. Cuotas en [1.01, 20].
- CONFIRMADA: ROI > 0, t >= 2, n >= 300, mismo signo en busqueda y reserva
  (corte por mediana de fecha). REFUTADA el resto. NO CONCLUYENTE si n<300.

## H2 -- MOVIMIENTO DE LINEA DENTRO DE LA MISMA CASA
Para los partidos con `start` y `kickoff` de la MISMA casa legal:
movimiento = linea_kickoff - linea_start.
Se apuesta AL PRECIO DE KICKOFF (que existe y es posterior al movimiento --
sin mirar al futuro), en dos variantes declaradas:
- **SEGUIR**: si la linea subio >= umbral, OVER; si bajo >= umbral, UNDER.
- **CONTRARIAR**: exactamente lo opuesto.
Umbrales declarados: 1.0, 2.0 y 3.0 puntos (dosis-respuesta: si el efecto es
real el ROI no puede invertirse al subir el umbral).
- CONFIRMADA una celda: ROI > 0, t >= 2, n >= 300, mismo signo en ambas
  mitades y dosis-respuesta no invertida. REFUTADA el resto.

## Controles obligatorios
1. **Base de comparacion:** el ROI de apostar OVER (o UNDER) a ciegas al
   precio de kickoff, sobre la MISMA muestra. Una celda de H2 que no supere
   a su lado ciego no mide movimiento, mide sesgo O/U.
2. **Simetria:** SEGUIR y CONTRARIAR son opuestos exactos; si las dos salen
   positivas, hay un error de contabilidad y el resultado se anula.
3. Se reporta cuanto se mueve la linea (mediana y p90) y cuantos partidos
   superan cada umbral, antes de mirar ningun ROI.

## Compromiso
Si las dos salen refutadas, el frente de totales pre-partido en NCAAB queda
cerrado y no se buscan subgrupos (ni por rango de linea, ni por casa, ni por
mes). El proyecto lleva cinco espejismos de dos digitos: la regla de parada
es el criterio, no la insistencia.
