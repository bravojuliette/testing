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
