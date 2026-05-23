# TradeBot Pro – Setup & Deployment Anleitung

## Was ist enthalten?

Die App besteht aus:
- **Backend**: Python-Server mit technischer Marktanalyse
- **Frontend**: Moderne Web-App (PWA) für Handy & Browser
- **Paper Trading**: Virtuelles Depot mit 10.000€ zum Testen
- **Benachrichtigungen**: E-Mail bei starken Signalen

---

## Schritt-für-Schritt Deployment auf Render.com (kostenlos)

### Schritt 1: GitHub Account erstellen (falls nicht vorhanden)
1. Gehe zu: https://github.com
2. Klicke auf „Sign up"
3. E-Mail und Passwort eingeben → Konto erstellen

### Schritt 2: Neues Repository erstellen
1. Nach dem Login auf https://github.com/new gehen
2. Repository Name: `tradebot-pro`
3. Auf „Create repository" klicken

### Schritt 3: Dateien hochladen
1. Klicke auf „uploading an existing file"
2. Lade alle Dateien aus dem ZIP hoch (komplette Ordnerstruktur)
3. Klicke auf „Commit changes"

### Schritt 4: Render.com Account erstellen
1. Gehe zu: https://render.com
2. Klicke auf „Get Started for Free"
3. Mit GitHub anmelden (dann verbindet sich Render automatisch)

### Schritt 5: Web Service erstellen
1. Im Render-Dashboard: „New +" → „Web Service"
2. Dein `tradebot-pro` Repository auswählen
3. Diese Einstellungen:
   - **Name**: tradebot-pro
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
4. Klicke auf „Create Web Service"

### Schritt 6: Warten (ca. 3-5 Minuten)
Render baut die App automatisch. Du siehst den Fortschritt.

### Schritt 7: App öffnen
Nach erfolgreichem Build bekommst du eine URL wie:
`https://tradebot-pro.onrender.com`

Diese URL im Handy-Browser öffnen → fertig!

---

## Als App auf dem Handy installieren (PWA)

### iPhone (Safari):
1. URL im Safari öffnen
2. Teilen-Button (Quadrat mit Pfeil nach oben) antippen
3. „Zum Home-Bildschirm" wählen
4. „Hinzufügen" bestätigen

### Android (Chrome):
1. URL in Chrome öffnen
2. Drei-Punkte-Menü oben rechts
3. „App installieren" oder „Zum Startbildschirm hinzufügen"

---

## E-Mail Benachrichtigungen einrichten (optional)

Für E-Mail-Benachrichtigungen brauchst du einen Gmail-Account:
1. In Render → dein Service → „Environment"
2. Diese Variablen hinzufügen:
   - `SMTP_USER`: deine Gmail-Adresse
   - `SMTP_PASS`: Gmail App-Passwort (nicht dein normales Passwort!)
   
Für ein Gmail App-Passwort:
1. Google Account → Sicherheit → 2-Faktor-Authentifizierung aktivieren
2. Dann: Google Account → Sicherheit → App-Passwörter
3. „Mail" auswählen → Passwort generieren → in Render eintragen

---

## Projektstruktur

```
tradebot-pro/
├── backend/
│   ├── main.py          → FastAPI Server & API-Endpunkte
│   ├── analyzer.py      → Technische Analyse (RSI, MACD, BB, etc.)
│   ├── paper_trading.py → Virtuelles Depot
│   └── notifications.py → E-Mail-Versand
├── frontend/
│   ├── index.html       → Die komplette Web-App
│   └── manifest.json    → PWA-Konfiguration
├── data/                → Wird automatisch erstellt (Portfolio-Daten)
├── requirements.txt     → Python-Abhängigkeiten
└── render.yaml          → Render.com Konfiguration
```

---

## Technische Indikatoren (alle aktiv)

| Indikator | Parameter | Zweck |
|-----------|-----------|-------|
| RSI | 14 Perioden | Über-/Unterverkauf |
| MACD | 12/26/9 | Trendwechsel |
| Bollinger Bands | 20 Perioden | Volatilität & Extrempunkte |
| Stochastik | 14/3 | Momentum |
| EMA | 20, 50, 200 | Trendrichtung |
| ADX | 14 Perioden | Trendstärke |
| ATR | 14 Perioden | Stop Loss / Take Profit Berechnung |

---

## Analysierte Märkte

**Indizes:** DAX, Euro Stoxx 50, FTSE 100, CAC 40, IBEX 35, AEX, SMI, ATX

**Einzelwerte:** 30+ Top-Aktien aus DAX, EuroStoxx, SMI, FTSE (SAP, ASML, LVMH, Nestlé, etc.)

---

## Signallogik

- Nur Signale mit Stärke ≥ 60/100 werden angezeigt
- Max. 5 Top-Signale pro Analyse
- Automatische Analyse mehrmals täglich
- ATR-basiertes Stop Loss & Take Profit (1:2 Risk/Reward)

---

## Hinweis

⚠️ Dieses Tool generiert automatisierte technische Signale zu Testzwecken.
Es handelt sich NICHT um Anlageberatung. Handeln Sie immer mit eigenem Ermessen.
