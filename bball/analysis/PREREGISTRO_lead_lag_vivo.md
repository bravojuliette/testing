# PRE-REGISTRO: LEAD-LAG EN JUEGO entre casas (totales, serie propia por casa)

Commiteado el 2026-09-01, ANTES de correr ningun P&L sobre estos datos. Lo
unico que se ha mirado del dato nuevo es el CONTEO de entradas por casa y
partido (la tabla del sondeo de fuentes) -- nunca una linea contra un
resultado. El criterio queda fijado aqui y el timestamp del commit es el
notario, como en los pre-registros anteriores.

## Que hace medible este test (y por que no lo era hasta hoy)
El medidor `lead_lag.py` quedo restringido a fotos PRE-PARTIDO (ENMIENDA 2)
porque en juego las lineas por casa venian del resumen congelado. Hoy se
comprueba que `/v2/event/odds` acepta `source` y devuelve la serie PROPIA de
cada casa con marcador en cada entrada, hacia atras 22 meses. Es decir: la
serie en vivo por casa SI existe, es historica y es retroactiva. Se cosecha
con `cosecha-src` a `bball_odds_hist` con la columna `source` rellena.

## Hipotesis
Cuando una casa mueve su linea de total en vivo y otra todavia no, la
segunda cotiza un precio VIEJO. Apostar el lado hacia el que se movio la
primera, EN la casa rezagada, tiene ROI > 0. No requiere predecir baloncesto:
requiere que una casa sepa antes que otra, que es un liston mucho mas bajo.
Es la Teoria 2 del programa, y la celda fresca de Euroliga del test de
outlier-vs-consenso apunto a ella (cuando la desviada tenia foto FRESCA,
apostar CONTRA ella perdia -25/-30%: la que se mueve primero suele acertar).

## EL CONFUNDIDOR QUE HAY QUE DECLARAR ANTES: la CADENCIA DE MUESTREO
Las casas no publican al mismo ritmo. En el mismo partido (11963837, WNBA
2026-08-30) bwin trae 5207 entradas en 18_3 y bet365 337. Una casa muestreada
15 veces mas fino aparecera SIEMPRE "moviendose primero" por pura
granularidad, sin saber nada antes que nadie. Este es el mismo genero de
artefacto que ya mato dos frentes (precios rancios en outlier-consenso;
resumen congelado en lead-lag pre-partido) y se controla ANTES, no despues:

1. **SIMETRIA (control principal).** El estadistico se calcula en las DOS
   direcciones para cada par de casas: A->B y B->A. Un lead-lag real es
   ASIMETRICO (una gana, la otra pierde). Si las dos direcciones salen
   positivas y significativas, es artefacto de cadencia y el par se descarta,
   por bonito que sea el ROI.
2. **PLACEBO (obligatorio, heredado de la ENMIENDA 1).** Se reasigna al azar
   quien es "lider" manteniendo el resto del procedimiento. El ROI real debe
   superar la distribucion del placebo; si no, no hay senal.
3. **CADENCIA EMPAREJADA.** Se reporta la ratio de entradas por partido de
   cada par. Un resultado que solo aparece en pares con ratio > 3 y se cae en
   los pares de cadencia parecida es artefacto, no ventaja.

## Procedimiento
- Datos: `bball_odds_hist` con `source IS NOT NULL`, mercado 18_3, entradas
  con `ss` no vacio (en juego), de partidos completados con total final.
- Fuentes: las que tengan serie en vivo (bet365 seguro; bwin/1xbet segun
  cobertura, que se mide con la cosecha piloto ANTES de correr esto).
- Senal: en el instante t en que la casa A publica una linea que difiere de
  su anterior en >= UMBRAL puntos, se mira la ultima linea publicada por la
  casa B en o antes de t. Si B sigue >= UMBRAL puntos por detras del nuevo
  valor de A, se compra EN B el lado hacia el que A se movio (A baja su
  total -> UNDER en B; A sube -> OVER en B), a las cuotas de la entrada
  vigente de B. UMBRALES declarados: 1.0, 2.0 y 3.0 puntos (dosis-respuesta:
  si el mecanismo es real el ROI no puede invertirse al subir el umbral).
- Liquidacion: contra el total final real del partido. Push (final == linea)
  excluido. Cuotas exigidas en [1.01, 20].
- Una apuesta por (partido, par de casas, senal); sin re-entrar mientras el
  desfase no se cierre y vuelva a abrirse.
- Reloj: `add_time` de cada entrada. Se descartan pares cuyos `add_time`
  disten mas de 300s (no se puede afirmar quien fue primero con esa holgura).
- ZOMBI (regla del usuario, 2026-08-30): se exige que cada casa del par tenga
  >= 2 cambios de linea distintos dentro del partido.
- Split busqueda/reserva por mediana de fecha, como siempre.

## Criterios (los de siempre, sin rescates)
- CONFIRMADA una celda (par de casas x umbral): ROI > 0, t >= 2, n >= 100,
  MISMO signo en busqueda y reserva, dosis-respuesta no invertida, ROI por
  encima del placebo, y **direccion contraria NO significativa** (simetria).
- NO CONCLUYENTE: n < 100.
- REFUTADA: el resto. Un fallo del control de simetria NO es rescatable.

## Aviso economico declarado ANTES (para no venderlo mejor de lo que es)
Una casa que republica 5000 veces por partido no deja poner dinero a un
numero concreto durante minutos: aunque el test CONFIRME, la ejecucion real
depende de tener cuenta abierta en la casa lenta, de que acepte el importe en
vivo y de que no limite. Se anadira una sensibilidad (NO primaria, porque
mira al futuro y por tanto sesga a favor de no encontrar nada) exigiendo que
el precio de B sobreviva >= 30s tras la senal, como cota inferior honesta de
lo que se podria haber llegado a jugar.

## ENMIENDA 1 (2026-09-01, declarada ANTES de correr nada): control de GAP PURO
Escribiendo el codigo aparece un confundidor mas fuerte que el de cadencia, y
se declara antes de mirar resultados porque solo puede hacer mas dificil
confirmar, nunca mas facil.

La regla "B esta lejos de la linea nueva de A, apuesto en B hacia A" es, en
el fondo, apostar hacia la linea MAS FRESCA de las dos. Y en vivo la linea
fresca esta mas cerca del ritmo ya realizado por puro paso del tiempo, sin que
nadie "lidere" nada. Es el mismo veneno que mato al frente outlier-consenso
(precios rancios), con otro disfraz.

Control: se corre la MISMA apuesta sin exigir que A se acabe de mover -- solo
que B lleve >= UMBRAL de retraso respecto a la linea vigente de A en ese
instante (GAP PURO). Si el ROI condicionado al movimiento de A no supera
claramente al del gap puro, NO hay lead-lag: hay rancidez, y la ventaja
pertenece al reloj, no a la casa. Se reporta siempre junto al principal.

## Validacion del arnes contra fixtures sinteticas (2026-09-01, antes del dato real)
Cuatro mundos construidos a mano, con el medidor corrido tal cual. Cada
artefacto lo caza un control DISTINTO -- por eso hacen falta los tres:

| fixture | que simula | REAL | INVER | PLAC | GAP | lo caza |
|---|---|---|---|---|---|---|
| nula | dos caminos independientes | +0.6/+3.5% t<1.7 | igual | igual | +3/+9% | nada que cazar |
| rancidez | B = A retrasada (nadie lidera) | +64/+78% t=51 | -47% | +64/+81% | **+59/+85% t=125** | GAP y PLAC |
| cadencia | misma info, A publica 8x mas fino | +40/+63% | **+76/+81%** | +46/+62% | +37/+75% | SIMETRIA |
| senal | A conoce antes el total | +90% | -16% | +90% | +78/+90% | (pasa, como debe) |

Lecturas que fijan como se leera el dato real:
1. La **rancidez pura da +78% con t=51 y una asimetria preciosa** (INVER
   -47%). Sin la ENMIENDA 1 se habria vendido como lead-lag confirmado. Es el
   resultado mas importante de esta validacion.
2. La **cadencia da +40% con las DOS direcciones positivas**: el control de
   simetria es el unico que la caza, y la ENMIENDA 1 sola no habria bastado.
3. En la fixture de senal el placebo tambien sale +90%: cuando A salta MUCHO,
   la direccion del salto es redundante con el tamaño del desfase. Es decir,
   un PLAC alto no basta para descartar, pero un PLAC alto CON un GAP igual de
   alto si: la senal no aporta nada sobre el simple retraso.
4. `t_pnl` devuelve 0.00 cuando todas las apuestas ganan (varianza nula). Es
   un artefacto de la fixture perfecta; con cuotas reales no ocurre.

### Precision del veredicto (declarada aqui, antes de ver ROI real)
Si GAP sale rentable y REAL no lo supera, el veredicto NO es "no hay nada":
es que **no hay LEAD-LAG, hay RANCIDEZ** -- una estrategia distinta, cuyo
cuello de botella no es adivinar quien manda sino si ese precio viejo se
podia jugar de verdad. Ese caso se juzga con la sensibilidad de
supervivencia >= 30s ya declarada, y no se llamara lead-lag confirmado.

## ENMIENDA 2 (2026-09-01, tras la cosecha piloto, ANTES de correr ROI real): series ENTRELAZADAS
La comprobacion de sanidad sobre el dato cosechado (200 partidos WNBA,
82.220 entradas en juego de bet365) revela que **la serie 18_3 de una casa no
es una serie**: entrelaza la linea viva con lineas alternativas CONGELADAS que
siguen reemitiendose arrastrando el marcador con el que se fijaron.

Evidencia literal (evento 4588488, ventana contigua): un flujo avanza
(ss 53:63 -> 54:63 -> 55:63, linea 204.5) mientras otro repite segundo a
segundo `ss=42:50, linea=199.5, cuotas 1.952/1.8`, inmovil durante minutos.
Leido como una sola serie, "la linea de bet365" oscila 5 puntos a 1 Hz.

**Filtro (principiado, no parche):** el marcador de baloncesto nunca baja, asi
que toda entrada cuyo marcador sea INFERIOR al maximo ya visto en esa
(evento, casa) es una reemision rancia y se descarta.

Efecto en ese evento: 887 -> 454 entradas; salto mediano entre entradas
consecutivas 2.00 -> 0.00 puntos; maximo 13.0 -> 5.0; pasos con salto >=2
puntos 572/886 (65%) -> 89/453 (20%). La serie reconstruida es monotona y
coherente (168.5 con 0:0 hasta 215.5 con 104:96, siempre por encima de lo ya
anotado).

**Magnitud real, para no exagerarlo:** en los 200 partidos la contaminacion
es una COLA, no la norma. Entradas descartadas por partido: mediana 0.6%,
p75 1.7%, p90 3.4%, maximo 48.8%. Solo el 6% de los partidos pasa del 5% y
el 4588488 es el peor de los 200. Aun asi el filtro es obligatorio: una sola
linea fantasma de 13 puntos fabrica una senal de libro, y el test se juega
justo en esos saltos grandes. Queda por medir si bwin (5207 entradas por
partido) esta mucho peor.

Nota lateral: el separador del marcador en el feed por-fuente es `:`
(15:9), no `-`. `suma_ss` de este modulo acepta los dos.

## Cobertura medida (piloto, 200 partidos mas ANTIGUOS del fichero)
bet365 tiene serie en juego en los 200; 1xbet y bwin, en NINGUNO (no existian
como fuente en 2022). **0 partidos con >=2 casas: ese tramo no sirve para un
test de pares.** El pre-registro no cambia; lo que cambia es donde hay
muestra. Se mide la cobertura en el tramo RECIENTE contra las 12 fuentes
candidatas antes de decidir el alcance de la cosecha completa.

## Diagnostico previo sobre el tramo RECIENTE (100 partidos, 2026), antes de correr ROI
Cobertura: **100 de 100 partidos con >=3 casas con serie EN JUEGO** (bwin,
1xbet, bet365; unibet en 15). betfair, williamhill, betway, 188bet y betfred
no devuelven nada; sbobet, dafabet y ladbrokes devuelven filas pero NINGUNA
en juego. Lista definitiva de fuentes: bet365, 1xbet, bwin (+unibet donde
haya). El test tiene potencia de sobra en este tramo.

### Contaminacion por entrelazado (lo que descarta el filtro de la enmienda 2)
| fuente | mediana | p75 | p90 | max | partidos >10% |
|---|---|---|---|---|---|
| 1xbet | 0.8% | 1.4% | 2.7% | 8.5% | 0/100 |
| bet365 | 8.9% | 11.8% | 14.8% | 17.9% | 38/100 |
| **bwin** | **22.4%** | 24.3% | 26.0% | 29.4% | **100/100** |
| unibet | 5.0% | 9.8% | 12.5% | 12.5% | 1/8 |

En el tramo WNBA-2022 la contaminacion de bet365 era del 0.6%; aqui es del
8.9%, y bwin tiene UNA DE CADA CINCO entradas rancias en todos y cada uno de
los 100 partidos. Sin el filtro de la enmienda 2 el test sobre bwin habria
sido basura pura. Queda claro que el filtro no es una precaucion teorica.

### Cadencia (el confundidor principal declarado)
| fuente | entradas en juego por partido (mediana) | ratio vs bet365 |
|---|---|---|
| bwin | 5732 | **x13.7** |
| 1xbet | 447 | x1.1 |
| bet365 | 419 | x1.0 |
| unibet | 56 | x0.1 |

**Consecuencia, fijada aqui antes de ver un solo ROI:** el par
**bet365 <-> 1xbet esta EMPAREJADO en cadencia (x1.1)** y es el par LIMPIO
del test -- el unico donde un resultado positivo no puede explicarse por
granularidad de muestreo. Todo par que incluya a bwin arrastra un desfase de
cadencia de x13.7 y nace sospechoso: en ese par, el control de simetria es
decisorio, no informativo. Se reportan todos los pares, pero el veredicto
principal se lee en bet365<->1xbet.

## RESULTADO (2026-09-01, corrido UNA sola vez sobre el dato completo)

Cosecha: 1495 partidos con >=2 casas con serie EN JUEGO; 3,93 millones de
filas en juego (bwin 2.366.176 / bet365 696.432 / 1xbet 719.315 / unibet
58.602). Corte busqueda/reserva 2026-03-11. 12 pares x 3 umbrales.

### El par LIMPIO (bet365 <-> 1xbet, cadencia 384 vs 513 = x1.3)
| celda | REAL | INVER | PLAC | GAP | S / R |
|---|---|---|---|---|---|
| 1xbet->bet365 u>=1 | **-1.8%** t=-6.9 | +1.1% | -1.8% | -2.7% | -3.4/-0.2 |
| 1xbet->bet365 u>=2 | +2.3% t=4.0 | +3.6% t=6.3 | +2.6% | +1.1% | **-2.8/+7.3** |
| 1xbet->bet365 u>=3 | +7.2% t=6.1 | **+5.0% t=3.4** | **+7.8%** | +4.8% | +2.8/+11.2 |
| bet365->1xbet u>=2 | +3.6% t=6.3 | **+2.3% t=4.0** | **+4.2%** | +3.6% | +2.0/+5.7 |
| bet365->1xbet u>=3 | +5.0% t=3.4 | **+7.2% t=6.1** | +3.9% | **+7.0%** | +1.3/+9.6 |

Ninguna celda del par limpio sobrevive: o cambia de signo entre mitades, o
enciende la SIMETRIA (las dos direcciones positivas y significativas a la vez
-- imposible en un lead-lag real), o el PLACEBO iguala o supera al REAL.

### El hecho que lo decide, y vale para TODOS los pares
**El PLACEBO iguala o supera al REAL en todas las celdas rentables.** Sin
excepcion. Aleatorizar la direccion en la que se movio el "lider" produce el
mismo dinero que seguirla. Ejemplos: bwin->bet365 u>=3 REAL +11.1% vs PLAC
**+15.2%**; 1xbet->bwin u>=3 REAL +16.3% vs PLAC **+16.7%**; bet365->unibet
u>=3 REAL +14.3% vs PLAC **+17.3%**; bwin->unibet u>=3 REAL +10.7% vs PLAC
**+11.4%**. Saber hacia donde se movio la casa que va primero NO APORTA NADA.

Las dos celdas que pasan la simetria (bwin->bet365 u>=3, INVER +0.3% t=0.46;
1xbet->bwin u>=3, INVER +0.8% t=1.15) caen igualmente por placebo. Se dejan
anotadas para que conste que no se descartaron mirando a otro lado.

### Y la firma del artefacto es exactamente la predicha
Los ROI grandes viven en los pares con MAS desfase de cadencia: unibet (37
entradas/partido, x0.1) y bwin (1905, x5). El par emparejado (x1.3) es el que
menos rinde y el que enciende la simetria. Justo lo que la fixture "cadencia"
anticipo el 2026-09-01 antes de ver un solo dato real.

## VEREDICTO: REFUTADO como LEAD-LAG.
No hay ninguna ventaja en seguir a la casa que se mueve primero. Lo que hay es
RANCIDEZ: el dinero sale del hueco entre una linea vieja y una fresca, no del
movimiento. Es lo que la ENMIENDA 1 declaro por adelantado que se leeria asi.

### Lo que SI queda medido (y por que no lo vendo como sistema)
El GAP PURO -- apostar contra la casa rezagada sin esperar a que nadie se
mueva -- rinde +13.1% con t=+29.3 (n=41.552) en bet365->unibet u>=3, y
+9.8% t=+23.4 en bwin->unibet. Es un efecto enorme y consistente.
Pero su cuello de botella NO es estadistico:
- unibet publica 37 entradas por partido: su "linea" es un numero que se queda
  quieto largos ratos. Que ese precio siguiera realmente disponible EN VIVO es
  justo lo que el feed no puede decir.
- Es la misma familia de artefacto que ya mato el frente kickoff-outlier
  (precios rancios que no eran apostables a ese precio en ese momento).
Declarar esto "sistema ganador" seria repetir el error de agosto con otro
disfraz. Queda en CUARENTENA como hipotesis de EJECUCION, no de estadistica:
solo se resuelve comprobando en la web de la casa, en vivo y con dinero
pequeño, si esa linea rancia se deja jugar. Ninguna cantidad de datos
historicos puede responder eso.

## Desglose POR LIGA (declarado en el pre-registro; corrido con el pooled)
Euroliga (253 partidos) reproduce el patron del pooled en el par limpio:
1xbet->bet365 u>=3 REAL +9.4% t=2.52 con INVER +10.8% t=2.81 (simetria
encendida) y PLAC +10.6%; bet365->1xbet u>=3 REAL +10.8% con INVER +9.4% y
PLAC +13.0%. Mismo veredicto.

### La UNICA celda que no se pliega limpiamente, y por que sigue sin valer
**bwin -> unibet, Euroliga, u>=1** (253 partidos):
REAL +7.5% t=+21.1 (S +6.8 / R +8.4, mismo signo) | **GAP +0.3% t=+0.6** |
PLAC +7.3% t=+15.5 | INVER +0.1% t=+0.04.

Es la unica celda donde REAL supera de largo al GAP: el hueco por si solo no
paga nada y, sin embargo, condicionar a que bwin ACABE de moverse paga +7.5%.
Leido literalmente: que la casa rapida se mueva avisa de que la lenta esta
descolocada, pero la DIRECCION en que se movio no aporta nada (placebo igual).

No se rescata, por tres razones declaradas:
1. **Falla el criterio pre-registrado** (REAL debe superar al PLACEBO). Y aqui
   PLAC = REAL, asi que lo que sea que haya, no es seguir al lider.
2. **La simetria no PASA aqui: es que no se puede medir.** INVER tiene n=982
   frente a los 68.371 de REAL, porque unibet casi nunca se mueve. Un INVER no
   significativo con 70 veces menos muestra no es evidencia de asimetria.
3. Es el par con MAS desfase de cadencia de todo el estudio (bwin 1905 vs
   unibet 37 entradas/partido = **x51**). Con bwin publicando cada pocos
   segundos, "bwin acaba de moverse" es casi siempre cierto, asi que REAL/PLAC
   miden el hueco en los momentos en que bwin esta activo -- y bwin se activa
   justo cuando el partido se mueve, que es cuando la linea de unibet esta peor.
   Confundidor de temporizacion, no ventaja.

### Limitacion del PLACEBO, dicha aqui y no escondida
Tal como esta implementado, el placebo aleatoriza la DIRECCION del movimiento
del lider pero el lado apostado lo sigue fijando el signo del hueco. Es decir,
aisla bien "¿importa hacia donde se movio?" pero NO es independiente de la
senal real. Por eso el control que manda en el veredicto es el GAP, que si es
independiente, y por eso se anadio en la ENMIENDA 1.
