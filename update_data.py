"""
Skrypt aktualizujący WIBOR 1M dla kalkulatora leasingu Porsche.
Uruchamiany codziennie przez GitHub Actions o 7:00.

Pobiera: aktualny WIBOR 1M ze stooq.pl (z fallbackiem na totalmoney.pl)
NIE aktualizuje cennika automatycznie — ceny wpisywane ręcznie w index.html.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

import requests

DATA_DIR  = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "data.json"
DATA_DIR.mkdir(exist_ok=True)


def fetch_wibor_stooq() -> float | None:
    """Pobiera WIBOR 1M ze stooq.pl — API CSV, nie wymaga parsowania HTML."""
    url = "https://stooq.pl/q/d/l/?s=wibor1m&i=d"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().splitlines() if l and not l.startswith("Date")]
        if not lines:
            return None
        last  = lines[-1].split(",")
        wibor = float(last[4])   # kolumna Close = wartość na zamknięcie dnia
        print(f"  ✓ WIBOR 1M = {wibor}% (stooq.pl, {lines[-1].split(',')[0]})")
        return round(wibor, 4)
    except Exception as e:
        print(f"  ⚠ stooq.pl error: {e}")
        return None


def fetch_wibor_totalmoney() -> float | None:
    """Fallback — totalmoney.pl (scraping tekstu strony)."""
    url = "https://www.totalmoney.pl/wskazniki/wibor"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        match = re.search(r"WIBOR 1M\s*[·•\-]\s*([\d,\.]+)\s*%", resp.text)
        if match:
            val = float(match.group(1).replace(",", "."))
            print(f"  ✓ WIBOR 1M = {val}% (totalmoney.pl — fallback)")
            return round(val, 4)
        print("  ⚠ totalmoney.pl: nie znaleziono wartości")
    except Exception as e:
        print(f"  ⚠ totalmoney.pl error: {e}")
    return None


def main():
    print(f"\n{'='*55}")
    print(f"  Aktualizacja WIBOR 1M — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    # Załaduj poprzedni stan
    old_data: dict = {}
    if DATA_FILE.exists():
        try:
            old_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Pobierz WIBOR
    print("\nPobieranie WIBOR 1M...")
    wibor = fetch_wibor_stooq() or fetch_wibor_totalmoney()

    if wibor is None:
        wibor = old_data.get("wibor", 3.81)
        print(f"  ⚠ Nie udało się pobrać — używam poprzedniej wartości: {wibor}%")
    else:
        prev = old_data.get("wibor")
        if prev is not None and prev != wibor:
            diff = round(wibor - prev, 4)
            sign = "+" if diff > 0 else ""
            print(f"  ↕ Zmiana względem poprzedniego odczytu: {prev}% → {wibor}% ({sign}{diff}pp)")

    # Zapisz data.json
    output = {
        "wibor":      wibor,
        "wibor_date": str(date.today()),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Cennik Porsche aktualizowany ręcznie w index.html. Tylko WIBOR jest pobierany automatycznie."
    }

    DATA_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✓ Zapisano {DATA_FILE}")
    print(f"  WIBOR 1M = {wibor}%  ({date.today()})")


if __name__ == "__main__":
    main()
