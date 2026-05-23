"""
Email Notification System
Sends signal alerts to dieter_kammer@gmx.de
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


RECIPIENT = os.environ.get("NOTIFY_EMAIL", "dieter_kammer@gmx.de")
SENDER = os.environ.get("SMTP_FROM", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")


def send_signal_email(signals: list) -> bool:
    """Send email with top trading signals."""
    if not signals:
        return False
    if not SMTP_USER or not SMTP_PASS:
        print("⚠️  SMTP nicht konfiguriert – E-Mail-Versand übersprungen.")
        return False

    subject = f"📈 {len(signals)} Trading Signal(e) – {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    html_rows = ""
    for s in signals:
        emoji = "🟢" if s["direction"] == "BUY" else "🔴"
        color = "#22c55e" if s["direction"] == "BUY" else "#ef4444"
        reasons = "<br>".join(f"• {r}" for r in s.get("signals", []))
        html_rows += f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;">
            <strong>{emoji} {s['name']}</strong><br>
            <span style="color:#888;font-size:12px;">{s['ticker']}</span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;text-align:center;">
            <span style="background:{color};color:white;padding:4px 10px;border-radius:12px;font-weight:bold;">
              {s['direction']}
            </span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;text-align:right;">
            <strong>{s['price']:.2f}€</strong>
          </td>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;text-align:right;color:#22c55e;">
            {s['take_profit']:.2f}€
          </td>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;text-align:right;color:#ef4444;">
            {s['stop_loss']:.2f}€
          </td>
          <td style="padding:12px;border-bottom:1px solid #2d2d2d;font-size:12px;color:#aaa;">
            {reasons}
          </td>
        </tr>
        """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#1a1a1a;color:#e0e0e0;padding:20px;">
      <h2 style="color:#f0b429;">📊 Trading Signal Report</h2>
      <p style="color:#888;">{datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}</p>
      <table style="width:100%;border-collapse:collapse;background:#222;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#2d2d2d;color:#f0b429;">
            <th style="padding:10px;text-align:left;">Wert</th>
            <th style="padding:10px;">Signal</th>
            <th style="padding:10px;text-align:right;">Preis</th>
            <th style="padding:10px;text-align:right;">Take Profit</th>
            <th style="padding:10px;text-align:right;">Stop Loss</th>
            <th style="padding:10px;text-align:left;">Begründung</th>
          </tr>
        </thead>
        <tbody>
          {html_rows}
        </tbody>
      </table>
      <p style="color:#555;font-size:11px;margin-top:20px;">
        ⚠️ Dies sind automatisch generierte technische Signale, keine Anlageberatung.
        Handeln Sie immer mit eigenem Ermessen und Risikobewusstsein.
      </p>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER or SMTP_USER
        msg["To"] = RECIPIENT
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, RECIPIENT, msg.as_string())
        print(f"✅ E-Mail gesendet an {RECIPIENT}")
        return True
    except Exception as e:
        print(f"❌ E-Mail-Fehler: {e}")
        return False
