# PRE-REGISTRO: ¿cuantas casas hacen falta para cruzar el cero?

Escrito el 2026-09-03 ANTES de calcular estos ROI. Extension declarada de
PREREGISTRO_mejor_precio.md, que dejo el mejor precio de 2 casas legales en
-0.45% (t=-0.36) sobre favoritos cortos -- a medio punto del equilibrio.

## La pregunta
Con las 22 casas del feed (no solo las 3 legales), el mejor precio de N casas
es monotono creciente en N. Se traza la curva ROI(N) para N = 2,3,4,6,8,12,22
sobre NCAAB moneyline de apertura, por cubos de cuota.
- Si la curva cruza el cero en algun N, ese N es el numero de cuentas que
  haria falta, y la pregunta pasa a ser si existen N casas legales en España.
- **Si NO cruza el cero ni con las 22, el line shopping queda descartado
  definitivamente** y no hay que buscar mas casas: no es cuestion de cuentas.

## Por que esto es una COTA SUPERIOR (y por eso decide)
Las capturas de distintas casas distan 19.4h de mediana. El maximo sobre una
ventana ancha solo puede ser IGUAL O MEJOR que un maximo simultaneo real.
Ademas se toma el maximo sobre casas que el usuario no puede usar. Luego:
- curva que no cruza el cero -> el line shopping REAL tampoco lo cruza.
  Conclusion firme, y negativa.
- curva que si cruza -> NO demuestra nada por si sola; solo dice donde
  mirar, y exigiria capturas simultaneas para confirmarlo.

## Criterio
No hay "CONFIRMADA" posible en este test, por lo dicho arriba: es un
descarte. Solo tiene dos salidas: **DESCARTADO** (no cruza) o **ABIERTO con
N** (cruza en N, y queda pendiente de verificacion con capturas simultaneas).
Se exige n >= 300 por celda para leerla.

## HALLAZGO DE INTEGRIDAD encontrado al correrlo (y que invalidaba la primera pasada)
La primera pasada dio numeros absurdos (-80% en cuotas cortas, **+242%** en
largas). No era un hallazgo: **las casas no guardan el par del moneyline en el
mismo orden**. Alineando cada casa contra Bet365 SOLO POR PRECIOS (nunca por
resultados): **16 de 19 casas estan invertidas**, con consistencia del 95-99%
--  es convencion por casa, no ruido. Duelbits 96.9%, CloudBet 97.1%, Coral y
Ladbrokes 99.3%, Pinnacle 97.1%... Alineadas, la sanidad cuadra: el favorito
gana el 70.3% (n=75.766).

Nota: `PREREGISTRO_mejor_precio.md` uso solo Bet365 y BWin, que estan
alineadas entre si (BWin invertida el 4.6%), asi que aquel resultado SI era
sano. Pero cualquier analisis futuro entre casas en este dataset debe alinear
primero o producira ROIs de tres cifras que no existen.

## RESULTADO (1a pasada, ad-hoc): ABIERTO con N
Trazada la curva ROI(N) del mejor precio de N casas sobre NCAAB moneyline de
apertura (n=5.713 partidos, 22 casas alineadas), la curva es monotona y en
cuotas cortas pasa de -4.1% con 1 casa a **+2.9% con 12**. Cruza el cero
entre N=6 y N=8, abriendo cuentas por orden de cobertura.

| N | [1.01,1.40) | [1.40,2.20) | [2.20,20) |
|---|---|---|---|
| 1 | -4.08% | -6.87% | -24.38% |
| 2 | -3.43% | -4.99% | -14.63% |
| 3 | -1.03% | -3.15% | -6.50% |
| 4 | -0.46% | -3.06% | -2.34% |
| 6 | -0.45% | -2.94% | -1.76% |
| **8** | **+2.65%** | +0.56% | +4.73% |
| 12 | +2.90% | +2.20% | +6.37% |

(La primera version ad-hoc de esta tabla, ya corregida aqui, decia que cruzaba
en N=4. Elegia las N casas por orden alfabetico, que es arbitrario y ademas
cambia que partidos califican. `cuantas_casas.py` las elige por cobertura --
el orden en que un apostante real abriria cuentas -- y el cruce se va a N~8.
El punto de cruce no era robusto; la forma de la curva si.)

**El pre-registro ya decia que esto NO es una confirmacion:** es una cota
superior (capturas a 19.4h de mediana = maximo sobre el TIEMPO, y casas que el
usuario no puede usar). Su unico valor es convertir la pregunta en una
concreta: *¿existen 8 casas legales en España cotizando el mismo partido?*

## VEREDICTO: DESCARTADO para el mercado español
Se contesto esa pregunta, y la respuesta mata el frente. **No es cuestion de
abrir mas cuentas: es que las casas españolas son todas la misma casa.**

**1. Cobertura real.** De las 7 casas con licencia española que aparecen en el
feed, solo 4 tienen cobertura utilizable en NCAAB: Bet365 (5.426 partidos),
Interwetten (5.349), Betsson (4.501), BWin (2.978). Betway y WilliamHill: **0**.
888Sport: 38. Nunca se llega a 8 cuentas, y con las 4 que hay ya se acabo.

**2. Son homogeneas y caras.** Margen medio en el moneyline de apertura:

| casa | margen |
|---|---|
| Bet365 | **4.21%** |
| BWin | 5.81% |
| Betsson | 7.49% |
| Interwetten | 9.76% |

Bet365 es la mas barata por bastante, y **da el mejor precio el 67.6%** de las
veces entre las españolas (BWin 19.3%, Betsson 9.2%, Interwetten 3.8%). Es
decir: el mejor precio de las 4 casas españolas *es Bet365* dos de cada tres
veces. Fuera de España el reparto es plano -- GGBet 23.8%, Bet365 16.7%,
Pinnacle 9.1%, DraftKings 9.0%, YSB88 8.9%, SBOBET 8.6% -- porque esas casas
**valoran distinto**, y de ahi salia toda la curva.

**3. La prueba que decide: mismos partidos, distintas casas.** Sobre los 2.274
partidos que tienen las 4 españolas a la vez (comparacion limpia, sin cambiar
la muestra al añadir cuentas), cuotas cortas:

| conjunto | ROI |
|---|---|
| Bet365 sola | -2.56% |
| Bet365 + BWin | -1.54% |
| + Interwetten | -1.30% |
| las 4 españolas | **-1.27%** |
| Bet365 + Pinnacle + GGBet + SBOBET (no jugables) | **+2.24%** |

Cuatro cuentas españolas recuperan 1.3 puntos y se quedan en -1.27%. Cuatro
cuentas *sharp* sobre esos mismos partidos dan +2.24%. **Lo que movia la curva
no era N, era QUE casas.** El line shopping funciona porque casas que piensan
distinto se contradicen; las españolas no se contradicen, copian a Bet365.

**4. El -0.45% anterior era un artefacto de muestra.** `PREREGISTRO_mejor_precio.md`
dio -0.45% con Bet365+BWin, "a medio punto del equilibrio". Ese numero sale de
n=1.240 apuestas -- solo los partidos donde ambas casas coinciden, que no son
una muestra aleatoria. Sobre los mismos partidos que el resto de conjuntos ese
par da **-1.54%**, y el conjunto completo de las 7 españolas da **-1.05%
(n=2.593)**. No estabamos a medio punto: estabamos a un punto largo, y con la
barrera de 4.2 puntos de `MAPA_MARGEN.md` delante.

**Conclusion: el line shopping queda cerrado.** Abrir mas cuentas españolas no
es la solucion porque no existen mas casas españolas con cobertura, y las que
hay dan el mismo precio que Bet365 solo que peor. Un apostante en España juega,
de facto, contra una unica linea de 4.21% de margen.

Reproducible: `python3 bball/analysis/cuantas_casas.py`
