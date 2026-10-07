"""
Skrypt aktualizujący WIBOR 1M dla kalkulatora leasingu Porsche.
Uruchamiany w dni robocze przez GitHub Actions (.github/workflows/update-wibor.yml).

Pobiera: aktualny WIBOR 1M ze stooq.pl (z fallbackiem na totalmoney.pl)
Zapisuje: data/data.json w GŁÓWNYM folderze repozytorium (czyta go kalkulator.html).
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

import requests

# Skrypt leży w .github/workflows/ -> główny folder repo to 2 poziomy wyżej
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR  = REPO_ROOT / "data"
DATA_FILE = DATA_DIR / "data.json"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; wibor-updater/1.0)"}


def valid(v):
    """WIBOR musi być sensowną liczbą (chroni przed zapisaniem śmieci)."""
    return v is not None and 0 < v < 25


def fetch_wibor_stooq():
    """stooq.pl — CSV z historią dzienną. Próbuje kilku symboli WIBOR 1M."""
    for symbol in ("plopln1m", "wibor1m"):
        url = f"https://stooq.pl/q/d/l/?s={symbol}&i=d"
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS)
            resp.raise_for_status()
            rows = [l for l in resp.text.strip().splitlines()
                    if l and l[0].isdigit() and l.count(",") >= 4]
            if not rows:
                print(f"  ⚠ stooq.pl ({symbol}): brak danych w odpowiedzi: {resp.text[:80]!r}")
                continue
            last = rows[-1].split(",")
            wibor = round(float(last[4]), 4)          # kolumna Close
            if valid(wibor):
                print(f"  ✓ WIBOR 1M = {wibor}% (stooq.pl/{symbol}, {last[0]})")
                return wibor, last[0]
        except Exception as e:
            print(f"  ⚠ stooq.pl ({symbol}) error: {e}")
    return None, None


def fetch_wibor_totalmoney():
    """Fallback — totalmoney.pl (wyszukanie wartości w tekście strony)."""
    url = "https://www.totalmoney.pl/wskazniki/wibor"
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        text = re.sub(r"<[^>]+>", " ", resp.text)      # usuń tagi HTML
        text = re.sub(r"\s+", " ", text)
        match = re.search(r"WIBOR\s*1M\D{0,40}?(\d{1,2}[,\.]\d{1,4})\s*%", text, re.I)
        if match:
            val = round(float(match.group(1).replace(",", ".")), 4)
            if valid(val):
                print(f"  ✓ WIBOR 1M = {val}% (totalmoney.pl — fallback)")
                return val, str(date.today())
        print("  ⚠ totalmoney.pl: nie znaleziono wartości")
    except Exception as e:
        print(f"  ⚠ totalmoney.pl error: {e}")
    return None, None


def main():
    print(f"\n{'=' * 55}")
    print(f"  Aktualizacja WIBOR 1M — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Plik: {DATA_FILE}")
    print(f"{'=' * 55}")

    old = {}
    if DATA_FILE.exists():
        try:
            old = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    wibor, wibor_date = fetch_wibor_stooq()
    if wibor is None:
        wibor, wibor_date = fetch_wibor_totalmoney()

    if wibor is None:
        # Nie nadpisuj daty — kalkulator pokaże, z kiedy jest ostatnia znana stawka
        print(f"  ✗ Nie udało się pobrać — zostawiam poprzednią wartość: {old.get('wibor')}%")
        raise SystemExit(1)   # czerwony status w Actions = widać, że coś nie działa

    prev = old.get("wibor")
    if prev is not None and prev != wibor:
        print(f"  ↕ Zmiana: {prev}% → {wibor}% ({wibor - prev:+.4f} pp)")

    output = {
        "wibor": wibor,
        "wibor_date": wibor_date,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "WIBOR 1M pobierany automatycznie. Cennik w kalkulator.html (CATALOG)."
    }
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Zapisano {DATA_FILE}: WIBOR 1M = {wibor}% ({wibor_date})")


if __name__ == "__main__":
    main()
