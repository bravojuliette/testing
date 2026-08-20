import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, isValidSessionToken } from "./lib/auth";

export const config = {
  // Todo excepto /login, la API de login, y assets estaticos de Next.
  matcher: ["/((?!login|api/login|_next/static|_next/image|favicon.ico).*)"],
};

export async function proxy(req: NextRequest) {
  const password = process.env.APP_PASSWORD || "";
  if (!password) {
    // Sin contrasena configurada no hay forma segura de proteger el panel;
    // mejor bloquear todo con un aviso claro que dejarlo abierto por defecto.
    return new NextResponse("Falta configurar APP_PASSWORD en las variables de entorno.", { status: 500 });
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (await isValidSessionToken(token, password)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("next", req.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}
