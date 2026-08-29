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

### #5 — Besiktas vs Tofas Bursa · pretemporada turca · 2026-08-29 — PENDIENTE
- Linea conocida: 163.5 (el usuario escribio 163,4; se toma 163.5).
- Metodo: anclaje. Besiktas ligero favorito en casa; pretemporada -> me
  inclino UN punto bajo la linea (misma corazonada que la #3 anulada, sigue
  sin datos que la respalden y por eso se registra, para poder juzgarla).
- **Prediccion: Besiktas 84 - Tofas 79** (total 163, lado UNDER)

### #6 — Alba Berlin vs Hamburg Towers · pretemporada alemana · 2026-08-29 — PENDIENTE
- Linea conocida: 167.5.
- Metodo: anclaje. Alba favorito claro en casa (aunque en declive desde que
  dejo la Euroliga); pretemporada -> mismo punto under.
- **Prediccion: Alba 87 - Hamburg 80** (total 167, lado UNDER)

### #7 — Congo vs Mali · Clasificacion Mundial FIBA (Africa) · 2026-08-29 — PENDIENTE
- Linea conocida: 153.5.
- Metodo: anclaje + el unico dato fresco de esta ventana: el CIV-Egipto de
  hoy (misma competicion) cerro con linea 156.5 y acabo en 138. Una muestra
  no es tendencia, pero el ritmo de los clasificatorios africanos viene
  saliendo por debajo de lo que las lineas europeas sugieren -> 3-4 puntos
  under. Ganador: Congo por poco, con poca conviccion (ambos de segunda
  fila continental).
- **Prediccion: Congo 77 - Mali 73** (total 150, lado UNDER)

### #8 — Chicago Sky vs New York Liberty · WNBA · 2026-08-29 — PENDIENTE
- Sin linea comunicada por el usuario al predecir.
- Metodo: PRIMER partido del marcador con datos propios (39 partidos de
  cada equipo en la base). Sky 87.2/89.8, Liberty 90.8/87.5; totales medios
  177/178 con la liga en 177.8. Los 3 directos de 2026: totales 191/189/179
  y margenes 1/1/7, el ultimo GANADO por el Sky (19-ago). Liberty mejor
  equipo, Sky en casa, historial directo alto y cerrado.
- Linea comunicada DESPUES de predecir: 179.5. Mi 179 (con datos) aterriza
  a 0.5 de la linea: asi de eficiente es el mercado cuando ambos tenemos la
  misma informacion. Lado tecnicamente UNDER, sin valor ninguno.
- **Prediccion: Sky 88 - Liberty 91** (total 179, lado UNDER vs 179.5)

### #9 — España vs Mali (W) · amistoso pre-Mundial · 2026-08-29 — PENDIENTE
- Sin linea al predecir; el usuario comunico DESPUES la linea: 139.5. La
  prediccion (135) quedo commiteada antes de conocerla -> lado UNDER limpio.
- Matiz declarado al conocer la linea: el factor amistoso (defensas
  relajadas pre-Mundial) empuja contra el under; la prediccion no se toca.
- ASUNCION declarada: femenino (la masculina esta en el EuroBasket; el
  Mundial femenino de Berlin empieza el 4-sep).
- **Prediccion: España 76 - Mali 59** (total 135, lado UNDER vs 139.5)

### #10 — Palencia Basket vs Basquet Coruña · pretemporada Primera FEB · 2026-08-29 — PENDIENTE
- Sin datos en la base (ligas españolas no recolectadas) y sin linea
  conocida al predecir. A pelo: Coruña algo mejor plantilla (paso reciente
  por ACB), Palencia en casa que en pretemporada vale poco, totales de la
  categoria 155-165 con sesgo bajo por amistoso.
- **Prediccion: Palencia 77 - Basquet Coruña 81** (total 158)

