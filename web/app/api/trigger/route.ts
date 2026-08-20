import { NextRequest, NextResponse } from "next/server";
import { dispatchWorkflow, WorkflowFile } from "../../../lib/github";

// El middleware ya exige sesion valida para llegar aqui -- esta ruta no
// vuelve a comprobar la contrasena, pero tampoco confia en el body a ciegas:
// solo acepta un conjunto fijo de workflows/inputs conocidos.
const WORKFLOWS: Record<string, WorkflowFile> = {
  scan: "live_scan.yml",
  sweep: "sweep.yml",
  collect: "collect.yml",
};

export async function POST(req: NextRequest) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body invalido (se esperaba JSON)." }, { status: 400 });
  }

  const kind = String(body?.type || "");
  const workflow = WORKFLOWS[kind];
  if (!workflow) {
    return NextResponse.json({ error: `type desconocido: ${kind}` }, { status: 400 });
  }

  const inputs: Record<string, string> = {};
  for (const [k, v] of Object.entries(body?.inputs || {})) {
    if (v !== undefined && v !== null && v !== "") inputs[k] = String(v);
  }

  try {
    await dispatchWorkflow(workflow, inputs);
    return NextResponse.json({ ok: true });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || String(err) }, { status: 502 });
  }
}
