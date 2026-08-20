import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, sessionTokenFor } from "../../../lib/auth";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const password = String(form.get("password") || "");
  const expected = process.env.APP_PASSWORD || "";
  const next = String(form.get("next") || "/");

  if (!expected || password !== expected) {
    const url = new URL("/login", req.url);
    url.searchParams.set("error", "1");
    url.searchParams.set("next", next);
    return NextResponse.redirect(url, { status: 303 });
  }

  const token = await sessionTokenFor(password);
  const res = NextResponse.redirect(new URL(next || "/", req.url), { status: 303 });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 dias
  });
  return res;
}
