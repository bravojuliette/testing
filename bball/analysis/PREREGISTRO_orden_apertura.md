# PRE-REGISTRO: el nicho del ORDEN DE APERTURA -- consenso previo contra Bet365

Escrito y commiteado el 2026-09-03 ANTES de calcular ningun ROI de este
documento. El timestamp del commit es la prueba.

## De donde sale este nicho (y por que no es pesca)
El usuario pidio dejar de barrer mercados enteros y **especializarse en un
filtro**. Se buscaron filtros con criterios que NO usan resultados:

- *Atencion de la casa* (nº de casas que cotizan el partido): **DESCARTADO sin
  test**. En NCAAB todos los partidos del feed los cotizan 11-16 casas
  (p10=11, p90=16) y el margen de Bet365 apenas se mueve (3.90% con 6-10 casas,
  4.26% con 16+). No hay partidos "olvidados" que filtrar.
- *Orden de apertura*: **este**. Cada casa abre su linea en un momento
  distinto, y esa hora esta en `captured_at`.

Hecho medido hoy: **Bet365 no abre la primera**. En 4.083 de 5.426 partidos de
NCAAB (y 7.151 sumando NBA/WNBA/Euroliga) abre con **>=5 casas ya abiertas**,
y la 5a habia abierto **2,7h antes** de mediana (p10 0.8h, p90 6.8h).

Eso define un nicho con una propiedad que ningun test anterior tuvo: **la
informacion es legitimamente ANTERIOR al precio jugable**. No hay lookahead.
Los tests de outlier-contra-consenso y de Bet365-contra-Pinnacle murieron
justo por lo contrario (comparaban con precios de 11h despues o rancios).

## El problema, declarado ANTES de mirar
Se midio tambien QUIEN abre antes, y la respuesta rebaja mucho la esperanza:

| casa | abre antes que Bet365 | su margen |
|---|---|---|
| DafaBet | 90.9% | 4.93% |
| CloudBet | 90.2% | 7.46% |
| FonBet | 87.3% | 7.61% |
| Duelbits | 84.0% | 5.02% |
| Coral / Ladbrokes | 53% | 8.20% |
| **PinnacleSports** | **7.0%** | 3.86% |
| **Everygame** | **5.9%** | 4.10% |
| YSB88 | 1.5% | 4.44% |
| BWin | 0.2% | 6.03% |

**Las casas blandas y caras abren primero; Bet365 va en medio; las sharp llegan
despues.** O sea que el consenso disponible en el momento jugable es un
consenso de casas con margenes del 5-8%, no la opinion sharp. El mercado pone
la informacion buena sistematicamente por detras del precio que se puede tomar.

Aun asi el test merece correrse: promediar muchas casas blandas cancela margen
(se de-viga cada una) y puede quedar un centro informativo. Pero la expectativa
declarada es baja.

## Universo y procedimiento (fijado aqui)
- Moneyline (18_1), snapshot `start`, partidos completados sin empate.
  Ligas NBA / NCAAB / WNBA / Euroleague. Orientacion NCAAB con
  `orientacion.py`: en 'swap' se reetiqueta el SLOT, **jamas** el marcador.
- **Alineacion del par obligatoria**: 15 de 17 casas guardan el par al reves
  que Bet365. Se alinea por PRECIOS contra Bet365 (nunca por resultados),
  con el metodo ya validado en `cuantas_casas.py`.
- Nicho: partidos donde **>=5 casas abrieron ANTES** que Bet365 (umbral fijado
  aqui; escalera declarada: >=5 y >=8).
- Consenso: de-vig proporcional de cada casa previa, y **MEDIANA** de sus
  probabilidades del local (mediana, no media: robusta a una casa disparatada).
- Ventaja: `e(X) = p_consenso(X) * cuota_365(X) - 1`. Se apuesta al lado de
  mayor ventaja **a la cuota de apertura de Bet365** si supera el umbral.
- Umbrales declarados: **e >= 0%, 2%, 5%**.

## EL CONTRASTE QUE DA VALOR AL TEST (declarado de antemano)
Se corre TODO dos veces:
1. **ANTES** (ejecutable): consenso solo con casas que abrieron antes que
   Bet365. Es la unica version apostable y la unica que puede CONFIRMAR.
2. **DESPUES** (inejecutable, solo diagnostico): consenso con las casas que
   abrieron despues -- incluidas Pinnacle y Everygame. Tiene lookahead a
   proposito y **no puede confirmar nada**.

Lectura declarada de las cuatro combinaciones:
- ANTES gana y DESPUES gana -> hay señal y ademas es alcanzable. CONFIRMADA.
- ANTES pierde y DESPUES gana -> **la señal existe pero llega tarde**: el
  problema no es que el mercado sea eficiente, es el ORDEN. Conclusion util y
  distinta de "no hay nada".
- ANTES gana y DESPUES pierde -> casi seguro ruido; se exigira reserva.
- Ninguna gana -> no hay señal explotable por esta via.

## PLACEBO
Barajar las probabilidades del consenso entre partidos (3 semillas: 1,2,3).

## Puerta de sanidad
Se reporta el acierto del consenso ANTES, el del consenso DESPUES y el de
Bet365 sobre los mismos partidos. Si el consenso ANTES no bate a la moneda, el
resultado es NO CONCLUYENTE por consenso inutil, no REFUTADA.

## Criterios de decision
- **CONFIRMADA** (solo la version ANTES): ROI > 0, t >= 2, n >= 300, mismo
  signo en busqueda y reserva (corte por mediana de fecha), escalera no
  invertida y placebo peor.
- **NO CONCLUYENTE**: n < 300 o puerta de sanidad no superada.
- **REFUTADA**: el resto, incluido ROI positivo con t < 2.

---

## AVISO: la primera pasada fue INVALIDA por un bug mio (alineacion)
La primera ejecucion dio un consenso ANTES con **52,60% de acierto** frente al
68,77% de Bet365. Eso era demasiado malo para ser un consenso real de casas de
apuestas, y en vez de publicarlo como refutacion se investigo.

Causa: la alineacion del par se votaba **globalmente por casa**. Pero el orden
del par **cambia por liga**: en NCAAB casi todas las casas van INVERTIDAS
respecto a Bet365, y en NBA/WNBA/Euroliga esas mismas casas van alineadas, con
consistencias del 96-99% *dentro* de cada liga. Un voto global promedia las dos
convenciones y sale a cara o cruz (50-54%), dejando los pares orientados al
azar. Detalle y arreglo en `bball/analysis/alineacion.py`.

Verificacion del arreglo: con alineacion por (casa, liga) las 27 casas del feed
aciertan entre 61,70% y 70,69%; **antes, 12 de ellas caian al ~50%**.

Todo lo que sigue esta corrido con la alineacion correcta.

## RESULTADO (2026-09-03, tras el arreglo): REFUTADA
Reproducible: `python3 bball/analysis/orden_apertura.py`

### Puerta de sanidad: SUPERADA, y el dato es interesante
| | acierto | n |
|---|---|---|
| consenso de las casas que abrieron ANTES | **68.74%** (t=+32.0) | 6280 |
| Bet365 sobre esos mismos partidos | **68.77%** | 6280 |

El consenso previo predice **exactamente igual de bien que Bet365**. No es un
consenso tonto: es tan bueno como la casa. Y aun asi:

### ROI (nicho >=5 casas antes)
| version | e>=0% | e>=2% | e>=5% |
|---|---|---|---|
| **ANTES (ejecutable)** | **-9.58%** (n=2613, t=-2.46) | -10.20% | -8.91% |
| DESPUES (lookahead) | -2.20% (n=3204) | -1.21% | -4.59% |

Negativa en toda la escalera y en las dos mitades (-11.22% busqueda / -7.97%
reserva). Con >=8 casas antes, igual: -10.39%.

**Y el placebo la bate:** barajar el consenso da -5.83%, -6.50% y -5.62%,
todos MEJORES que el real (-9.58%). Es decir, apostar donde el consenso previo
discrepa de Bet365 es **peor que apostar al azar**.

### Lectura segun la tabla de cuatro casos declarada
Ni ANTES ni DESPUES ganan (la version con lookahead se queda en -2.20% y en el
mejor caso +0.52%). Por tanto: **no hay señal explotable por esta via**, y
tampoco es el caso de "la señal existe pero llega tarde".

El motivo queda claro y es mas fuerte que un simple "no sale": el consenso de
las casas previas acierta lo mismo que Bet365 (68.74% vs 68.77%). **Cuando dos
predictores igual de buenos discrepan, la discrepancia es ruido, no
informacion** -- y apostarla cuesta el margen. Por eso la seleccion sale peor
que el azar: elige sistematicamente los partidos donde el ruido es mayor.
