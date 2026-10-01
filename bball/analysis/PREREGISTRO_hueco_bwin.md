# PRE-REGISTRO: el HUECO de bwin contra bet365 en vivo (totales)

Escrito el 2026-09-01 DESPUES de encontrar el efecto. Se declara POST-HOC sin
rodeos: no estaba pre-registrado, salio de trocear los resultados del lead-lag
buscando una casa jugable desde España. Por eso nace en CUARENTENA y no se
apuesta un euro hasta la confirmacion prospectiva de aqui abajo.

## La regla, en una linea
Mirar el total EN VIVO de bet365 y el de bwin en el mismo partido. Cuando la
linea de bwin esta >= 3 puntos POR DEBAJO de la de bet365, apostar OVER en bwin
a su cuota vigente. (bwin es legal en España; bet365 tambien, pero aqui solo se
OBSERVA -- no hace falta cuenta en la casa de referencia.)

## Lo medido (1495 partidos cosechados, 558 con las dos casas)
Escalera de frescura -- se exige que la entrada de bwin tenga como mucho N
segundos de antiguedad en el momento de apostar:

| frescura | ref. bet365 | ref. 1xbet |
|---|---|---|
| 300s | +7.5% (t=10.6) n=16680 | +8.1% (t=12.5) n=20255 |
| 60s | +7.3% (t=10.1) | +8.0% (t=12.3) |
| 20s | +7.5% (t=10.2) | +8.2% (t=12.3) |
| **10s** | **+7.1% (t=9.3) n=14475** | **+8.1% (t=11.7) n=17487** |

Mismo signo en busqueda y reserva (corte 2026-03-11) en TODOS los niveles.
A 10 segundos el precio esta vivo por definicion: **no es el artefacto de
precios rancios** que mato el frente kickoff-outlier en agosto (alli el efecto
se evaporaba al exigir frescura; aqui no se mueve).

**Asimetria NO predicha, y es casi todo el efecto:**
OVER (bwin corto) n=6950 ROI **+15.6%** acierto 62.5% | UNDER (bwin largo)
n=8808 ROI +1.1% acierto 54.4%. Cuota media 1.857 -> punto muerto 53.8%, o sea
el lado UNDER apenas lo roza. La ventaja vive en que la linea de bwin se queda
CORTA, no en que se desvie.

## Controles ya pasados
- **No es desajuste de mercado.** Dentro del mismo partido bwin y bet365
  coinciden: diferencia mediana +0.0, p10 -0.5, p90 +1.0, CERO partidos con
  |dif| > 20. El 171.5 vs 220.5 de las medianas globales era mezcla de ligas
  (bwin cubre WNBA/Euroliga; bet365 ademas NBA). Se comprobo expresamente
  porque un desajuste de mercado habria explicado todo el efecto.
- **No es rancidez.** Sobrevive intacto de 300s a 10s.
- **No es cadencia.** bwin publica ~1900 entradas en juego por partido: es la
  casa MAS rapida del estudio, no la lenta. El efecto no puede venir de que
  bwin este muestreada de forma gruesa.
- **Filtro de entrelazado aplicado** (marcador monotono, ENMIENDA 2 del
  pre-registro del lead-lag): bwin descarta el 22.4% de sus entradas por
  reemisiones rancias, y aun asi el efecto queda.

## Lo que NO esta comprobado, y es lo que decide si vale dinero
1. **Que bwin acepte la apuesta a ese numero en vivo.** Un hueco de 3 puntos
   entre dos casas es justo lo que una casa corrige en segundos. El feed dice
   que el precio existia; no dice que dejaran ponerle dinero, ni cuanto.
2. **Limites y limitacion de cuenta.** Un +15% en vivo repetido es exactamente
   el perfil que las casas limitan.
3. **Que el efecto siga vivo hacia delante.** Todo lo anterior es historico.

## CONFIRMACION PROSPECTIVA (criterio fijado AQUI, antes de que exista el dato)
- Datos: partidos de WNBA/Euroliga/NBA del **2 al 30 de septiembre de 2026**,
  cosechados con `cosecha-src` (bet365 + bwin), que NO existen hoy.
- Regla congelada: la de arriba, umbral 3.0, frescura <= 20s, lado OVER.
- CONFIRMADA: ROI > 0 con t >= 2 y n >= 300, y el lado OVER por encima del
  UNDER como aqui. Sin tocar el umbral ni la frescura para que salga.
- REFUTADA: cualquier otra cosa. NO CONCLUYENTE solo si n < 300.
- Y aunque CONFIRME: sigue sin ser apostable hasta que el usuario verifique en
  la web de bwin, en vivo y con importe pequeño, que la apuesta entra.

## Aviso que va por delante de cualquier cifra
Este proyecto ha matado hoy cuatro efectos de dos digitos (rancidez +78%,
cadencia +40%, entrelazado, y el lead-lag entero). Todos parecian esto. La
diferencia aqui es que sobrevive a los controles que mataron a aquellos -- lo
cual lo hace el mejor candidato que hemos tenido, NO lo hace un sistema.

## CORRECCION del estadistico y datos de EJECUCION (2026-09-01, mismo dia)

### El t estaba inflado: las apuestas NO son independientes
Las 7.099 apuestas del lado OVER salen de 556 partidos -> **12,8 apuestas por
partido**. Doce apuestas dentro del mismo partido son la misma situacion
repetida, no doce pruebas. Agregando a UN dato por partido:

| forma de contar | ROI | t |
|---|---|---|
| cada apuesta (lo publicado arriba) | +15,4% | **+14,4** |
| cada PARTIDO (lo correcto) | +9,0% | **+2,92** |

Sigue pasando el liston (t>=2) pero por poco. La cifra honesta es **t=2,92**,
no 9,3 ni 14,4. Toda lectura de este pre-registro debe usar la de partidos.

### Frecuencia, banca y riesgo (556 partidos con ambas casas, ~6 meses)
- Señal en el **99%** de los partidos; mediana de 11 apuestas por partido.
- P&L por partido: media **+1,96 unidades**, mediana +2,27, desviacion 10,75.
- Solo el **58% de los partidos** acaba en positivo. Peor partido: -38 uds.
- Total del periodo: +1.090 unidades.
- Racha adversa (200 remuestreos): tipica **-106 uds**, y -150 en el 10% malo.
  Con banca por debajo de ~150 unidades te arruinas antes de que el edge se
  manifieste, aunque el edge sea real.

### LA VENTANA: el hueco dura 15 segundos
Medido sobre 7.077 huecos, tiempo hasta que se cierra:
p10 **3s** | p25 **7s** | **MEDIANA 15s** | p75 32s | p90 70s.
Solo el **12%** sigue abierto pasado un minuto; el 6% pasados dos.

**Consecuencia:** la operativa manual es imposible. La cadena bwin mueve ->
BetsAPI publica -> sondeo -> aviso -> abrir app -> apostar son minutos, y el
hueco lleva cerrado un cuarto de hora en tiempo de mercado.

**Y la hipotesis incomoda que esto abre:** si el hueco solo dura 15 segundos,
es muy posible que "gane" precisamente porque NADIE puede cogerlo -- un precio
real pero inalcanzable. Seria el artefacto de agosto en su version refinada: no
un precio rancio, sino uno vivo y fuera de alcance. La prueba manual del
usuario no mide si gana, mide **si llega**.

---

## 1-oct-2026: la confirmacion NO se ha podido correr (POSPUESTA)

**Esto no es un veredicto.** No es CONFIRMADA, no es REFUTADA y no es NO
CONCLUYENTE: el criterio de arriba decide sobre datos, y no hay datos. El
candidato sigue en CUARENTENA con el criterio intacto, sin tocar el umbral de
3.0 ni la frescura de 20s ni el lado OVER.

### Por que
El paso 1 (recolectar los partidos del 2 al 30 de septiembre) es imposible:
BetsAPI devuelve **403 PERMISSION_DENIED** (`"Check Coverage on
betsapi.com/mm/pricing_table"`). Re-sondeado hoy, 1-oct, con `--no-cache`
sobre `/v3/events/ended`: el mismo 403 (run 36833759402). Es la cobertura de
la cuenta, no un endpoint ni un limite de ritmo; el diagnostico completo y las
cuatro sondas del 28-sep estan en `BLOQUEO_BETSAPI.md`.

### Lo que se comprobo antes de darlo por imposible
- `bball_odds_hist` (la serie POR CASA que necesita la regla) **no existe en
  Turso**: vive solo en los volcados locales de `data_local/`.
- Los volcados que hay en la rama son todos de la cosecha previa al 1-sep
  (`bball_cosecha_grande`, `_recientes`, `_piloto`, NBA, Euroliga, chicas).
  Es decir: **no hay ni una muestra prospectiva parcial** que correr. El
  pre-registro exigia datos "que NO existen hoy [1-sep]" y eso sigue siendo
  literalmente cierto.
- Tampoco se va a correr la regla sobre los datos viejos: eso seria volver a
  medir in-sample el efecto que ya encontramos ahi, que es exactamente lo que
  la cuarentena existe para evitar.

### Lo que esto cuesta, dicho claro
La ventana del 2 al 30 de septiembre es historia. Cuando vuelva la cobertura,
`/v3/events/ended` si acepta dias pasados, asi que en principio se puede
recuperar; **pero la serie en vivo por casa de `/v2/event/odds` puede tener
retencion limitada**, y si BetsAPI ya no la sirve para septiembre, esa ventana
se pierde para siempre y habra que fijar una ventana prospectiva NUEVA (con el
mismo criterio, sin reabrir ningun parametro).

Re-sondeo programado: 15-oct. Si para entonces la cobertura sigue caida, se
vuelve a posponer; el criterio no se mueve.
