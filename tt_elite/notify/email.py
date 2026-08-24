"""Envio de alertas por email via la API HTTP de Resend (https://resend.com) --
una sola API key, sin lios de contrasenas de aplicacion SMTP."""
from __future__ import annotations

import requests

from .. import config

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(subject: str, html_body: str, text_body: str | None = None) -> None:
    if not (config.RESEND_API_KEY and config.EMAIL_TO):
        raise RuntimeError("Falta RESEND_API_KEY o EMAIL_TO en el entorno.")

    payload = {
        "from": config.EMAIL_FROM,
        "to": [config.EMAIL_TO],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Resend devolvio HTTP {resp.status_code} al enviar el email: {resp.text[:500]!r}")


def render_picks_email(picks: list[dict]) -> tuple[str, str]:
    """Devuelve (subject, html_body) para una lista de picks (dicts tipo fila de
    la tabla `picks`)."""
    n = len(picks)
    subject = f"TT Elite: {n} pick{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''}"

    rows_html = []
    for p in picks:
        rows_html.append(
            "<tr>"
            f"<td>{p['time']}</td>"
            f"<td>{p['underdog']}</td> vs <td>{p['favorito']}</td>"
            f"<td>{p['odds_underdog']:.2f}</td>"
            f"<td>{p['model_prob_underdog']*100:.1f}%</td>"
            f"<td>{p['edge_pp']*100:+.1f}pp</td>"
            f"<td>{p['ev_pct']*100:+.1f}%</td>"
            f"<td><b>{p['signal']}</b></td>"
            f"<td>{p['book']}</td>"
            "</tr>"
        )

    html = f"""
    <h2>TT Elite Series -- {n} pick(s) nuevo(s)</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:sans-serif;font-size:13px">
      <tr style="background:#eee">
        <th>Hora</th><th>Underdog</th><th>vs Favorito</th><th>Cuota</th>
        <th>Prob. modelo</th><th>Edge</th><th>EV</th><th>Senal</th><th>Casa</th>
      </tr>
      {''.join(rows_html)}
    </table>
    <p style="color:#888;font-size:12px">Generado automaticamente. Esto no es una recomendacion de apuesta;
    revisa siempre el pick antes de actuar.</p>
    """
    return subject, html
