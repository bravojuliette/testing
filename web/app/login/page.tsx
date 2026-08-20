export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const params = await searchParams;
  const next = params.next || "/";
  const error = params.error === "1";

  return (
    <main className="login-page">
      <form className="login-card" action="/api/login" method="POST">
        <h1>TT Elite</h1>
        <p className="subtitle">Introduce la contraseña del panel</p>
        <input type="hidden" name="next" value={next} />
        <input
          type="password"
          name="password"
          placeholder="Contraseña"
          autoFocus
          required
        />
        {error && <p className="error">Contraseña incorrecta.</p>}
        <button type="submit">Entrar</button>
      </form>
    </main>
  );
}
