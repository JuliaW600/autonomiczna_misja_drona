"""Atrapy do testów: "udają" drona i czujnik, więc misję można sprawdzić bez symulatora.

Atrapa drona natychmiast "dolatuje" gdziekolwiek, zapisuje każdą komendę, a na życzenie
zgłasza awarię. Dzięki temu testy trwają ułamek sekundy i można je powtarzać bez końca.
"""
from mission.geo import Punkt
from mission.sensors.base import Czujnik, Detekcja
from mission.vehicle import BladPojazdu, Pojazd

DOM_DOMYSLNY = Punkt(-35.363261, 149.165230)


class AtrapaDrona(Pojazd):
    """`awarie` to słownik {nazwa operacji: ile razy ma się udać, zanim zacznie zawodzić}.

    Przykład: {"lec_do": 3} - trzy loty się udadzą, czwarty zgłosi BladPojazdu;
    {"uzbroj": 0} - uzbrojenie zawodzi od razu.
    """

    def __init__(self, dom: Punkt = DOM_DOMYSLNY, awarie: dict[str, int] | None = None):
        self.dom = dom
        self.uzbrojony = False
        self.zrzucono = False
        self.pozycja_zrzutu: Punkt | None = None
        self.komendy: list[tuple] = []
        self._polozenie = dom
        self._wysokosc = 0.0
        self._awarie = dict(awarie or {})
        self._udane: dict[str, int] = {}

    def _wykonaj(self, nazwa: str, *argumenty) -> None:
        self.komendy.append((nazwa, *argumenty))
        if nazwa in self._awarie and self._udane.get(nazwa, 0) >= self._awarie[nazwa]:
            raise BladPojazdu(f"Atrapa: zasymulowana awaria operacji '{nazwa}'")
        self._udane[nazwa] = self._udane.get(nazwa, 0) + 1

    def polacz(self, limit_s: float = 30) -> None:
        self._wykonaj("polacz")

    def pozycja(self) -> tuple[Punkt, float]:
        return self._polozenie, self._wysokosc

    def uzbroj(self, limit_s: float = 120) -> None:
        self._wykonaj("uzbroj")
        self.uzbrojony = True

    def wystartuj(self, wysokosc_m: float, limit_s: float = 60) -> None:
        self._wykonaj("wystartuj", wysokosc_m)
        self._wysokosc = wysokosc_m

    def lec_do(self, cel: Punkt, wysokosc_m: float, tolerancja_m: float = 3.0, limit_s: float = 120) -> None:
        self._wykonaj("lec_do", cel)
        self._polozenie = cel
        self._wysokosc = wysokosc_m

    def zrzut(self, limit_s: float = 10) -> None:
        self._wykonaj("zrzut")
        self.zrzucono = True
        self.pozycja_zrzutu = self._polozenie

    def wroc_i_laduj(self, limit_s: float = 180) -> None:
        self._wykonaj("wroc_i_laduj")
        self._polozenie = self.dom
        self._wysokosc = 0.0
        self.uzbrojony = False

    def nazwy_komend(self) -> list[str]:
        return [komenda[0] for komenda in self.komendy]


class CzujnikZeSkryptem(Czujnik):
    """Czujnik odpowiadający według scenariusza: kolejne wywołania dostają kolejne odpowiedzi z listy.

    Gdy lista się skończy, czujnik nic już nie widzi. Pozwala w teście dokładnie ustawić
    np. "pierwszy raz widzę coś, a przy sprawdzeniu już nic" (fałszywy alarm).
    """

    def __init__(self, odpowiedzi: list[list[Detekcja]]):
        self._odpowiedzi = list(odpowiedzi)
        self.wywolania: list[tuple[Punkt, float]] = []

    def wykryj(self, pozycja: Punkt, wysokosc_m: float) -> list[Detekcja]:
        self.wywolania.append((pozycja, wysokosc_m))
        return self._odpowiedzi.pop(0) if self._odpowiedzi else []