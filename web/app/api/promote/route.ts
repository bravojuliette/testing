import { NextRequest, NextResponse } from "next/server";
import { getExperiment, setActiveStrategyJson } from "../../../lib/db";

// Protegido por el middleware (misma sesion que el resto del panel). Escribe
// directo en Turso -- no hace falta pasar por GitHub Actions para esto,
// es solo un UPDATE de una fila.
export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body invalido (se esperaba JSON)." }, { status: 400 });
  }

  const experimentId = Number(body?.experimentId);
  if (!experimentId) {
    return NextResponse.json({ error: "Falta experimentId." }, { status: 400 });
  }

  try {
    const experiment = await getExperiment(experimentId);
    if (!experiment) {
      return NextResponse.json({ error: `No existe el experimento ${experimentId}.` }, { status: 404 });
    }
    await setActiveStrategyJson(experiment.params_json);
    return NextResponse.json({ ok: true, name: experiment.name, hash: experiment.params_hash });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || String(err) }, { status: 502 });
  }
}
