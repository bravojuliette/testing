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
| 2 | OK | OK (under) | 18 | no |

## Predicciones

### #1 — Chinese Taipei Blue (W) vs Japan (W) · Jones Cup femenina · 2026-08-29 — LIQUIDADA
- **Prediccion: 63-74** (linea conocida: 135.5)
- Real: **66-75** → ganador OK, over OK (141 > 135.5), error de total 4, exacto no
- Contexto honesto: la prediccion se hizo con el partido YA EN JUEGO (sin
  conocer marcador). La primera version (84-79) asumia torneo masculino e
  iba 26 puntos desviada; la buena vino tras saber que era femenino y
  anclarse a la linea. El merito es en gran parte de la linea.

### #2 — Costa de Marfil vs Egipto · Clasificacion Mundial FIBA · 2026-08-29 — LIQUIDADA
- **Prediccion: 82-74** (total 156, un pelo under de la linea 156.5)
- Real: **72-66** (total 138; cuartos 30/36/44/28) -> ganador OK, under OK
  (138 < 156.5), error de total 18, exacto no.
- **Apuesta real del usuario: over 149.5 en vivo -> PERDIDA** (faltaron 12
  puntos; el Q4 anoto solo 28).
- Autopsia honesta de la lectura en vivo: con 110 tras 3 cuartos dije que el
  over del usuario era ~57-61% favorito, usando la Euroliga como comparable
  (Q4 medio 41.7). El Q4 real fue 28. Una muestra no refuta la estimacion,
  pero el comparable era generoso: un clasificatorio africano anota menos
  que la Euroliga en el ultimo cuarto, y ese sesgo iba TODO hacia el over.
- Nota: la liga real es Clasificacion Mundial FIBA, no AfroBasket como se
  anoto al predecir.

### #3 — ANULADA a peticion del usuario
La prediccion del Manisa-Fenerbahce se retira del marcador por decision del
usuario, ANTES de conocerse el resultado (el partido seguia en juego). Que
la anulacion sea previa al resultado importa: anular despues de verlo seria
seleccion a dedo; asi, solo reduce la muestra. No cuenta en el conteo.

### #4 — Safe Spaces vs Strathmore · liga keniana (femenino) · 2026-08-29 — ANULADA (partido cancelado)
El partido se cancelo en juego, segun informa el usuario. Sin resultado no
hay liquidacion posible: fuera del conteo por causa externa (esto no es
seleccion a dedo: no existe resultado que hubiera podido gustar o no).
La apuesta real del usuario (over 104.5) queda tipicamente devuelta por la
casa en cancelaciones -- comprobar en el historial de la cuenta.
- Contexto al predecir: EN VIVO, 12-13 a ~1 min del final del Q1. SIN linea
  conocida y SIN datos de estos equipos en la base: es la prediccion mas
  desnuda del marcador (sin ancla de mercado).
- Metodo: Q1 proyectado ~27-28; se regresa el ritmo hacia el tipico de liga
  africana femenina (~110-120 de total) porque nuestra medicion de cuartos
  dice que el Q1 predice poco el resto. Ganador por conocimiento vago
  (Safe Spaces suele dominar el femenino keniano), no por el 12-13.
- **Prediccion: Safe Spaces 59 - Strathmore 55** (total 114)

> **Apuesta REAL del usuario: OVER 104.5, tomada en vivo.** Gana con 105+
> puntos totales. Dato interesante: existe linea viva (104.5) y la
> prediccion a ciegas de Claude (114) queda ~9 puntos POR ENCIMA del
> mercado -- la primera vez que Claude discrepa de verdad de una linea.
> Historial del proyecto: cuando Claude y la linea discrepan mucho, suele
> tener razon la linea. La apuesta del usuario necesita bastante menos que
> la prediccion: le vale con que el mercado se quede solo un poco corto.

