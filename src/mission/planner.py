
"""Planowanie trasy "kosiarką" (lawnmower) nad prostokątnym obszarem."""
import math
from dataclasses import dataclass
from pathlib import Path

from mission.geo import Punkt, odleglosc_m, przesun


@dataclass(frozen=True)
class Obszar:
    """Prostokąt do przeszukania.

    poczatek   - narożnik południowo-zachodni
    szerokosc_m - rozmiar w kierunku wschodnim
    glebokosc_m - rozmiar w kierunku północnym
    """

    poczatek: Punkt
    szerokosc_m: float
    glebokosc_m: float


def szerokosc_pola_widzenia_m(wysokosc_m: float, fov_stopnie: float) -> float:
    """Szerokość pasa terenu widzianego przez kamerę skierowaną w dół."""
    if wysokosc_m <= 0:
        raise ValueError("wysokosc_m musi być dodatnia")
    if not 0 < fov_stopnie < 180:
        raise ValueError("fov_stopnie musi być w przedziale (0, 180)")
    return 2 * wysokosc_m * math.tan(math.radians(fov_stopnie) / 2)


def rozstaw_pasow_m(wysokosc_m: float, fov_stopnie: float, zakladka: float) -> float:
    """Maksymalny odstęp między pasami, żeby sąsiednie pasy się nakładały."""
    if not 0 <= zakladka < 1:
        raise ValueError("zakladka musi być w przedziale [0, 1)")
    return szerokosc_pola_widzenia_m(wysokosc_m, fov_stopnie) * (1 - zakladka)


def trasa_kosiarka(obszar: Obszar, wysokosc_m: float, fov_stopnie: float, zakladka: float = 0.2) -> list[Punkt]:
    """Zwraca listę punktów trasy: pasy biegną na północ i południe, na zmianę.

    Pasy są rozłożone równomiernie na całej szerokości obszaru, a ich liczba
    jest tak dobrana, żeby odstęp nie przekroczył rozstawu wynikającego z kamery.
    """
    if obszar.szerokosc_m <= 0 or obszar.glebokosc_m <= 0:
        raise ValueError("wymiary obszaru muszą być dodatnie")

    rozstaw = rozstaw_pasow_m(wysokosc_m, fov_stopnie, zakladka)
    liczba_pasow = max(1, math.ceil(obszar.szerokosc_m / rozstaw))

    punkty: list[Punkt] = []
    for i in range(liczba_pasow):
        wschod_m = (i + 0.5) * obszar.szerokosc_m / liczba_pasow
        poludnie = przesun(obszar.poczatek, 0.0, wschod_m)
        polnoc = przesun(obszar.poczatek, obszar.glebokosc_m, wschod_m)
        punkty.extend([poludnie, polnoc] if i % 2 == 0 else [polnoc, poludnie])
    return punkty


def dlugosc_trasy_m(punkty: list[Punkt]) -> float:
    """Całkowita długość trasy (suma odcinków) w metrach."""
    return sum(odleglosc_m(a, b) for a, b in zip(punkty, punkty[1:]))


def zapisz_waypoints(punkty: list[Punkt], dom: Punkt, wysokosc_m: float, sciezka: Path) -> None:
    """Zapisuje trasę w formacie plików misji Mission Plannera / QGroundControl (.waypoints).

    Kolejność: punkt domowy, start (TAKEOFF), punkty trasy, powrót (RTL).
    """
    # kolumny: nr, current, frame, command, p1, p2, p3, p4, lat, lon, alt, autocontinue
    wiersze = [
        (0, 1, 0, 16, 0, 0, 0, 0, dom.lat, dom.lon, 0.0, 1),
        (1, 0, 3, 22, 0, 0, 0, 0, dom.lat, dom.lon, wysokosc_m, 1),
    ]
    for p in punkty:
        wiersze.append((len(wiersze), 0, 3, 16, 0, 0, 0, 0, p.lat, p.lon, wysokosc_m, 1))
    wiersze.append((len(wiersze), 0, 3, 20, 0, 0, 0, 0, 0.0, 0.0, 0.0, 1))

    linie = ["QGC WPL 110"]
    for w in wiersze:
        linie.append("\t".join(f"{x:.8f}" if isinstance(x, float) else str(x) for x in w))
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text("\n".join(linie) + "\n", encoding="utf-8")

def zageszcz(punkty: list[Punkt], krok_m: float) -> list[Punkt]:
    """Dodaje punkty pośrednie, tak by sąsiednie punkty były oddalone najwyżej o `krok_m`.

    Po co: kamera ma "rozejrzeć się" nie tylko na końcach pasów, ale też w trakcie przelotu.
    Pierwszy punkt zostaje bez zmian, każdy kolejny oryginalny punkt też trafia do wyniku.
    """
    if krok_m <= 0:
        raise ValueError("krok_m musi być dodatni")
    if not punkty:
        return []
    wynik = [punkty[0]]
    for a, b in zip(punkty, punkty[1:]):
        liczba_odcinkow = max(1, math.ceil(odleglosc_m(a, b) / krok_m - 1e-9))
        for k in range(1, liczba_odcinkow + 1):
            u = k / liczba_odcinkow
            wynik.append(Punkt(a.lat + (b.lat - a.lat) * u, a.lon + (b.lon - a.lon) * u))
    return wynik