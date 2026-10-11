"""Dzień 4: uruchamia scenariusze testowe (pliki YAML z config/scenarios) i sprawdza, czy wynik jest taki, jak oczekiwano.

Na atrapie (bez symulatora, kilka sekund):
    python scripts/scenariusz.py --wszystkie --atrapa
W symulatorze (pojedynczy scenariusz):
    python scripts/scenariusz.py config/scenarios/04_slaba_bateria.yaml --connect tcp:127.0.0.1:5762
"""
import argparse
import logging
from pathlib import Path

from mission.atrapy import AtrapaDrona
from mission.raport import podsumowanie, zapisz_raport
from mission.scenariusz import sprawdz_oczekiwania, uruchom_scenariusz, wczytaj_scenariusz, wczytaj_wszystkie
from mission.vehicle import BladPojazdu, MavlinkPojazd
from mission.zegar import ZegarSztuczny


def uruchom_jeden(scenariusz, args, polaczony_pojazd):
    print(f"\n=== Scenariusz: {scenariusz.nazwa} ===\n{scenariusz.opis}\n")
    if args.atrapa:
        zegar = ZegarSztuczny()
        pojazd = AtrapaDrona(zegar=zegar, czas_komendy_s=scenariusz.czas_komendy_s)
        pojazd.polacz()
    else:
        zegar = None
        pojazd = polaczony_pojazd
        pojazd.przywroc_awarie()
    try:
        wynik = uruchom_scenariusz(scenariusz, pojazd, zegar, args.limit_czasu)
    finally:
        if not args.atrapa:
            pojazd.przywroc_awarie()
    print("\n" + podsumowanie(wynik))
    zapisz_raport(wynik, Path(args.raporty) / f"{scenariusz.nazwa}.json", scenariusz.nazwa)
    problemy = sprawdz_oczekiwania(scenariusz, wynik, pojazd if args.atrapa else None)
    for problem in problemy:
        print(f"  NIEZGODNE Z OCZEKIWANIEM: {problem}")
    return not problemy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pliki", nargs="*", help="pliki scenariuszy (YAML)")
    parser.add_argument("--wszystkie", action="store_true", help="wszystkie scenariusze z config/scenarios")
    parser.add_argument("--atrapa", action="store_true", help="atrapa drona zamiast symulatora")
    parser.add_argument("--connect", default="tcp:127.0.0.1:5762")
    parser.add_argument("--limit-czasu", type=float, default=None, help="nadpisz limit czasu misji [s]")
    parser.add_argument("--raporty", default="output/raporty", help="folder na raporty JSON")
    args = parser.parse_args()
    if not args.pliki and not args.wszystkie:
        parser.error("podaj plik scenariusza albo --wszystkie")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scenariusze = wczytaj_wszystkie(Path("config/scenarios")) if args.wszystkie else []
    scenariusze += [wczytaj_scenariusz(Path(p)) for p in args.pliki]

    pojazd = None
    if not args.atrapa:
        pojazd = MavlinkPojazd(args.connect)
        try:
            pojazd.polacz()
        except BladPojazdu as blad:
            logging.error("Nie udało się połączyć: %s", blad)
            raise SystemExit(1)

    wyniki = {}
    for scenariusz in scenariusze:
        if scenariusz.tylko_atrapa and not args.atrapa:
            print(f"\n=== Scenariusz: {scenariusz.nazwa} === pominięty (da się go uruchomić tylko na atrapie)")
            continue
        wyniki[scenariusz.nazwa] = uruchom_jeden(scenariusz, args, pojazd)

    print("\n=== PODSUMOWANIE ===")
    for nazwa, zaliczony in wyniki.items():
        print(f"  {'ZALICZONY   ' if zaliczony else 'NIEZALICZONY'}  {nazwa}")
    if not all(wyniki.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()