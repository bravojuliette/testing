/**
 * Espejo en TypeScript de tt_elite/model/params.py::StrategyParams (los
 * valores por defecto de BASELINE) + textos explicativos para el dashboard.
 * Si cambias los defaults en Python, cambialos tambien aqui -- es la unica
 * duplicacion que hace falta para poder mostrar "en que se diferencia este
 * experimento del baseline" sin tener que llamar a Python desde el dashboard.
 */
export type StrategyParams = {
  name: string;
  initial_elo: number;
  rolling_elo_k: number;
  elo_scale: number;
  session_k: number;
  session_delta_cap: number;
  common_opp_k: number;
  common_opp_cap: number;
  h2h_weight: number;
  h2h_cap: number;
  h2h_max_matches: number;
  min_matches_played: number;
  min_model: number;
  min_edge: number;
  min_ev: number;
  min_market_gap: number;
  fb_min_model: number;
  fb_min_edge: number;
  fb_min_ev: number;
};

export const BASELINE_PARAMS: StrategyParams = {
  name: "baseline_v7",
  initial_elo: 1000,
  rolling_elo_k: 24,
  elo_scale: 400,
  session_k: 42,
  session_delta_cap: 105,
  common_opp_k: 25,
  common_opp_cap: 40,
  h2h_weight: 0.15,
  h2h_cap: 35,
  h2h_max_matches: 20,
  min_matches_played: 3,
  min_model: 0.52,
  min_edge: 0.06,
  min_ev: 0.03,
  min_market_gap: 0.005,
  fb_min_model: 0.55,
  fb_min_edge: 0.1,
  fb_min_ev: 0.08,
};

type FieldInfo = { label: string; tip: string; group: "senal" | "modelo" | "fallback" };

export const FIELD_INFO: Record<string, FieldInfo> = {
  min_model: {
    label: "Prob. mínima del modelo",
    tip: "El modelo tiene que dar al underdog al menos esta probabilidad de ganar para considerar la apuesta.",
    group: "senal",
  },
  min_edge: {
    label: "Edge mínimo",
    tip: "Diferencia mínima (en puntos porcentuales) entre lo que cree el modelo y lo que implica la cuota del mercado. Más alto = más exigente, menos picks pero más discrepancia.",
    group: "senal",
  },
  min_ev: {
    label: "EV mínimo",
    tip: "Valor esperado mínimo de la apuesta (probabilidad del modelo × cuota − 1). Un EV de 0.05 significa +5% esperado por unidad apostada, en teoría.",
    group: "senal",
  },
  min_market_gap: {
    label: "Diferencia mínima de mercado",
    tip: "Cuánto tienen que diferir las probabilidades implícitas de mercado entre favorito y underdog para que el partido cuente como 'con favorito claro'.",
    group: "senal",
  },
  fb_min_model: {
    label: "Prob. mínima (fallback)",
    tip: "Igual que 'Prob. mínima del modelo', pero cuando la cuota viene de un bookmaker de respaldo (menos fiable) en vez de la casa de referencia.",
    group: "fallback",
  },
  fb_min_edge: {
    label: "Edge mínimo (fallback)",
    tip: "Igual que 'Edge mínimo', pero para cuotas de bookmakers de respaldo. Se exige más porque la cuota es menos fiable.",
    group: "fallback",
  },
  fb_min_ev: {
    label: "EV mínimo (fallback)",
    tip: "Igual que 'EV mínimo', pero para cuotas de bookmakers de respaldo.",
    group: "fallback",
  },
  session_k: {
    label: "Sensibilidad a la forma del día",
    tip: "Cuánto pesa el rendimiento de un jugador EN LA SESIÓN DE HOY (no su Elo histórico) al calcular su probabilidad de ganar. Más alto = la forma reciente pesa más.",
    group: "modelo",
  },
  session_delta_cap: {
    label: "Tope de forma del día",
    tip: "Límite máximo (en puntos Elo) que puede sumar o restar la forma de la sesión de hoy, para que una racha puntual no dispare la probabilidad sin control.",
    group: "modelo",
  },
  common_opp_k: {
    label: "Sensibilidad a rivales comunes",
    tip: "Cuánto pesa la comparación 'cómo le fue a cada jugador contra los mismos rivales' cuando ambos ya jugaron contra alguien en común hoy.",
    group: "modelo",
  },
  common_opp_cap: {
    label: "Tope de rivales comunes",
    tip: "Límite máximo del ajuste por rivales comunes.",
    group: "modelo",
  },
  h2h_weight: {
    label: "Peso del historial directo",
    tip: "Cuánto influye el historial de enfrentamientos directos entre los dos jugadores (necesita al menos 3 partidos previos entre ellos para activarse).",
    group: "modelo",
  },
  h2h_cap: {
    label: "Tope del historial directo",
    tip: "Límite máximo del ajuste por historial directo.",
    group: "modelo",
  },
  h2h_max_matches: {
    label: "Partidos de historial a recordar",
    tip: "Cuántos enfrentamientos directos pasados como máximo se tienen en cuenta (los más recientes).",
    group: "modelo",
  },
  min_matches_played: {
    label: "Partidos previos mínimos",
    tip: "Cuántos partidos tiene que haber jugado YA cada jugador en la sesión de hoy antes de que el sistema considere apostar en su próximo partido.",
    group: "modelo",
  },
  rolling_elo_k: {
    label: "Velocidad de actualización del Elo",
    tip: "Cuánto se mueve el Elo de un jugador tras cada resultado real. Más alto = el Elo reacciona más rápido a resultados recientes.",
    group: "modelo",
  },
  elo_scale: {
    label: "Escala del Elo",
    tip: "Constante que traduce una diferencia de Elo en una probabilidad de victoria (estándar del sistema Elo, normalmente no hace falta tocarla).",
    group: "modelo",
  },
  initial_elo: {
    label: "Elo inicial",
    tip: "Elo que se le asigna a un jugador la primera vez que se le ve, si no hay dato previo.",
    group: "modelo",
  },
};

export const TERMS: Record<string, string> = {
  hitRate: "Porcentaje de picks liquidados (ya jugados) que acertaron.",
  roi: "Retorno sobre la inversión: ganancia o pérdida media por unidad apostada, en %. Negativo significa que en promedio se pierde dinero.",
  pnl: "Profit & Loss: unidades ganadas o perdidas en total (1 unidad = 1 apuesta a stake fijo).",
  edge: "Diferencia entre la probabilidad que da el modelo y la que implica la cuota de mercado, en puntos porcentuales.",
  ev: "Valor esperado de la apuesta: probabilidad del modelo × cuota − 1. Positivo en teoría significa apuesta rentable a largo plazo SI el modelo acierta.",
  sharpe: "Media del PnL dividida entre su desviación estándar. Mide si el resultado es consistente o depende de pocos picks con mucha varianza. Más alto (y positivo) es mejor.",
  signal: "SI = señal directa sobre la casa de referencia. SI_FALLBACK = señal fuerte sobre una casa de respaldo (umbral más exigente). REVISAR = discrepancia moderada en una casa de respaldo, no se actúa automáticamente.",
  warmupTrainTest: "Warmup: días que solo alimentan el Elo, sin generar picks. Train: periodo donde se ajustan/miran los resultados. Test: periodo 'a ciegas' que nunca se usó para elegir parámetros -- es la validación real.",
  pending: "Picks generados cuyo partido todavía no ha terminado.",
  active: "La configuración de parámetros que usa AHORA MISMO el scanner en vivo (corre cada 10 min) para decidir qué avisos mandar.",
};

export function paramDiffs(params: Partial<StrategyParams>, base: StrategyParams = BASELINE_PARAMS) {
  const diffs: { key: string; label: string; value: number; baseValue: number }[] = [];
  for (const key of Object.keys(base) as (keyof StrategyParams)[]) {
    if (key === "name") continue;
    const v = params[key];
    const b = base[key];
    if (typeof v === "number" && typeof b === "number" && v !== b) {
      diffs.push({ key, label: FIELD_INFO[key]?.label || key, value: v, baseValue: b });
    }
  }
  return diffs;
}

/** Compara dos StrategyParams ignorando 'name' -- lo que importa para saber
 * si un experimento ES la estrategia activa ahora mismo es si sus numeros
 * coinciden, no como se llame. */
export function paramsEqualIgnoringName(a: StrategyParams | null, b: StrategyParams | null): boolean {
  if (!a || !b) return false;
  for (const key of Object.keys(BASELINE_PARAMS) as (keyof StrategyParams)[]) {
    if (key === "name") continue;
    if (a[key] !== b[key]) return false;
  }
  return true;
}

export function parseParamsJson(paramsJson: string | null): StrategyParams | null {
  if (!paramsJson) return null;
  try {
    return JSON.parse(paramsJson) as StrategyParams;
  } catch {
    return null;
  }
}
