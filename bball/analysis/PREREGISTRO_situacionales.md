# Pre-registro: factores situacionales de calendario -> OVER

**Escrito el 2026-08-28, ANTES de analizar los datos de NCAAB con los que se
va a comprobar.** En el momento de escribir esto la recoleccion de NCAAB
esta en curso (861 partidos de diciembre 2025, sin `reparse-kickoff`
aplicado todavia) y NO se ha mirado ningun resultado suyo. Este documento
fija las hipotesis, el procedimiento y el criterio de decision para que el
resultado no se pueda reinterpretar despues.

## De donde sale

Sobre los 3021 partidos con cierre real (NBA, WNBA, Euroliga; temporadas
2024-25 y 2025-26), medido en el commit `db588a8`, ANTES de que entrara
ningun partido de NCAAB en la base:

| Estrategia | n | Cuota | Acierto | ROI | t | Beneficio | Peor racha | Drawdown |
|---|---|---|---|---|---|---|---|---|
| Altitud -> over | 101 | 1.91 | 61.0% | +16.1% | 1.75 | +16.3u | 5 | 5.1u |
| Viaje largo -> over | 109 | 1.91 | 61.5% | +17.1% | 1.92 | +18.6u | 4 | 5.4u |
| Las dos juntas | 202 | 1.91 | 60.2% | +14.6% | 2.24 | +29.6u | 7 | 7.1u |

Base fisica medida (desviacion del total final respecto a la linea de
cierre, en puntos):

| Grupo | desviacion media | % over |
|---|---|---|
| Todos los partidos | +0.80 | ~50% |
| Partido en altitud | **+5.54** | 61.0% |
| Visitante en viaje >=4 | **+1.33** | 61.5% |

**Motivos para dudar (por los que se hace este test):**

1. t = 1.75 y t = 1.92 individualmente estan POR DEBAJO del liston de t>=2.
2. El t = 2.24 conjunto sale de juntar dos efectos que ya habia visto por
   separado; juntarlos despues de verlos no es una prediccion, es un ajuste.
3. Altitud es solo NBA: n=101 sobre **dos equipos** (Denver y Utah). Podria
   ser estilo de juego de esas dos plantillas, no la altitud.
4. Llegue a esto mirando los datos. Necesita datos frescos, no los mismos.

## Hipotesis a comprobar (dos, fijadas aqui, sin variantes)

> **H1 (altitud).** Cuando el equipo LOCAL juega en un pabellon a >=1300 m
> de altitud, apostar **over** a la linea principal de cierre da ROI
> positivo.

> **H2 (viaje largo).** Cuando el equipo VISITANTE llega encadenando **>=4
> partidos consecutivos como visitante**, apostar **over** a la linea
> principal de cierre da ROI positivo.

Cada una se juzga por separado con su propio criterio. El conjunto de las
dos se reporta como dato, pero NO puede rescatar a ninguna de las dos: si
H1 y H2 salen refutadas por separado, el conjunto no las salva.

## Datos de comprobacion

Los partidos de **NCAAB** (y WNCAAB si llega a haber volumen) que se estan
recolectando ahora y que no participaron en ningun analisis previo.

NCAAB es un test especialmente exigente para H1: en la NBA la altitud son
dos equipos; en NCAAB hay decenas de universidades de montaña, muchas de
ellas a mas altura que Denver.

## Lista de equipos de altitud (CERRADA AQUI, antes de ver resultados)

Criterio: altitud de la ciudad del pabellon **>= 1300 m** (el suelo de la
pareja NBA que genero la hipotesis: Denver ~1609 m, Salt Lake City ~1300 m).
Altitudes tomadas de la ciudad sede, no del resultado de ningun partido.

**NBA:** DEN Nuggets, UTA Jazz.

**NCAAB — nombres ya presentes en la base:**
Adams State (Alamosa, 2299), Air Force (Colorado Springs, 2073), BYU (Provo,
1387), Colorado (Boulder, 1655), Colorado Christian (Lakewood, 1730),
Colorado Mesa (Grand Junction, 1400), Colorado School of Mines (Golden,
1730), Colorado State Pueblo (1430), Colorado-Colorado Springs (1900),
Denver (1609), Fort Lewis (Durango, 2012), Idaho St (Pocatello, 1370),
Metropolitan State (Denver, 1609), Montana State (Bozeman, 1468), Nevada
(Reno, 1373), New Mexico (Albuquerque, 1580), New Mexico Highlands (Las
Vegas NM, 1950), Northern Arizona (Flagstaff, 2106), Northern Colorado
(Greeley, 1443), Regis (Denver, 1609), Southern Utah (Cedar City, 1770),
Utah (Salt Lake City, 1400), Utah State (Logan, 1382), Utah Valley (Orem,
1387), Weber State (Ogden, 1310), Western Colorado (Gunnison, 2347),
Wyoming (Laramie, 2194).

**NCAAB — nombres aun no vistos en la base, pre-comprometidos por si
aparecen al terminar la recoleccion:**
Colorado State (Fort Collins, 1525), Colorado College (1839), Northern New
Mexico (Espanola, 1740), Western New Mexico (Silver City, 1800), Trinidad
State (1836), Otero (La Junta, 1250 -> NO, queda fuera), Lamar CC (1130 ->
NO, queda fuera).

**Explicitamente EXCLUIDOS por estar por debajo de 1300 m** (para que no
haya tentacion de meterlos despues si el resultado sale flojo):
Utah Tech (850), Idaho (790), Boise State (820), Montana (978), New Mexico
State (1190), Eastern New Mexico (1220), UTEP (1140), South Dakota Mines
(1030), Black Hills State (1100), Chadron State (1050), South Dakota (390).

Cualquier equipo cuyo nombre no aparezca en las listas de altitud de arriba
cuenta como **NO altitud**. No se añaden nombres despues de ver resultados.

## Procedimiento (fijado de antemano)

- Linea y cuota: snapshot `kickoff` (cierre real), **primera casa
  disponible** entre Bet365, Betway, BWin — en ese orden, sin elegir la
  mejor de las tres.
- Se apuesta **over a la linea principal**, no a peldaños alternativos.
- Se exige historial de **>=10 partidos previos** de ambos equipos, igual
  que en el analisis original.
- Viaje = partidos consecutivos como visitante contados hacia atras dentro
  de la temporada, usando solo partidos anteriores. Sin look-ahead.
- Stake plano de 1 unidad. Push (total = linea) cuenta como 0.
- Sin filtros adicionales, sin barrido de umbrales (ni el 1300 m ni el
  viaje >=4 se mueven), sin elegir liga ni periodo despues de ver los datos.

## Criterio de decision (fijado de antemano)

Para cada hipotesis por separado:

- **CONFIRMADA** si ROI > 0 **y** t >= 2 sobre los datos nuevos.
- **REFUTADA** en cualquier otro caso, incluido ROI positivo con t < 2.
- **NO CONCLUYENTE** si salen menos de **100 apuestas** para esa hipotesis.
  Con menos de eso no se rebaja el liston: se declara insuficiente y punto.

## Controles

Sobre los mismos datos nuevos, sin que afecten al veredicto principal:

- **Control fisico de H1.** La desviacion media respecto a la linea en
  partidos de altitud deberia reproducir algo parecido a **+5.54 puntos**.
  Si el ROI sale positivo pero la desviacion fisica NO aparece, es señal de
  que lo que hay es ruido y no un efecto de altitud.
- **Control fisico de H2.** Idem con **+1.33 puntos**.
- **Gradiente de altitud.** Si el efecto es real deberia ser mayor en los
  pabellones mas altos (>=1800 m) que en la franja 1300-1800 m. Es un
  control, no un filtro: no se usa para redefinir el umbral.
- **Gradiente de viaje.** Idem: viaje >=6 deberia ser al menos tan bueno
  como viaje >=4.
- **Placebo.** Local en viaje (no aplica) y visitante de altitud jugando
  fuera: no deberian mostrar nada.

## Compromiso

Se reporta lo que salga. Si sale refutada, **no se buscan subgrupos**
(liga, periodo, umbral de altitud distinto, longitud de viaje distinta,
peldaño alternativo) para rescatarla: eso convertiria estos datos en otra
ventana de busqueda y anularia el valor de este documento.

Precedente: el pre-registro de underdogs WNBA
(`PREREGISTRO_wnba_underdogs.md`) salio refutado con t = -2.10 y la celda
de control con +39.9% de ROI **no se investigo**. Aqui se aplica la misma
disciplina.

---

# ENMIENDA 1 (2026-08-28, con CERO resultados vistos)

## Que se ha visto antes de enmendar

Se corrio `veredicto_situacionales.py` sobre los 1518 partidos de NCAAB
recolectados hasta ahora (2025-12-01 .. 2025-12-20) y salio **n = 0 en las
dos hipotesis y en todos los controles**. No se ha calculado ni un solo ROI,
ni un solo acierto, ni un solo valor de t sobre datos de NCAAB. Lo unico
observado es un recuento de disponibilidad de muestra:

    equipos distintos en NCAAB: 823
    partidos por equipo hasta ahora: media 3.7, maximo 8
    partidos con >=10 previos de AMBOS equipos: 0
    partidos con  >=4 previos de ambos: 98
    partidos con  >=2 previos de ambos: 633

Esto es un hecho estructural del calendario universitario (800+ equipos, ~2
partidos por semana), no un resultado. La enmienda se hace por eso.

## Que cambia

**El requisito de >=10 partidos previos se elimina para estas dos
hipotesis.** Estaba heredado por copia de `situacionales.py`, donde hacia
falta porque alli se calculaban medias moviles de anotacion. **Ninguna de
las dos hipotesis usa medias de anotacion:**

- H1 solo necesita saber si el equipo local esta en la lista de altitud, que
  esta cerrada de antemano. No necesita historial ninguno.
- H2 solo necesita el contador de partidos consecutivos fuera. El propio
  umbral (>=4) ya exige haber observado 4 partidos de ese equipo, asi que
  se autolimita: no hace falta un requisito adicional.

Sesgo que introduce y en que direccion: una racha de viaje que empezara
antes del inicio de la ventana recolectada se cuenta truncada, asi que
algunos viajes largos reales se contaran como cortos y **se quedaran fuera**
de H2. Es un sesgo hacia PERDER apuestas validas, no hacia ganarlas. No
puede fabricar un falso positivo. Para reducirlo se añade **noviembre 2025**
a la recoleccion.

## Que NO cambia

El criterio de decision se mantiene intacto: **CONFIRMADA solo si ROI > 0 y
t >= 2**, REFUTADA en cualquier otro caso, NO CONCLUYENTE si n < 100. La
lista de equipos de altitud sigue cerrada, el umbral de viaje sigue en 4, la
casa sigue siendo la primera disponible entre Bet365/Betway/BWin, y la
prohibicion de rescatar por subgrupos sigue en pie.

## Por que esto no invalida el pre-registro

La distincion que hace que esta enmienda sea legitima y no una trampa: se
cambia un requisito de DISPONIBILIDAD DE MUESTRA, con n=0 y sin haber visto
ningun resultado. Si el cambio se hiciera despues de ver un ROI flojo y para
mejorarlo, seria justo lo contrario. Queda escrito aqui para que se pueda
comprobar el orden de los hechos en el historial de git.

---

# ENMIENDA 2 (2026-08-29): los datos de NCAAB estaban corrompidos de origen

## Que se descubrio

El feed de NCAAB de BetsAPI mezcla dos fuentes con convenciones opuestas de
local/visitante, sin ningun marcador que las distinga en el JSON:

- Partidos SIN cuotas (D2 y menores): el local guardado gana el **79.4%** — bien.
- Partidos con 10+ casas cotizando (la Division I): el local guardado gana
  el **35.9%** — invertidos casi en bloque.

Confirmado contra el mundo fisico con `/v1/event/view`: el evento 10722521
figura como `home=Rutgers, away=Michigan, ss=60-101`, y su estadio es el
**Crisler Center de Ann Arbor** — el pabellon de Michigan. El local real era
Michigan.

## Que significa para lo ya reportado

**La lectura intermedia del veredicto (H1 y H2 "refutadas" con n=113 y
n=145) se calculo sobre partidos mayoritariamente invertidos y NO vale.**
La muestra del veredicto son precisamente los partidos con cuotas, o sea la
poblacion invertida: el filtro "local en altitud" estaba midiendo en
realidad "el visitante es de altitud", y el contador de viajes contaba
rachas sobre roles al reves.

**Contaminacion que hay que declarar:** en esa lectura intermedia, la fila
que llamabamos placebo ("visitante de altitud jugando fuera") daba +13.8%
con t=1.45 — y con la orientacion invertida, esa fila era aproximadamente
la H1 verdadera. Es decir: al descubrir el bug, quedo a la vista una pista
de que la H1 corregida podria salir positiva. No se puede des-ver. Se
declara aqui para que el lector del veredicto final lo pondere: el proceso
ya no es un pre-registro quimicamente puro, y si el resultado final queda
cerca del liston, esta contaminacion es un motivo mas de escepticismo, no
menos.

## Que cambia en el procedimiento

1. **La altitud pasa a medirse por el ESTADIO, no por el equipo local:**
   `/v1/event/view` da estadio y ciudad de cada partido. "Partido en
   altitud" = ciudad del estadio a >=1300 m, con la MISMA lista de
   ciudades/umbrales ya cerrada en el pre-registro original. Esto es mas
   fiel a la hipotesis fisica original (el efecto es del pabellon, no del
   nombre del equipo) y ademas trata bien las canchas neutrales.
2. **El local/visitante de cada partido de NCAAB se corrige con el estadio
   modal de cada equipo** (el pabellon mas frecuente en sus partidos es su
   casa): si el estadio del partido es la casa del visitante listado, el
   partido esta invertido y se corrige; si no es la casa de ninguno, se
   marca neutral y queda FUERA de H1-por-equipo y de los contadores de
   viaje (un torneo neutral no es un viaje de carretera clasico, pero
   tampoco es jugar en casa; excluirlo es lo conservador).
3. **Los criterios de decision NO cambian:** ROI > 0 y t >= 2, por
   hipotesis y por separado; n >= 100; sin subgrupos, sin umbrales nuevos.

## Orden de los hechos, para el historial

Este documento se commitea ANTES de recolectar los estadios y antes de
recalcular nada sobre datos corregidos. Lo unico visto hasta ahora sobre
datos de NCAAB: la lectura intermedia invalida descrita arriba, y los
recuentos de orientacion (79.4% / 35.9% / Crisler Center) que motivaron
esta enmienda.
