"""Dzień 3: pełna misja - start, szukanie celu kamerą, potwierdzenie, zrzut, powrót.

Z symulatorem:        python scripts/misja.py --connect tcp:127.0.0.1:5762
Bez symulatora:       python scripts/misja.py --atrapa
"""
import argparse
import logging
from pathlib import Path

from mission.atrapy import AtrapaDrona
from mission.geo import odleglosc_m, przesun
from mission.planner import Obszar, dlugosc_trasy_m, trasa_kosiarka, zageszcz, zapisz_waypoints
from mission.sensors.simulated_camera import WirtualnaKamera, wczytaj_cele
from mission.state_machine import Misja, Ustawienia, Wynik
from mission.vehicle import BladPojazdu, MavlinkPojazd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", default="tcp:127.0.0.1:5762")
    parser.add_argument("--atrapa", action="store_true", help="atrapa drona zamiast symulatora")
    parser.add_argument("--cele", default="data/cele.yaml", help="plik YAML z celami")
    parser.add_argument("--bez-celu", action="store_true", help="kamera nie ma czego znaleźć")
    parser.add_argument("--alt", type=float, default=20.0, help="wysokość lotu [m]")
    parser.add_argument("--fov", type=float, default=60.0, help="kąt widzenia kamery [stopnie]")
    parser.add_argument("--szerokosc", type=float, default=60.0, help="szerokość obszaru (wschód) [m]")
    parser.add_argument("--glebokosc", type=float, default=40.0, help="głębokość obszaru (północ) [m]")
    parser.add_argument("--krok", type=float, default=5.0, help="co ile metrów kamera się rozgląda")
    parser.add_argument("--falszywe", type=float, default=0.02, help="prawdopodobieństwo fałszywego alarmu na spojrzenie")
    parser.add_argument("--seed", type=int, default=42, help="ziarno losowości kamery")
    parser.add_argument("--out", default="output/trasa.waypoints")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("misja")

    pojazd = AtrapaDrona() if args.atrapa else MavlinkPojazd(args.connect)
    try:
        pojazd.polacz()
        dom, _ = pojazd.pozycja()
    except BladPojazdu as blad:
        log.error("Nie udało się połączyć: %s", blad)
        raise SystemExit(1)

    cele = [] if args.bez_celu else wczytaj_cele(Path(args.cele), dom)
    kamera = WirtualnaKamera(cele, fov_stopnie=args.fov, p_falszywy_alarm=args.falszywe, seed=args.seed)

    obszar = Obszar(przesun(dom, 10, 10), args.szerokosc, args.glebokosc)
    trasa = zageszcz(trasa_kosiarka(obszar, args.alt, args.fov), args.krok)
    log.info("Trasa: %d punktów kontrolnych, %.0f m", len(trasa), dlugosc_trasy_m(trasa))
    zapisz_waypoints(trasa_kosiarka(obszar, args.alt, args.fov), dom, args.alt, Path(args.out))

    wynik = Misja(pojazd, kamera, trasa, Ustawienia(wysokosc_m=args.alt)).uruchom()

    print()
    print(f"Wynik misji: {wynik.wynik.name} ({wynik.wynik.value})")
    print("Stany: " + " -> ".join(s.value for s in wynik.historia))
    if wynik.powod_przerwania:
        print(f"Powód przerwania: {wynik.powod_przerwania}")
    if wynik.wynik is Wynik.SUKCES and cele:
        blad_m = odleglosc_m(wynik.pozycja_zrzutu, cele[0].polozenie)
        print(f"Zrzut {blad_m:.1f} m od prawdziwego celu '{cele[0].nazwa}'")


if __name__ == "__main__":
    main()