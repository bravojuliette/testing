# PRE-REGISTRO: la casa OUTLIER contra el CONSENSO (líneas de total, kickoff)

Commiteado el 2026-08-31, antes de correr el test. Primera teoría del
programa "batir al eslabón lento, no al mercado": no intenta predecir
baloncesto mejor que la casa — apuesta a que cuando una casa discrepa
mucho de las demás, son las demás las que tienen razón.

## Mecanismo (por qué podría funcionar donde los patrones fallaron)
Una línea desviada del consenso suele ser un modelo desactualizado o una
casa que no vio una noticia (baja, descanso programado, back-to-back).
Es el método estándar de la industria (línea sharp vs casa soft). No
requiere información nueva: requiere que N-1 casas sepan más que 1, un
listón mucho más bajo que saber más que todas.

## Datos (mirada previa DECLARADA: solo cobertura y dispersión, jamás ROI)
- `bball_local.db`: NBA (2644 eventos, todos con >=3 casas), WNBA (1210),
  Euroleague (1056); 4439 incluyen a PinnacleSports.
- `bball_chicas.db`: solo 222 eventos con >=3 casas (el 85% cotiza solo
  Bet365) -> bloque POOLED informativo, potencia baja declarada.
- Mercado: totales (18_3), snapshot kickoff, partidos completados.
- De moneyline NO hay snapshots kickoff multi-casa: fuera de este test.

## Procedimiento
1. Por evento con >=3 casas cotizando línea de total al kickoff:
   - Para cada casa b: desviación_b = línea_b − mediana(líneas del resto).
   - OUTLIER = la casa con |desviación| máxima. Se exige |desviación| >=
     umbral. UMBRAL PRIMARIO: 2 puntos. Escalera declarada: 3 y 4 puntos
     como test de dosis-respuesta (si el efecto es real, el ROI debe
     crecer, o al menos no invertirse, con la desviación).
2. Apuesta: EN la casa outlier, HACIA el consenso: línea outlier POR
   ENCIMA de la mediana -> UNDER a sus cuotas; por debajo -> OVER.
   Cuotas en [1.01, 20]; push (final == línea outlier) excluido.
   Una apuesta por evento (solo la casa más desviada).
3. Variante PINNACLE (bloque aparte, misma mecánica): consenso = la línea
   de PinnacleSports en vez de la mediana; outlier = cualquier casa soft
   desviada >= umbral de Pinnacle; se apuesta en la soft hacia Pinnacle.
   (El clásico de la industria en versión medible.)
4. Bloques: NBA / WNBA / Euroleague / CHICAS-pooled, por separado.
   Split búsqueda/reserva por mediana de fecha de cada bloque.

## Criterios (los de siempre)
- CONFIRMADA una celda: ROI > 0, t >= 2, n >= 100 (pooled), MISMO signo
  en búsqueda y reserva, y dosis-respuesta no invertida (el umbral 3-4 no
  puede dar sistemáticamente peor que el 2 si el mecanismo es real).
- NO CONCLUYENTE: n < 100 (se espera en chicas).
- REFUTADA: el resto. Sin rescates por subgrupos no declarados.

## Riesgo declarado ANTES de mirar (para no inventar excusas después)
La desviación puede ser un artefacto de CAPTURA: si el snapshot de la
outlier es más viejo que el de las demás, su línea "desviada" quizá ya no
era apostable. Se reporta la diferencia de `captured_at` entre outlier y
consenso; si el efecto solo existe con snapshots viejos, es artefacto, no
ventaja. Además, aun CONFIRMADA, la ejecución real exige tener cuenta en
la casa lenta y que no te limite — el aviso económico de siempre.
