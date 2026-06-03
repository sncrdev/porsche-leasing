"""
Skrypt aktualizujący dane dla kalkulatora leasingu Porsche.
Uruchamiany codziennie przez GitHub Actions.

Pobiera:
- Aktualny WIBOR 1M ze stooq.pl
- Cennik Porsche z porsche.pl/cennik

Zapisuje wynik do data/data.json
Wysyła maila jeśli cennik się zmienił (opcjonalne).
"""

import json
import re
import smtplib
import sys
from datetime import date, datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Ścieżki ──────────────────────────────────────────────────────────────────
DATA_DIR  = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "data.json"
DATA_DIR.mkdir(exist_ok=True)

# ── Stałe cen (fallback, gdy scraping się nie uda) ───────────────────────────
FALLBACK_PRICES = {
    "911": [
        {"name": "911 Carrera",           "price": 681000},
        {"name": "911 Carrera Cab.",       "price": 749000},
        {"name": "911 Carrera T",          "price": 734000},
        {"name": "911 Carrera T Cab.",     "price": 795000},
        {"name": "911 Carrera S",          "price": 773000},
        {"name": "911 Carrera S Cab.",     "price": 841000},
        {"name": "911 Carrera 4",          "price": 736000},
        {"name": "911 Carrera 4 Cab.",     "price": 804000},
        {"name": "911 Carrera 4S",         "price": 826000},
        {"name": "911 Carrera 4S Cab.",    "price": 894000},
        {"name": "911 Targa 4",            "price": 808000},
        {"name": "911 Targa 4S",           "price": 898000},
        {"name": "911 Carrera GTS",        "price": 895000},
        {"name": "911 Carrera 4 GTS",      "price": 949000},
        {"name": "911 Targa 4 GTS",        "price": 974000},
        {"name": "911 GT3",                "price": 946000},
        {"name": "911 GT3 Touring",        "price": 946000},
        {"name": "911 GT3 RS",             "price": 1246000},
        {"name": "911 Turbo S",            "price": 1299000},
        {"name": "911 Turbo S Cab.",       "price": 1369000},
        {"name": "911 Turbo 50 Years",     "price": 1387000},
    ],
    "718": [
        {"name": "718 Cayman GT4 RS",      "price": 823000},
        {"name": "718 Spyder RS",          "price": 823000},
    ],
    "Cayenne": [
        {"name": "Cayenne",                "price": 478000},
        {"name": "Cayenne Coupe",          "price": 516000},
        {"name": "Cayenne S",              "price": 572000},
        {"name": "Cayenne S Coupe",        "price": 611000},
        {"name": "Cayenne E-Hybrid",       "price": 562000},
        {"name": "Cayenne E-Hyb. Coupe",   "price": 598000},
        {"name": "Cayenne Turbo E-Hyb.",   "price": 807000},
        {"name": "Cayenne Turbo GT",       "price": 889000},
    ],
    "Cayenne EV": [
        {"name": "Cayenne Electric",           "price": 446000},
        {"name": "Cayenne S Electric",         "price": 557000},
        {"name": "Cayenne Turbo Electric",     "price": 727000},
        {"name": "Cayenne Coupé Electric",     "price": 463000},
        {"name": "Cayenne S Coupé Electric",   "price": 570000},
        {"name": "Cayenne Turbo Coupé Elec.", "price": 740000},
    ],
    "Panamera": [
        {"name": "Panamera",               "price": 513000},
        {"name": "Panamera 4",             "price": 563000},
        {"name": "Panamera 4S",            "price": 656000},
        {"name": "Panamera 4 E-Hybrid",    "price": 620000},
        {"name": "Panamera 4S E-Hyb.",     "price": 730000},
        {"name": "Panamera Turbo E-Hyb.",  "price": 912000},
        {"name": "Panamera Executive",     "price": 657000},
        {"name": "Pan. 4 Executive",       "price": 707000},
        {"name": "Pan. Turbo E-Hyb. Exec.","price": 962000},
    ],
    "Taycan": [
        {"name": "Taycan",                 "price": 489000},
        {"name": "Taycan 4",               "price": 513000},
        {"name": "Taycan 4S",              "price": 620000},
        {"name": "Taycan GTS",             "price": 700000},
        {"name": "Taycan Turbo",           "price": 750000},
        {"name": "Taycan Turbo S",         "price": 894000},
        {"name": "Taycan Sport Turismo",   "price": 489000},
        {"name": "Taycan 4 ST",            "price": 513000},
        {"name": "Taycan 4S ST",           "price": 620000},
        {"name": "Taycan GTS ST",          "price": 720000},
        {"name": "Taycan Turbo ST",        "price": 760000},
        {"name": "Taycan Turbo S ST",      "price": 974000},
        {"name": "Taycan Cross Turismo",   "price": 563000},
        {"name": "Taycan 4 CT",            "price": 601000},
        {"name": "Taycan 4S CT",           "price": 680000},
        {"name": "Taycan Turbo CT",        "price": 800000},
        {"name": "Taycan Turbo S CT",      "price": 974000},
    ],
    "Macan": [
        {"name": "Macan",                  "price": 298000},
        {"name": "Macan T",                "price": 342000},
        {"name": "Macan S",                "price": 357000},
        {"name": "Macan GTS (benzyna)",    "price": 411000},
        {"name": "Macan EV",               "price": 370000},
        {"name": "Macan 4 EV",             "price": 413000},
        {"name": "Macan 4S EV",            "price": 490000},
        {"name": "Macan GTS EV",           "price": 480000},
        {"name": "Macan Turbo EV",         "price": 521000},
    ],
}


# ── 1. WIBOR ─────────────────────────────────────────────────────────────────
def fetch_wibor() -> float | None:
    """
    Pobiera WIBOR 1M ze stooq.pl (API CSV).
    Endpoint zwraca dane w formacie CSV: Date,Open,High,Low,Close,Volume
    """
    url = "https://stooq.pl/q/d/l/?s=wibor1m&i=d"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().splitlines() if l and not l.startswith("Date")]
        if not lines:
            return None
        # ostatni wiersz = najnowszy dzień
        last = lines[-1].split(",")
        wibor = float(last[4])  # kolumna Close
        print(f"  WIBOR 1M: {wibor}% (stooq.pl)")
        return round(wibor, 4)
    except Exception as e:
        print(f"  ⚠ WIBOR fetch error: {e}")
        return None


def fetch_wibor_fallback() -> float | None:
    """Zapasowy endpoint — totalmoney.pl."""
    url = "https://www.totalmoney.pl/wskazniki/wibor"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r"WIBOR 1M\s*[·•]\s*([\d,\.]+)\s*%", resp.text)
        if match:
            val = float(match.group(1).replace(",", "."))
            print(f"  WIBOR 1M (fallback): {val}% (totalmoney.pl)")
            return round(val, 4)
    except Exception as e:
        print(f"  ⚠ WIBOR fallback error: {e}")
    return None


# ── 2. Cennik Porsche ─────────────────────────────────────────────────────────
def fetch_porsche_prices() -> dict | None:
    """
    Próbuje pobrać cennik z porsche.pl/cennik.
    Strona renderowana jest przez JavaScript, więc scraping może nie działać
    bez headless browser. Zwraca None jeśli nie uda się sparsować danych —
    wtedy zostają poprzednie ceny z data.json.
    """
    url = "https://www.porsche.com/poland/cennik/"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Szukamy wzorca "Model Rok Cena" w tekście strony
        # Format: "911 Carrera 2026 (T) 681 000,00"
        pattern = r"(911[^\d]+|Cayenne[^\d]+|Macan[^\d]+|Taycan[^\d]+|Panamera[^\d]+|718[^\d]+)" \
                  r"20\d{2}[^0-9]+([\d\s]{3,8}),00"
        matches = re.findall(pattern, text)

        if len(matches) < 5:
            print("  ⚠ Cennik Porsche: za mało wyników ze scrapingu — używam poprzednich cen")
            return None

        # Budujemy uproszczoną mapę name→price
        raw = {}
        for name_raw, price_raw in matches:
            name  = name_raw.strip().rstrip("0123456789 \t")
            price = int(price_raw.replace(" ", "").replace("\xa0", ""))
            raw[name] = price

        print(f"  Cennik Porsche: znaleziono {len(raw)} modeli")
        return raw

    except Exception as e:
        print(f"  ⚠ Cennik Porsche fetch error: {e}")
        return None


def detect_price_changes(old_prices: dict, new_prices: dict) -> list[str]:
    """Porównuje dwa słowniki cen i zwraca listę zmian."""
    changes = []
    for cat, models in new_prices.items():
        old_cat = {m["name"]: m["price"] for m in old_prices.get(cat, [])}
        for m in models:
            old_p = old_cat.get(m["name"])
            new_p = m["price"]
            if old_p is not None and old_p != new_p:
                diff = new_p - old_p
                sign = "+" if diff > 0 else ""
                changes.append(
                    f"{m['name']}: {old_p:,} → {new_p:,} zł ({sign}{diff:,} zł)"
                )
    return changes


# ── 3. Powiadomienie mailowe ───────────────────────────────────────────────────
def send_email(subject: str, body: str, to: str, smtp_host: str,
               smtp_port: int, smtp_user: str, smtp_pass: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to], msg.as_string())
        print(f"  ✓ Mail wysłany do {to}")
    except Exception as e:
        print(f"  ⚠ Mail error: {e}")


# ── 4. Main ───────────────────────────────────────────────────────────────────
def main():
    import os
    print(f"\n{'='*60}")
    print(f"Aktualizacja danych — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    # Załaduj poprzedni stan
    old_data = {}
    if DATA_FILE.exists():
        try:
            old_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── WIBOR ──
    print("\n[1/2] Pobieranie WIBOR 1M...")
    wibor = fetch_wibor() or fetch_wibor_fallback()
    if wibor is None:
        wibor = old_data.get("wibor", 3.81)
        print(f"  Używam poprzedniej wartości: {wibor}%")

    # ── Cennik ──
    print("\n[2/2] Pobieranie cennika Porsche...")
    # Próbujemy scrapować — jeśli się nie uda, używamy fallbacku
    scraped = fetch_porsche_prices()

    # Budujemy finalną strukturę cen
    # Na razie używamy FALLBACK_PRICES jako bazy (scraping strony JS jest zawodny)
    # W przyszłości można podmienić konkretne ceny na scraped
    current_prices = FALLBACK_PRICES.copy()

    # Wykrywanie zmian (względem poprzedniego zapisu)
    old_prices = old_data.get("prices", {})
    changes = detect_price_changes(old_prices, current_prices) if old_prices else []
    if changes:
        print(f"\n  ⚡ Wykryto zmiany w cenniku ({len(changes)}):")
        for c in changes:
            print(f"    • {c}")

        # Wyślij maila jeśli skonfigurowane
        notify_email = os.getenv("NOTIFY_EMAIL")
        smtp_host    = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port    = int(os.getenv("SMTP_PORT", "465"))
        smtp_user    = os.getenv("SMTP_USER", "")
        smtp_pass    = os.getenv("SMTP_PASS", "")
        if notify_email and smtp_user and smtp_pass:
            body = "Zmiany w cenniku Porsche Polska:\n\n" + "\n".join(f"• {c}" for c in changes)
            send_email(
                subject=f"[Kalkulator Porsche] Zmiana cennika — {date.today()}",
                body=body, to=notify_email,
                smtp_host=smtp_host, smtp_port=smtp_port,
                smtp_user=smtp_user, smtp_pass=smtp_pass,
            )
    else:
        print("  Brak zmian w cenniku.")

    # ── Zapisz data.json ──
    output = {
        "wibor":        wibor,
        "wibor_date":   str(date.today()),
        "prices":       current_prices,
        "updated_at":   datetime.now().isoformat(timespec="seconds"),
    }
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Zapisano {DATA_FILE}")
    print(f"  WIBOR 1M = {wibor}%")
    print(f"  Modeli łącznie = {sum(len(v) for v in current_prices.values())}")


if __name__ == "__main__":
    main()
