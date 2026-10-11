"""Dzień 2: dron startuje, przelatuje trasę "kosiarką" nad prostokątem i wraca.

Użycie:  python scripts/lec_trase.py --connect tcp:127.0.0.1:5762
"""
import argparse
import logging
from pathlib import Path

from mission.geo import przesun
from mission.planner import Obszar, dlugosc_trasy_m, trasa_kosiarka, zapisz_waypoints
from mission.vehicle import MavlinkPojazd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", default="tcp:127.0.0.1:5762")
    parser.add_argument("--alt", type=float, default=20.0, help="wysokość lotu [m]")
    parser.add_argument("--fov", type=float, default=60.0, help="kąt widzenia kamery [stopnie]")
    parser.add_argument("--szerokosc", type=float, default=60.0, help="szerokość obszaru (wschód) [m]")
    parser.add_argument("--glebokosc", type=float, default=40.0, help="głębokość obszaru (północ) [m]")
    parser.add_argument("--out", default="output/trasa.waypoints", help="plik misji dla Mission Plannera")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("lec_trase")

    dron = MavlinkPojazd(args.connect)
    dron.polacz()
    dom, _ = dron.pozycja()

    # Obszar zaczyna się 10 m na północ i 10 m na wschód od miejsca startu.
    obszar = Obszar(przesun(dom, 10, 10), args.szerokosc, args.glebokosc)
    trasa = trasa_kosiarka(obszar, args.alt, args.fov)
    log.info("Trasa: %d punktów, %.0f m", len(trasa), dlugosc_trasy_m(trasa))
    zapisz_waypoints(trasa, dom, args.alt, Path(args.out))
    log.info("Zapisano plik misji: %s", args.out)

    dron.uzbroj()
    dron.wystartuj(args.alt)
    for i, punkt in enumerate(trasa, start=1):
        log.info("Punkt %d/%d", i, len(trasa))
        dron.lec_do(punkt, args.alt)
    dron.wroc_i_laduj()
    log.info("Koniec misji")


if __name__ == "__main__":
    main()