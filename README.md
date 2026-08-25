# TT Elite — sistema de picks para TT Elite Series

Reemplaza el stack Google Sheets (Apps Script) + Colab por una sola base de
código Python. La idea central: **separar la parte cara en red (descargar
histórico) de la parte de experimentar (evaluar estrategias)**, para poder
iterar sobre el modelo en segundos en vez de volver a scrapear cada vez.

```
Apps Script (scanner en vivo)  ─┐
                                 ├─►  tt_elite/  (una sola base de código)
Colab (backtest 1 año)         ─┘         │
                                           ├─► GitHub Actions (cron + botones)
                                           └─► web/ (dashboard en Vercel)
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
  vivo ahora mismo. Se guarda en la base de datos (tabla `meta`, no un
  archivo -- así el botón "Promover" del dashboard escribe directo y el
  scanner lo recoge en la siguiente pasada, sin depender de un commit a git).
  Se actualiza con `promote` después de un sweep.
- **`web/`** — dashboard en Next.js (se despliega en Vercel): datos cargados,
  experimentos con sus KPIs y en qué se diferencian del baseline, picks en
  vivo con filtros, y botones para lanzar collect/sweep/scan y promover.
  resultados y experimentos, y botones para lanzar `scan`/`sweep`/`collect`
  (que en realidad disparan los workflows de GitHub Actions vía su API). Ver
  la sección "Dashboard web" más abajo.

## Instalación local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y rellena BETSAPI_TOKEN + SENDGRID_API_KEY
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
   GitHub Actions) recoge la estrategia activa (guardada en la base de datos)
   automáticamente en la siguiente corrida. También puedes promover con un
   clic desde la sección "Experimentos" del dashboard.

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
| `SENDGRID_API_KEY` | API key de [SendGrid](https://sendgrid.com) para el envío del email (**nunca en código ni en el repo**) |
| `EMAIL_FROM`, `EMAIL_TO` | remitente/destinatario. `EMAIL_FROM` tiene que estar verificado en SendGrid como "Single Sender" (Settings → Sender Authentication → Single Sender Verification, solo requiere confirmar un clic en un email, sin DNS) |

Sin `TURSO_DATABASE_URL` configurado, el estado vive en `data/tt_elite.db`
local (sirve para desarrollo, pero cada corrida de GitHub Actions sería una
máquina nueva sin memoria de la anterior). Con Turso configurado (ver sección
siguiente), el mismo estado persiste entre corridas y es compartido con el
dashboard. Si quieres correrlo en tu propia máquina en vez de GitHub Actions,
un cron normal invocando `python -m tt_elite.cli scan` cada 5-10 minutos hace
lo mismo.

## Cadenas de barridas transitivas (sistema aparte, observacional)

Sistema independiente del scanner principal -- **no genera picks ni
probabilidad de acierto, no tiene backtest detrás**. Dentro de una misma
sesión (torneo del día): si un jugador A goleó 3-0 a un rival X, y ese mismo
X goleó 3-0 a un rival Y, y toca disputarse A vs Y, se marca aquí -- con las
cuotas que tenía cada uno, y (cuando el partido termina) si la teoría se
cumplió o no.

```bash
python -m tt_elite.cli scan-blowout-chain --show   # busca y muestra las de hoy (solo A underdog)
python -m tt_elite.cli scan-blowout-chain --show --all  # incluye tambien las que A ya es favorito
python -m tt_elite.cli scan-blowout-chain --days-back 5  # re-escanea una ventana mayor
python -m tt_elite.cli scan-blowout-chain --no-odds  # no consulta BetsAPI (mas rapido, no requiere token)
```

La detección en sí solo lee `raw_matches` ya recolectado por el scanner en
vivo (no llama a BetsAPI ni TT-Series). Las cuotas de cada partido A vs Y sí
requieren `BETSAPI_TOKEN` -- pero solo se consultan **una vez** por cadena
(se guardan en `blowout_chain_signals` y no se repite la consulta en pasadas
siguientes). Corre cada 10 min junto al scan principal en `live_scan.yml`.

Por defecto (`--show` en el CLI, y en el dashboard en `/cadenas`) solo se
muestran las cadenas donde **A tiene cuota de underdog** (el mercado lo ve
menos probable que a Y) -- si A ya es favorito, la cadena no dice nada que
la cuota no dijera ya; el interés está en los casos donde la teoría discrepa
del mercado. `/cadenas` tiene un enlace "Ver todas" para quitar ese filtro.
Se ve separado en "pendientes" (por disputarse) y "ya jugados".

También se muestra la **rentabilidad**: qué habría pasado apostando 1 unidad
a A en cada cadena ya jugada con cuota conocida (P&L y ROI, sobre el mismo
filtro underdog/todas que esté activo). Es un dato observacional sobre una
muestra todavía muy pequeña, no una conclusión ni una estrategia validada.

### Backfill histórico (más muestra = rentabilidad más realista)

`raw_matches` tiene ~2 años de histórico (del backtest original) y
`raw_odds` ya tiene cuotas de apertura para la mayoría de esos días
(recolectadas en su momento con `collect --fetch-odds`, antes de que
existiera este sistema de cadenas). Un backfill reutiliza esas cuotas ya
guardadas -- **no dispara un aluvión de llamadas a BetsAPI**, solo consulta
en vivo lo que de verdad falte (normalmente los últimos días):

```bash
python -m tt_elite.cli scan-blowout-chain --days-back 31 --show   # ultimo mes
```

Esto recalcula y guarda TODAS las cadenas de esa ventana en
`blowout_chain_signals` (no solo las de hoy) -- así que el histórico y la
rentabilidad que se ven en `/cadenas` y en `--show` pasan a reflejar esa
muestra mayor automáticamente, sin más cambios. Para correrlo con TODO el
historico disponible, usa un `--days-back` que cubra desde el primer día
de `raw_matches` (consulta `python -m tt_elite.cli status`).

### Racha previa de A (filtro adicional)

Cada cadena guarda también `a_prior_win_streak`: cuántas victorias
consecutivas llevaba A **dentro de esa misma sesión**, justo antes de A vs Y
(0 si el último resultado de A fue una derrota, o si A no jugó nada más
antes -- sin mirar al futuro). `/cadenas` y `--show` desglosan el histórico
y la rentabilidad por racha mínima (≥0, ≥1, ≥2, ≥3).

Con el historial completo, exigir más racha previa **no mejora** la
rentabilidad -- la empeora: sobre la muestra de A-underdog, ROI pasa de
+1.2% (sin exigir racha) a -29.9% (exigiendo 3 victorias seguidas). No es
un filtro que convenga aplicar.

## Dashboard web (Vercel) + base de datos compartida (Turso)

Además del scanner en vivo por email, hay un dashboard (`web/`, Next.js) para
ver los picks/resultados/experimentos desde el navegador y lanzar un
scan/sweep/collect con un botón. Para que funcione, GitHub Actions (quien
escribe los datos) y Vercel (quien los lee) tienen que compartir la misma
base de datos — por eso se usa **Turso** (SQLite alojado) en vez del archivo
SQLite local.

### 1. Crear la base de datos en Turso

1. Cuenta gratis en https://turso.tech (o `turso auth signup` con su CLI).
2. Crea una base de datos: en su dashboard web, "Create Database" (o
   `turso db create tt-elite`).
3. Copia dos valores:
   - **Database URL** (empieza por `libsql://...`)
   - **Auth token**: "Create Token" en la base de datos (o
     `turso db tokens create tt-elite`)

### 2. Añadir esos valores a GitHub Secrets

En el repo, `Settings` → `Secrets and variables` → `Actions` → *Repository
secrets*, añade (además de los que ya tenías: `BETSAPI_TOKEN`, `SENDGRID_API_KEY`,
`EMAIL_*`):

| Secret | Valor |
|---|---|
| `TURSO_DATABASE_URL` | la Database URL de arriba |
| `TURSO_AUTH_TOKEN` | el Auth token de arriba |

Con esto, `live_scan.yml`, `sweep.yml` y `collect.yml` ya escriben en Turso
en vez del archivo local.

### 3. Desplegar el dashboard en Vercel

1. En Vercel: "Add New" → "Project" → importa este repo de GitHub.
2. **Importante**: en "Root Directory" selecciona `web` (el dashboard vive
   en ese subdirectorio, no en la raíz del repo).
3. En "Environment Variables" añade:

   | Variable | Valor |
   |---|---|
   | `TURSO_DATABASE_URL` | la misma que en GitHub Secrets |
   | `TURSO_AUTH_TOKEN` | el mismo que en GitHub Secrets |
   | `GITHUB_OWNER` | `bravojuliette` |
   | `GITHUB_REPO` | `testing` |
   | `GITHUB_REF` | el nombre de la rama donde viven los workflows (la rama por defecto del repo) |
   | `GITHUB_TOKEN` | un Personal Access Token (ver paso 4) |
   | `APP_PASSWORD` | una contraseña tuya para entrar al dashboard |

4. Deploy. Vercel te da una URL tipo `tt-elite-web.vercel.app` — esa es tu
   aplicativo.

### 4. Crear el token de GitHub para que Vercel pueda lanzar workflows

El dashboard lanza `scan`/`sweep`/`collect` llamando a la API de GitHub
Actions, así que necesita un token con permiso de escritura sobre Actions
**solo de este repo** (no un token con acceso a toda tu cuenta):

1. GitHub → tu foto de perfil → `Settings` (la de tu cuenta, no la del repo)
   → `Developer settings` (al final del menú izquierdo) → `Personal access
   tokens` → `Fine-grained tokens` → `Generate new token`.
2. "Repository access" → `Only select repositories` → elige `testing`.
3. "Permissions" → `Actions` → `Read and write`.
4. Generate token, cópialo (empieza por `github_pat_...`) y pégalo como
   `GITHUB_TOKEN` en Vercel (paso 3).

### Uso

Entras a la URL de Vercel, pones tu `APP_PASSWORD`, y ves:
- Picks recientes (30 días), hit rate, ROI, PnL.
- Experimentos recientes (resultados de sweeps).
- Botones para lanzar `scan` / `sweep` / `collect` — cada uno dispara el
  workflow correspondiente en GitHub Actions (puedes seguir el progreso real
  en la pestaña Actions del repo, el dashboard solo dispara, no ejecuta nada
  él mismo).

## Notas importantes

- **El token de BetsAPI y la API key de SendGrid nunca deben subirse al
  repo.** `.env` está en `.gitignore`; en producción van como GitHub
  Secrets.
- El modelo es una heurística (igual que en tus scripts originales). Un
  ROI positivo en backtest **no garantiza** rentabilidad futura — valida
  siempre en una ventana de test que el motor de sweep nunca vio mientras
  ajustabas parámetros, y no subas el stake hasta tener bastante muestra
  en vivo.
- `data/tt_elite.db` es SQLite normal — puedes explorarlo con cualquier
  cliente SQLite o `pandas.read_sql` si quieres analizar picks a mano.
