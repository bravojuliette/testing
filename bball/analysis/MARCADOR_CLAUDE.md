# Marcador de predicciones "a ojo" de Claude

El usuario tira partidos aleatorios; Claude predice el **marcador exacto**
antes de conocer el resultado y aqui queda el conteo, sin borrar ni
reinterpretar nada. **La fecha del commit de cada prediccion es la prueba
de que se hizo antes del resultado** (por eso esto es un archivo en git y
no una tabla).

Reglas fijadas el 2026-08-29, con 1 prediccion hecha:
- Se registra el marcador predicho; de el se derivan ganador, total y
  over/under contra la linea si se conocia.
- Se liquida contra el resultado real. Cada dimension es acierto o fallo.
- Referencia de "bueno": a cuota 1.90 la casa exige 52.4% en O/U.
- Prediccion de Claude sobre si mismo, para contrastar cuando haya muestra:
  "perdere contra el margen: 48-51% en O/U, y el ganador lo acertare mas o
  menos lo que diga la cuota, no mas".

## Conteo

| # | ganador | O/U | error total | exacto |
|---|---|---|---|---|
| 1 | OK | OK (over) | 4 | no |

## Predicciones

### #1 — Chinese Taipei Blue (W) vs Japan (W) · Jones Cup femenina · 2026-08-29 — LIQUIDADA
- **Prediccion: 63-74** (linea conocida: 135.5)
- Real: **66-75** → ganador OK, over OK (141 > 135.5), error de total 4, exacto no
- Contexto honesto: la prediccion se hizo con el partido YA EN JUEGO (sin
  conocer marcador). La primera version (84-79) asumia torneo masculino e
  iba 26 puntos desviada; la buena vino tras saber que era femenino y
  anclarse a la linea. El merito es en gran parte de la linea.

### #2 — Costa de Marfil vs Egipto · AfroBasket · 2026-08-29 — PENDIENTE
- Contexto al predecir: partido EN VIVO, quedaba 9:45 del Q1 con 2-0 (sin
  informacion util del marcador). Lineas vistas: handicap CIV -7.5 (1.87),
  total 156.5 (con flecha de subida), ganador 1.34 / 3.10.
- Metodo: anclaje a la linea. El mercado dice CIV por ~8 con ~156 puntos.
  FIBA 40 min. Sin opinion propia que aporte sobre eso.
- **Prediccion: Costa de Marfil 82 - Egipto 74** (total 156, un pelo under;
  ganador CIV)

### #3 — Manisa Buyuksehir Belediye vs Fenerbahce · pretemporada turca · 2026-08-29 — PENDIENTE
- Contexto al predecir: empezaba en ~27 min. Handicap Fener -9.5 (1.85),
  total 159.5, ganador 3.70 / 1.22.
- Metodo: anclaje a la linea (Fener por ~10, ~159 puntos). Unica opinion
  propia: es pretemporada -- rotaciones largas y ritmo irregular, asi que
  me inclino un punto bajo la linea, sabiendo que es una corazonada sin
  datos que la respalden.
- **Prediccion: Manisa 74 - Fenerbahce 84** (total 158, under; ganador Fener)
