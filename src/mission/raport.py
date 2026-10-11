"""Raport z misji: krótkie podsumowanie dla człowieka i plik JSON dla maszyn."""
import json
from pathlib import Path

from mission.geo import Punkt
from mission.state_machine import WynikMisji


def _punkt(p: Punkt | None) -> dict | None:
    return None if p is None else {"lat": round(p.lat, 7), "lon": round(p.lon, 7)}


def raport_jako_slownik(wynik: WynikMisji, scenariusz: str | None = None) -> dict:
    return {
        "scenariusz": scenariusz,
        "wynik": wynik.wynik.name,
        "opis_wyniku": wynik.wynik.value,
        "alarm": None if wynik.alarm is None else wynik.alarm.name,
        "powod_przerwania": wynik.powod_przerwania,
        "czas_misji_s": round(wynik.czas_misji_s, 1),
        "historia_stanow": [s.value for s in wynik.historia],
        "cel": _punkt(wynik.cel),
        "pozycja_zrzutu": _punkt(wynik.pozycja_zrzutu),
    }


def zapisz_raport(wynik: WynikMisji, sciezka: Path, scenariusz: str | None = None) -> None:
    sciezka = Path(sciezka)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tresc = json.dumps(raport_jako_slownik(wynik, scenariusz), ensure_ascii=False, indent=2)
    sciezka.write_text(tresc + "\n", encoding="utf-8")


def podsumowanie(wynik: WynikMisji) -> str:
    linie = [
        f"Wynik misji: {wynik.wynik.name} ({wynik.wynik.value})",
        "Stany: " + " -> ".join(s.value for s in wynik.historia),
        f"Czas misji: {wynik.czas_misji_s:.0f} s",
    ]
    if wynik.alarm is not None:
        linie.append(f"Alarm: {wynik.alarm.name} ({wynik.alarm.value})")
    if wynik.powod_przerwania:
        linie.append(f"Powód przerwania: {wynik.powod_przerwania}")
    return "\n".join(linie)