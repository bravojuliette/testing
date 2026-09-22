"""Calibracion favorito-longshot con datos LIMPIOS (primera vez posible).

Terreno firme: NBA/Euroliga/WNBA<=2025, casas fiables, cuotas ya
normalizadas por el reparse (NO volver a intercambiar: hacerlo aqui produjo
un doble swap que fabrico un falso +55% en longshots -- quedo como leccion).

RESULTADO (2026-08-29, n=57k filas):
  0.90-0.95 implicita: gana 95.2% (implicita 91.5%) -> ROI -0.2%
  0.80-0.90:           gana 85.6% (84.6%)           -> ROI -3.8%
  tramos medios:                                       ROI -6 a -8%
  0.05-0.20:           gana 13.4% (14.7%)           -> ROI -15.5%

El sesgo favorito-longshot EXISTE y va en la direccion de libro: el favorito
fuerte esta ligeramente barato (el sesgo casi cancela el margen: apostarlo
cuesta -0.2%, la apuesta mas barata del baloncesto) y el longshot es una
trituradora (-15.5%). No hay beneficio: hay un mapa de donde se esconde el
margen. Conclusion operativa: si se apuesta por ocio, favoritos fuertes; los
longshots son el lado sistematicamente caro.

La teoria B (incoherencia ML vs handicap de la misma casa) dio -6% en el
grueso; su cola de "+45%" era la descalibracion de un modelo logistico de
una sola pendiente en handicaps extremos (Nets +12.5 / ML 5.65 es coherente;
mi sigmoide decia que no). Sin señal real.
"""
