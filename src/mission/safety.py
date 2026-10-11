"""Monitor bezpieczeństwa: czysta funkcja, która ocenia stan drona i zwraca alarm albo nic.

Czysta funkcja = to samo wejście daje zawsze ten sam wynik, bez losowości i bez zegara w środku.
Dlatego każdy alarm da się przetestować jedną linijką, bez drona i bez symulatora.
"""
from dataclasses import dataclass
from enum import Enum

from mission.geo import Punkt, wspolrzedne_lokalne
from mission.vehicle import Telemetria


class Alarm(Enum):
    UTRATA_LACZNOSCI = "brak łączności z dronem"
    UTRATA_GPS = "utrata sygnału GPS"
    SLABA_BATERIA = "zbyt niski poziom baterii"
    POZA_OBSZAREM = "dron opuścił dozwoloną strefę"
    PRZEKROCZONY_CZAS = "przekroczony limit czasu misji"


@dataclass(frozen=True)
class Strefa:
    """Prostokąt dozwolony dla drona, w metrach względem miejsca startu (północ i wschód)."""

    polnoc_min_m: float
    polnoc_max_m: float
    wschod_min_m: float
    wschod_max_m: float

    def __post_init__(self):
        if self.polnoc_min_m >= self.polnoc_max_m or self.wschod_min_m >= self.wschod_max_m:
            raise ValueError("strefa: minimum musi być mniejsze od maksimum (północ i wschód)")

    def zawiera(self, polnoc_m: float, wschod_m: float) -> bool:
        return (
            self.polnoc_min_m <= polnoc_m <= self.polnoc_max_m
            and self.wschod_min_m <= wschod_m <= self.wschod_max_m
        )


@dataclass(frozen=True)
class Limity:
    min_bateria_proc: float = 30.0
    min_napiecie_v: float = 10.8
    min_fix_gps: int = 3
    max_wiek_heartbeat_s: float = 5.0
    czas_misji_s: float = 600.0
    strefa: Strefa | None = None


def sprawdz(telemetria: Telemetria, pozycja: Punkt, dom: Punkt, czas_misji_s: float, limity: Limity = Limity()) -> Alarm | None:
    """Zwraca najważniejszy aktywny alarm albo None. Kolejność kontroli = ważność alarmów.

    Pole telemetrii równe `None` znaczy "nie wiem" i nie powoduje alarmu.
    """
    if telemetria.wiek_heartbeat_s > limity.max_wiek_heartbeat_s:
        return Alarm.UTRATA_LACZNOSCI
    if telemetria.fix_gps is not None and telemetria.fix_gps < limity.min_fix_gps:
        return Alarm.UTRATA_GPS
    if telemetria.bateria_proc is not None and telemetria.bateria_proc < limity.min_bateria_proc:
        return Alarm.SLABA_BATERIA
    if telemetria.napiecie_v is not None and telemetria.napiecie_v < limity.min_napiecie_v:
        return Alarm.SLABA_BATERIA
    if limity.strefa is not None:
        polnoc_m, wschod_m = wspolrzedne_lokalne(dom, pozycja)
        if not limity.strefa.zawiera(polnoc_m, wschod_m):
            return Alarm.POZA_OBSZAREM
    if czas_misji_s > limity.czas_misji_s:
        return Alarm.PRZEKROCZONY_CZAS
    return None