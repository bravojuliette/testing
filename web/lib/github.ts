const GITHUB_API = "https://api.github.com";

export type WorkflowFile = "live_scan.yml" | "sweep.yml" | "collect.yml";

export async function dispatchWorkflow(workflow: WorkflowFile, inputs: Record<string, string>): Promise<void> {
  const token = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_OWNER;
  const repo = process.env.GITHUB_REPO;
  const ref = process.env.GITHUB_REF || "main";
  if (!token || !owner || !repo) {
    throw new Error("Falta GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO en las variables de entorno.");
  }

  const res = await fetch(
    `${GITHUB_API}/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref, inputs }),
    }
  );

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GitHub respondio ${res.status} al disparar ${workflow}: ${text}`);
  }
}

export function actionsRunsUrl(): string {
  const owner = process.env.GITHUB_OWNER;
  const repo = process.env.GITHUB_REPO;
  return owner && repo ? `https://github.com/${owner}/${repo}/actions` : "#";
}
