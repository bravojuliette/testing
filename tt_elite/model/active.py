"""Que StrategyParams usa el scanner en vivo ahora mismo.

Se guarda en la tabla `meta` de la base de datos (SQLite local o Turso, lo
que este activo -- ver tt_elite/db.py), NO en un archivo. Un archivo dentro
del repo no serviria: cuando el dashboard "promueve" una estrategia, lo hace
escribiendo directo en Turso (sin pasar por git), y GitHub Actions clona el
repo desde cero en cada corrida, asi que cualquier archivo escrito ahi se
perderia en cuanto terminase esa corrida.

Flujo pensado: corres sweeps -> revisas el leaderboard de `experiments` (en
el dashboard o con `python -m tt_elite.cli sweep`) -> cuando confias en una
configuracion, la promueves (boton "Promover" en el dashboard, o
`python -m tt_elite.cli promote --experiment-id N`) -> el scanner en vivo la
recoge automaticamente en la siguiente ejecucion.
"""
from __future__ import annotations

from .params import BASELINE, StrategyParams

META_KEY = "active_strategy_params"


def load_active_params(conn) -> StrategyParams:
    from .. import db as dbmod

    raw = dbmod.get_meta(conn, META_KEY)
    if raw:
        return StrategyParams.from_json(raw)
    return BASELINE


def save_active_params(conn, params: StrategyParams) -> None:
    from .. import db as dbmod

    dbmod.set_meta(conn, META_KEY, params.to_json())
