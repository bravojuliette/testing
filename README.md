# TT Elite — sistema de picks para TT Elite Series

Reemplaza el stack Google Sheets (Apps Script) + Colab por una sola base de
código Python. La idea central: **separar la parte cara en red (descargar
histórico) de la parte de experimentar (evaluar estrategias)**, para poder
iterar sobre el modelo en segundos en vez de volver a scrapear cada vez.

```
Apps Script (scanner en vivo)  ─┐
                                 ├─►  tt_elite/  (una sola base de código)
Colab (backtest 1 año)         ─┘
```

## Piezas

- **`tt_elite/model/`** — el modelo (Elo rodante + forma de sesión + rivales
  comunes + H2H) y el evaluador de señales (SI / SI_FALLBACK / REVISAR),
  parametrizados vía `StrategyParams` (dataclass). Los mismos parámetros que
  ya tenías corriendo en v7.1/v5 están en `StrategyParams()` por defecto.
- **`tt_elite/backtest/collect.py`** — descarga TT-Series + BetsAPI para un
  rango de fechas y lo cachea en SQLite (`data/tt_elite.db`). Resumible: si
  se corta a mitad de camino, vuelve a correr y continúa donde quedó.
- **`tt_elite/backtest/replay.py`** — motor de backtest puro (sin red):
  reproduce cronológicamente los datos ya cacheados contra un
  `StrategyParams` dado. Por eso un sweep de cientos de configuraciones tarda
  segundos.
- **`tt_elite/backtest/sweep.py`** — corre una grilla de parámetros con split
  train/test (walk-forward) y guarda cada corrida en la tabla `experiments`,
  para comparar variantes y evitar sobreajuste.
- **`tt_elite/live/scan.py`** — el scanner en vivo: revisa las sesiones de
  hoy, actualiza el Elo/H2H persistente, evalúa candidatos elegibles contra
  la **estrategia activa** y manda email si hay algo nuevo accionable.
- **`tt_elite/model/active.py`** — qué `StrategyParams` usa el scanner en
  vivo ahora mismo (`config/active_strategy.json`). Se actualiza con
  `promote` después de un sweep.

## Instalación local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y rellena BETSAPI_TOKEN + credenciales SMTP
```

Corre los tests (no necesitan red, validan modelo + motor de backtest con
datos sintéticos):

```bash
python -m unittest discover -s tt_elite/tests -v
```

## Flujo para "encontrar un sistema ganador"

1. **Recolectar histórico una vez** (esto sí gasta cuota de BetsAPI, igual
   que tu backtest de Colab; resumible si se corta):

   ```bash
   python -m tt_elite.cli collect --start 2025-01-01 --end 2026-08-01
   ```

2. **Barrer parámetros** sobre ese histórico ya cacheado (rápido, sin red).
   `--warmup-start` alimenta el Elo antes de empezar a evaluar; `--train-*`
   es para mirar/ajustar, `--test-*` es la validación **out-of-sample real**
   — nunca elijas una configuración por su ROI en train, eso es sobreajuste
   garantizado con datos de apuestas:

   ```bash
   python -m tt_elite.cli sweep \
     --warmup-start 2025-01-01 --train-start 2025-04-01 \
     --test-start 2026-02-01 --test-end 2026-08-01 \
     --min-test-samples 30
   ```

   Esto imprime un leaderboard ordenado por ROI de test. Puedes pasar tu
   propia grilla con `--grid-file grid.json`, p.ej.:

   ```json
   {"min_model": [0.52, 0.55, 0.60], "session_k": [30, 42, 55], "h2h_weight": [0.10, 0.15, 0.20]}
   ```

3. **Repetir el split en otra ventana de fechas** (walk-forward real: si una
   configuración solo funciona en un periodo de test, no sirve). Cuando una
   configuración se sostiene en varios splits, actívala:

   ```bash
   python -m tt_elite.cli promote --experiment-id 42
   # o directo:
   python -m tt_elite.cli promote --params-json '{"name": "...", ...}'
   ```

4. El scanner en vivo (`python -m tt_elite.cli scan`, o el workflow de
   GitHub Actions) recoge automáticamente `config/active_strategy.json` en la
   siguiente corrida.

5. **Sigue coleccionando en producción**: cada corrida del scanner en vivo
   también guarda los partidos del día en la misma base SQLite (con el mismo
   `match_uid` que usaría un `collect` de esa fecha), así que tu histórico
   sigue creciendo solo y el próximo sweep tiene más datos out-of-sample de
   verdad, no solo el año que ya tenías.

## Scanner en vivo + alertas por email

```bash
python -m tt_elite.cli scan               # una pasada
python -m tt_elite.cli scan --dry-run-email  # calcula y guarda, no manda email
python -m tt_elite.cli report --days 14    # picks recientes y su resultado
```

En producción corre solo, cada 10 min, vía
`.github/workflows/live_scan.yml` (GitHub Actions). Configura estos
**Secrets** del repo (Settings → Secrets and variables → Actions):

| Secret | Para qué |
|---|---|
| `BETSAPI_TOKEN` | tu token de BetsAPI (**nunca lo pongas en código ni en el repo**) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | envío del email. Con Gmail: activa verificación en 2 pasos y crea una "contraseña de aplicación" en https://myaccount.google.com/apppasswords |
| `EMAIL_FROM`, `EMAIL_TO` | remitente/destinatario |

El estado (SQLite: histórico, Elo/H2H persistente, picks) vive en la cache de
Actions entre corridas (no se commitea al repo). Si quieres correrlo en tu
propia máquina en vez de GitHub Actions, un cron normal invocando
`python -m tt_elite.cli scan` cada 5-10 minutos hace lo mismo.

## Notas importantes

- **El token de BetsAPI y las credenciales SMTP nunca deben subirse al
  repo.** `.env` está en `.gitignore`; en producción van como GitHub
  Secrets.
- El modelo es una heurística (igual que en tus scripts originales). Un
  ROI positivo en backtest **no garantiza** rentabilidad futura — valida
  siempre en una ventana de test que el motor de sweep nunca vio mientras
  ajustabas parámetros, y no subas el stake hasta tener bastante muestra
  en vivo.
- `data/tt_elite.db` es SQLite normal — puedes explorarlo con cualquier
  cliente SQLite o `pandas.read_sql` si quieres analizar picks a mano.
