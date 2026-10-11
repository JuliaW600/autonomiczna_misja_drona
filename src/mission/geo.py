"""Proste obliczenia geograficzne dla małych obszarów (kilkaset metrów).

Przybliżenie: w okolicy punktu odniesienia Ziemia jest "płaska", a
1 stopień szerokości geograficznej to stały dystans w metrach.
"""
import math
from dataclasses import dataclass

METROW_NA_STOPIEN = 111_320.0


@dataclass(frozen=True)
class Punkt:
    """Punkt na Ziemi: szerokość (lat) i długość (lon) geograficzna w stopniach."""

    lat: float
    lon: float


def przesun(punkt: Punkt, polnoc_m: float, wschod_m: float) -> Punkt:
    """Zwraca punkt przesunięty o podaną liczbę metrów na północ i na wschód."""
    lat = punkt.lat + polnoc_m / METROW_NA_STOPIEN
    lon = punkt.lon + wschod_m / (METROW_NA_STOPIEN * math.cos(math.radians(punkt.lat)))
    return Punkt(lat, lon)


def wspolrzedne_lokalne(poczatek: Punkt, punkt: Punkt) -> tuple[float, float]:
    """Zwraca (północ_m, wschód_m) punktu względem punktu początkowego."""
    polnoc_m = (punkt.lat - poczatek.lat) * METROW_NA_STOPIEN
    wschod_m = (punkt.lon - poczatek.lon) * METROW_NA_STOPIEN * math.cos(math.radians(poczatek.lat))
    return polnoc_m, wschod_m


def odleglosc_m(a: Punkt, b: Punkt) -> float:
    """Odległość w poziomie między dwoma punktami, w metrach."""
    polnoc_m, wschod_m = wspolrzedne_lokalne(a, b)
    return math.hypot(polnoc_m, wschod_m)