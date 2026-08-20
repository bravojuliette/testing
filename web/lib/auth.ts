/**
 * Autenticacion minima: una sola contrasena compartida (APP_PASSWORD).
 * El token de sesion es un HMAC-SHA256 determinista de esa contrasena, asi
 * que no hace falta guardar sesiones en ningun sitio: el middleware (Edge)
 * y el login (Node) solo tienen que recalcular el mismo hash y compararlo.
 * Suficiente para un panel personal de un solo usuario -- no es multiusuario.
 */
export const SESSION_COOKIE = "tt_elite_session";

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function sessionTokenFor(password: string): Promise<string> {
  return sha256Hex(`tt-elite-session:${password}`);
}

export async function isValidSessionToken(token: string | undefined, password: string): Promise<boolean> {
  if (!token || !password) return false;
  const expected = await sessionTokenFor(password);
  return timingSafeEqual(token, expected);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
