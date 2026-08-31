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

## RESULTADO (2026-08-31, corrido tal cual)

**Pasada principal, espectacular a primera vista:** NBA +13,2% a +18,3%
(t≈6, n=1181-2091), positivo en ambas mitades, dosis-respuesta creciente
con el umbral, idéntico con consenso-mediana y con Pinnacle. WNBA +6 a
+13% (t hasta 2,4). Euroleague +1 a +8% (t<2). Chicas negativo (n<110,
sin casas sharp). En cualquier otro proyecto esto se publicaría como
sistema ganador.

**Sensibilidad de frescura (el riesgo declarado): lo mata del todo.**
Exigiendo que el snapshot de la outlier esté a <=120s del más fresco del
evento (gap mediano de la pasada principal: ~20 MINUTOS):
- NBA: +1,9% → -17% según celda (t<=0,4; n=15-42).
- WNBA: -7 a -18% en TODAS las celdas.
- Euroleague: **-25 a -31% con t hasta -2,8** — significativamente PEOR
  que el margen.

**Veredicto: ARTEFACTO, no ventaja.** El "+13% t=6" es valor-contra-
línea-de-cierre medido sobre precios viejos que ya no existían: la línea
outlier rancia siempre pierde contra el consenso final (eso es el CLV de
libro, el hecho mejor documentado del sector) pero no era apostable a ese
precio en ese momento. Y el detalle más informativo está en la celda
fresca de Euroliga: cuando una casa se desvía del consenso CON snapshot
fresco, apostar contra ella pierde -25/-30% — es decir, **la que se mueve
primero suele tener razón** (lidera el movimiento con información; las
"stale" son las demás). Esto invierte el mecanismo e indica dónde está la
señal real: en el LEAD-LAG (seguir a la casa que se mueve primero,
segundos después, contra las lentas), que es exactamente la Teoría 2
(latencia en vivo) del programa. Este frente kickoff-outlier queda
CERRADO como inapostable con datos históricos; la versión honesta solo
puede testearse en tiempo real con el scanner.
