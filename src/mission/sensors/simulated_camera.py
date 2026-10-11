"""Wirtualna kamera: symulator ArduPilota nie ma kamery, więc "widzi" cele z pliku YAML."""
import math
import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from mission.geo import Punkt, przesun, wspolrzedne_lokalne
from mission.sensors.base import Czujnik, Detekcja


@dataclass(frozen=True)
class Cel:
    nazwa: str
    polozenie: Punkt


def wczytaj_cele(sciezka: Path, dom: Punkt) -> list[Cel]:
    """Wczytuje cele z YAML. Pozycje w pliku to metry od miejsca startu drona (`dom`)."""
    dane = yaml.safe_load(Path(sciezka).read_text(encoding="utf-8"))
    if not isinstance(dane, dict) or "cele" not in dane:
        raise ValueError(f"{sciezka}: brak klucza 'cele'")
    cele = []
    for i, wpis in enumerate(dane["cele"] or [], start=1):
        try:
            polnoc_m = float(wpis["polnoc_m"])
            wschod_m = float(wpis["wschod_m"])
        except (KeyError, TypeError, ValueError) as blad:
            raise ValueError(f"{sciezka}: cel nr {i} musi mieć liczby 'polnoc_m' i 'wschod_m'") from blad
        cele.append(Cel(str(wpis.get("nazwa", f"cel_{i}")), przesun(dom, polnoc_m, wschod_m)))
    return cele


class WirtualnaKamera(Czujnik):
    """Kamera skierowana prosto w dół, widząca kwadrat o boku `2 * wysokość * tan(FOV / 2)`.

    Cel w polu widzenia jest wykrywany z prawdopodobieństwem `p_wykrycia`, a jego
    pozycja jest zaszumiona (`szum_m`). Dodatkowo kamera potrafi zgłosić fałszywy alarm.
    Ziarno (`seed`) sprawia, że losowość jest powtarzalna, więc testy też.
    """

    def __init__(
        self,
        cele: list[Cel],
        fov_stopnie: float = 60.0,
        p_wykrycia: float = 0.9,
        szum_m: float = 1.0,
        p_falszywy_alarm: float = 0.0,
        seed: int = 0,
    ):
        if not 0 < fov_stopnie < 180:
            raise ValueError("fov_stopnie musi być w przedziale (0, 180)")
        for nazwa, wartosc in (("p_wykrycia", p_wykrycia), ("p_falszywy_alarm", p_falszywy_alarm)):
            if not 0 <= wartosc <= 1:
                raise ValueError(f"{nazwa} musi być w przedziale [0, 1]")
        if szum_m < 0:
            raise ValueError("szum_m nie może być ujemny")
        self.cele = list(cele)
        self.fov_stopnie = fov_stopnie
        self.p_wykrycia = p_wykrycia
        self.szum_m = szum_m
        self.p_falszywy_alarm = p_falszywy_alarm
        self._los = random.Random(seed)

    def wykryj(self, pozycja: Punkt, wysokosc_m: float) -> list[Detekcja]:
        if wysokosc_m <= 0:
            return []
        polowa_boku_m = wysokosc_m * math.tan(math.radians(self.fov_stopnie) / 2)
        wykrycia = []
        for cel in self.cele:
            polnoc_m, wschod_m = wspolrzedne_lokalne(pozycja, cel.polozenie)
            w_polu_widzenia = abs(polnoc_m) <= polowa_boku_m and abs(wschod_m) <= polowa_boku_m
            if w_polu_widzenia and self._los.random() < self.p_wykrycia:
                zaszumiony = przesun(
                    cel.polozenie,
                    self._los.gauss(0, self.szum_m),
                    self._los.gauss(0, self.szum_m),
                )
                wykrycia.append(Detekcja(zaszumiony, self._los.uniform(0.7, 1.0)))
        if self._los.random() < self.p_falszywy_alarm:
            falszywy = przesun(
                pozycja,
                self._los.uniform(-polowa_boku_m, polowa_boku_m),
                self._los.uniform(-polowa_boku_m, polowa_boku_m),
            )
            wykrycia.append(Detekcja(falszywy, self._los.uniform(0.3, 0.6)))
        return wykrycia