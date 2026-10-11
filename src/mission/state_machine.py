"""Maszyna stanów misji: przygotowanie, start, szukanie, potwierdzenie, zrzut, powrót.

Przed każdym krokiem w powietrzu misja pyta monitor bezpieczeństwa (`safety.sprawdz`).
Alarm przerywa szukanie: zwykle dron wraca do bazy, a przy utracie GPS ląduje w miejscu.

W każdej chwili misja jest w dokładnie jednym stanie. Każdy stan to jedna metoda,
która coś robi i zwraca stan następny. Dzięki temu łatwo sprawdzić w teście,
którędy poszła misja (`WynikMisji.historia`) i co się stało, gdy coś zawiodło.
"""
import logging
from dataclasses import dataclass
from enum import Enum

from mission.geo import Punkt, odleglosc_m, srednia_pozycja
from mission.safety import Alarm, Limity, sprawdz
from mission.sensors.base import Czujnik, Detekcja
from mission.vehicle import BladPojazdu, Pojazd
from mission.zegar import Zegar, ZegarSystemowy

log = logging.getLogger(__name__)


class Stan(Enum):
    PRZYGOTOWANIE = "przygotowanie"
    STARTOWANIE = "startowanie"
    SZUKANIE = "szukanie"
    POTWIERDZANIE = "potwierdzanie"
    ZRZUT = "zrzut"
    POWROT = "powrót"
    LADOWANIE_AWARYJNE = "lądowanie awaryjne"
    KONIEC = "koniec"


class Wynik(Enum):
    SUKCES = "cel znaleziony i ładunek zrzucony"
    NIE_ZNALEZIONO = "obszar przeszukany, celu nie znaleziono"
    PRZERWANA = "misja przerwana (błąd drona lub alarm bezpieczeństwa)"


@dataclass(frozen=True)
class Ustawienia:
    wysokosc_m: float = 20.0
    liczba_potwierdzen: int = 3
    wymagane_potwierdzenia: int = 2
    promien_potwierdzenia_m: float = 6.0
    tolerancja_zrzutu_m: float = 2.0


@dataclass(frozen=True)
class WynikMisji:
    wynik: Wynik
    historia: tuple[Stan, ...]
    cel: Punkt | None = None
    pozycja_zrzutu: Punkt | None = None
    powod_przerwania: str | None = None
    alarm: Alarm | None = None
    czas_misji_s: float = 0.0


class Misja:
    def __init__(
        self,
        pojazd: Pojazd,
        czujnik: Czujnik,
        trasa: list[Punkt],
        ustawienia: Ustawienia = Ustawienia(),
        limity: Limity = Limity(),
        zegar: Zegar | None = None,
    ):
        if not trasa:
            raise ValueError("trasa nie może być pusta")
        if not 1 <= ustawienia.wymagane_potwierdzenia <= ustawienia.liczba_potwierdzen:
            raise ValueError("wymagane_potwierdzenia musi mieścić się w przedziale 1..liczba_potwierdzen")
        self.pojazd = pojazd
        self.czujnik = czujnik
        self.trasa = trasa
        self.ustawienia = ustawienia
        self.limity = limity
        self.zegar = zegar or ZegarSystemowy()
        self._start = 0.0
        self._dom: Punkt | None = None
        self._alarm: Alarm | None = None
        self._nastepny_punkt = 0
        self._kandydat: Detekcja | None = None
        self._cel: Punkt | None = None
        self._pozycja_zrzutu: Punkt | None = None
        self._wynik = Wynik.NIE_ZNALEZIONO
        self._powod: str | None = None
        self._historia: list[Stan] = []
        self._obsluga = {
            Stan.PRZYGOTOWANIE: self._przygotowanie,
            Stan.STARTOWANIE: self._startowanie,
            Stan.SZUKANIE: self._szukanie,
            Stan.POTWIERDZANIE: self._potwierdzanie,
            Stan.ZRZUT: self._zrzut,
            Stan.POWROT: self._powrot,
            Stan.LADOWANIE_AWARYJNE: self._ladowanie_awaryjne,
        }

    def uruchom(self) -> WynikMisji:
        self._start = self.zegar.teraz()
        stan = Stan.PRZYGOTOWANIE
        while stan is not Stan.KONIEC:
            log.info("Stan: %s", stan.value)
            self._historia.append(stan)
            try:
                if stan in (Stan.POTWIERDZANIE, Stan.ZRZUT):
                    stan_po_alarmie = self._sprawdz_bezpieczenstwo()
                    if stan_po_alarmie is not None:
                        stan = stan_po_alarmie
                        continue
                stan = self._obsluga[stan]()
            except BladPojazdu as blad:
                log.error("Błąd w stanie '%s': %s", stan.value, blad)
                self._wynik = Wynik.PRZERWANA
                self._powod = str(blad)
                konczace = (Stan.PRZYGOTOWANIE, Stan.POWROT, Stan.LADOWANIE_AWARYJNE)
                stan = Stan.KONIEC if stan in konczace else Stan.POWROT
        self._historia.append(Stan.KONIEC)
        log.info("Wynik misji: %s", self._wynik.value)
        return WynikMisji(
            self._wynik,
            tuple(self._historia),
            self._cel,
            self._pozycja_zrzutu,
            self._powod,
            self._alarm,
            self._czas_misji(),
        )

    def _czas_misji(self) -> float:
        return self.zegar.teraz() - self._start

    def _sprawdz_bezpieczenstwo(self) -> Stan | None:
        """Zwraca stan, do którego trzeba przejść z powodu alarmu, albo None, gdy wszystko w porządku."""
        pozycja, _ = self.pojazd.pozycja()
        alarm = sprawdz(self.pojazd.telemetria(), pozycja, self._dom, self._czas_misji(), self.limity)
        if alarm is None:
            return None
        log.warning("ALARM: %s", alarm.value)
        self._alarm = alarm
        self._wynik = Wynik.PRZERWANA
        self._powod = f"alarm bezpieczeństwa: {alarm.value}"
        return Stan.LADOWANIE_AWARYJNE if alarm is Alarm.UTRATA_GPS else Stan.POWROT

    def _przygotowanie(self) -> Stan:
        self._dom, _ = self.pojazd.pozycja()
        self.pojazd.uzbroj()
        return Stan.STARTOWANIE

    def _startowanie(self) -> Stan:
        self.pojazd.wystartuj(self.ustawienia.wysokosc_m)
        return Stan.SZUKANIE

    def _szukanie(self) -> Stan:
        while self._nastepny_punkt < len(self.trasa):
            stan_po_alarmie = self._sprawdz_bezpieczenstwo()
            if stan_po_alarmie is not None:
                return stan_po_alarmie
            punkt = self.trasa[self._nastepny_punkt]
            self._nastepny_punkt += 1
            self.pojazd.lec_do(punkt, self.ustawienia.wysokosc_m)
            pozycja, wysokosc = self.pojazd.pozycja()
            wykrycia = self.czujnik.wykryj(pozycja, wysokosc)
            if wykrycia:
                self._kandydat = max(wykrycia, key=lambda w: w.pewnosc)
                log.info("Możliwy cel (pewność %.2f), sprawdzam", self._kandydat.pewnosc)
                return Stan.POTWIERDZANIE
        self._wynik = Wynik.NIE_ZNALEZIONO
        return Stan.POWROT

    def _potwierdzanie(self) -> Stan:
        u = self.ustawienia
        kandydat = self._kandydat.polozenie
        self.pojazd.lec_do(kandydat, u.wysokosc_m)
        zgodne = []
        for _ in range(u.liczba_potwierdzen):
            pozycja, wysokosc = self.pojazd.pozycja()
            for w in self.czujnik.wykryj(pozycja, wysokosc):
                if odleglosc_m(w.polozenie, kandydat) <= u.promien_potwierdzenia_m:
                    zgodne.append(w.polozenie)
                    break
        if len(zgodne) >= u.wymagane_potwierdzenia:
            self._cel = srednia_pozycja(zgodne)
            log.info("Cel potwierdzony (%d z %d spojrzeń)", len(zgodne), u.liczba_potwierdzen)
            return Stan.ZRZUT
        log.info("Fałszywy alarm (%d z %d spojrzeń), szukam dalej", len(zgodne), u.liczba_potwierdzen)
        return Stan.SZUKANIE

    def _zrzut(self) -> Stan:
        self.pojazd.lec_do(self._cel, self.ustawienia.wysokosc_m, tolerancja_m=self.ustawienia.tolerancja_zrzutu_m)
        self._pozycja_zrzutu, _ = self.pojazd.pozycja()
        self.pojazd.zrzut()
        self._wynik = Wynik.SUKCES
        return Stan.POWROT

    def _powrot(self) -> Stan:
        self.pojazd.wroc_i_laduj()
        return Stan.KONIEC

    def _ladowanie_awaryjne(self) -> Stan:
        self.pojazd.laduj_awaryjnie()
        return Stan.KONIEC