"""Envio de alertas por email via SMTP (pensado para Gmail + contrasena de
aplicacion, pero sirve con cualquier SMTP estandar)."""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .. import config


def send_email(subject: str, html_body: str, text_body: str | None = None) -> None:
    if not (config.SMTP_USER and config.SMTP_PASSWORD and config.EMAIL_TO):
        raise RuntimeError("Faltan credenciales SMTP (SMTP_USER/SMTP_PASSWORD/EMAIL_TO) en el entorno.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM or config.SMTP_USER
    msg["To"] = config.EMAIL_TO

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.sendmail(msg["From"], [config.EMAIL_TO], msg.as_string())


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
