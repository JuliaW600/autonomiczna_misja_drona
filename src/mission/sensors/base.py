"""Wspólny interfejs czujników. Logika misji zna tylko to, nie konkretną kamerę."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from mission.geo import Punkt


@dataclass(frozen=True)
class Detekcja:
    """Wynik wykrycia: gdzie algorytm uważa, że jest cel, i jak bardzo jest tego pewny (0..1)."""

    polozenie: Punkt
    pewnosc: float


class Czujnik(ABC):
    @abstractmethod
    def wykryj(self, pozycja: Punkt, wysokosc_m: float) -> list[Detekcja]:
        """Zwraca wykrycia widoczne z kamery zawieszonej nad `pozycja` na wysokości `wysokosc_m`."""