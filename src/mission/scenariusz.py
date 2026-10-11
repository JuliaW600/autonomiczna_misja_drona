"""Scenariusze testowe zapisane w plikach YAML: co się dzieje, co psujemy i czego oczekujemy.

Ten sam plik można uruchomić na atrapie (testy automatyczne) i w symulatorze (pokaz w Mission Plannerze).
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mission.geo import Punkt, przesun
from mission.planner import Obszar, trasa_kosiarka, zageszcz
from mission.safety import Limity, Strefa
from mission.sensors.simulated_camera import Cel, WirtualnaKamera
from mission.state_machine import Misja, Ustawienia, WynikMisji
from mission.vehicle import Pojazd
from mission.zegar import Zegar

WYSOKOSC_M = 20.0
FOV_STOPNIE = 60.0
KROK_M = 5.0
MARGINES_STREFY_M = 30.0
REAKCJE = {"powrot": "powrót", "ladowanie_awaryjne": "lądowanie awaryjne"}


@dataclass(frozen=True)
class Awaria:
    typ: str
    po_punktach: int


@dataclass(frozen=True)
class Scenariusz:
    nazwa: str
    opis: str
    cele_m: tuple[tuple[float, float], ...]
    oczekiwane: dict
    awaria: Awaria | None = None
    p_wykrycia: float = 0.9
    p_falszywy_alarm: float = 0.02
    seed: int = 42
    czas_misji_s: float | None = None
    strefa: Strefa | None = None
    czas_komendy_s: float = 0.0
    tylko_atrapa: bool = False
    pola_dodatkowe: dict = field(default_factory=dict)


class PojazdZAwaria:
    """Obudowa na dowolnego drona: po N-tym locie psuje baterię, GPS albo łączność.

    Wszystko poza `lec_do` przekazuje bez zmian do prawdziwego (lub atrapowego) drona.
    """

    def __init__(self, pojazd: Pojazd, awaria: Awaria | None):
        self._pojazd = pojazd
        self._awaria = awaria
        self._loty = 0

    def lec_do(self, *argumenty, **opcje):
        self._pojazd.lec_do(*argumenty, **opcje)
        self._loty += 1
        if self._awaria is not None and self._loty == self._awaria.po_punktach:
            self._pojazd.wstrzyknij_awarie(self._awaria.typ)

    def __getattr__(self, nazwa):
        return getattr(self._pojazd, nazwa)


def wczytaj_scenariusz(sciezka: Path) -> Scenariusz:
    sciezka = Path(sciezka)
    dane = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
    if not isinstance(dane, dict):
        raise ValueError(f"{sciezka}: plik pusty albo niepoprawny")
    for klucz in ("nazwa", "opis", "oczekiwane"):
        if klucz not in dane:
            raise ValueError(f"{sciezka}: brak klucza '{klucz}'")
    oczekiwane = dane["oczekiwane"]
    for klucz in ("wynik", "alarm", "reakcja"):
        if klucz not in oczekiwane:
            raise ValueError(f"{sciezka}: w 'oczekiwane' brak klucza '{klucz}'")
    if oczekiwane["reakcja"] not in REAKCJE:
        raise ValueError(f"{sciezka}: 'reakcja' musi być jedną z: {', '.join(REAKCJE)}")
    try:
        cele = tuple((float(c["polnoc_m"]), float(c["wschod_m"])) for c in dane.get("cele") or [])
        awaria = None
        if dane.get("awaria"):
            awaria = Awaria(str(dane["awaria"]["typ"]), int(dane["awaria"]["po_punktach"]))
        strefa = None
        if dane.get("strefa"):
            polnoc, wschod = dane["strefa"]["polnoc_m"], dane["strefa"]["wschod_m"]
            strefa = Strefa(float(polnoc[0]), float(polnoc[1]), float(wschod[0]), float(wschod[1]))
        kamera = dane.get("kamera") or {}
        return Scenariusz(
            nazwa=str(dane["nazwa"]),
            opis=str(dane["opis"]),
            cele_m=cele,
            oczekiwane=oczekiwane,
            awaria=awaria,
            p_wykrycia=float(kamera.get("p_wykrycia", 0.9)),
            p_falszywy_alarm=float(kamera.get("p_falszywy_alarm", 0.02)),
            seed=int(kamera.get("seed", 42)),
            czas_misji_s=None if dane.get("czas_misji_s") is None else float(dane["czas_misji_s"]),
            strefa=strefa,
            czas_komendy_s=float(dane.get("czas_komendy_s", 0.0)),
            tylko_atrapa=bool(dane.get("tylko_atrapa", False)),
        )
    except (KeyError, TypeError, ValueError, IndexError) as blad:
        raise ValueError(f"{sciezka}: niepoprawna zawartość ({blad})") from blad


def wczytaj_wszystkie(folder: Path) -> list[Scenariusz]:
    return [wczytaj_scenariusz(p) for p in sorted(Path(folder).glob("*.yaml"))]


def uruchom_scenariusz(
    scenariusz: Scenariusz,
    pojazd: Pojazd,
    zegar: Zegar | None = None,
    limit_czasu_s: float | None = None,
) -> WynikMisji:
    """Buduje misję według scenariusza i ją wykonuje. `pojazd` musi być już połączony.

    `limit_czasu_s` (jeśli podany) nadpisuje limit czasu misji ze scenariusza.
    """
    dom, _ = pojazd.pozycja()
    cele = [Cel(f"cel_{i}", przesun(dom, n, e)) for i, (n, e) in enumerate(scenariusz.cele_m, start=1)]
    kamera = WirtualnaKamera(
        cele,
        fov_stopnie=FOV_STOPNIE,
        p_wykrycia=scenariusz.p_wykrycia,
        p_falszywy_alarm=scenariusz.p_falszywy_alarm,
        seed=scenariusz.seed,
    )
    obszar = Obszar(przesun(dom, 10, 10), 60.0, 40.0)
    trasa = zageszcz(trasa_kosiarka(obszar, WYSOKOSC_M, FOV_STOPNIE), KROK_M)
    strefa = scenariusz.strefa or Strefa(
        -MARGINES_STREFY_M,
        10 + obszar.glebokosc_m + MARGINES_STREFY_M,
        -MARGINES_STREFY_M,
        10 + obszar.szerokosc_m + MARGINES_STREFY_M,
    )
    limity = Limity(strefa=strefa)
    czas = limit_czasu_s if limit_czasu_s is not None else scenariusz.czas_misji_s
    if czas is not None:
        limity = Limity(czas_misji_s=czas, strefa=strefa)
    misja = Misja(
        PojazdZAwaria(pojazd, scenariusz.awaria),
        kamera,
        trasa,
        Ustawienia(wysokosc_m=WYSOKOSC_M),
        limity,
        zegar,
    )
    return misja.uruchom()


def sprawdz_oczekiwania(scenariusz: Scenariusz, wynik: WynikMisji, pojazd: Pojazd | None = None) -> list[str]:
    """Zwraca listę rozbieżności między oczekiwanym a faktycznym wynikiem (pusta = scenariusz zaliczony)."""
    oczekiwane = scenariusz.oczekiwane
    problemy = []
    if wynik.wynik.name != oczekiwane["wynik"]:
        problemy.append(f"wynik: oczekiwano {oczekiwane['wynik']}, jest {wynik.wynik.name}")
    faktyczny_alarm = None if wynik.alarm is None else wynik.alarm.name
    if faktyczny_alarm != oczekiwane["alarm"]:
        problemy.append(f"alarm: oczekiwano {oczekiwane['alarm']}, jest {faktyczny_alarm}")
    oczekiwany_stan = REAKCJE[oczekiwane["reakcja"]]
    stan_przed_koncem = wynik.historia[-2].value if len(wynik.historia) >= 2 else None
    if stan_przed_koncem != oczekiwany_stan:
        problemy.append(f"reakcja: oczekiwano '{oczekiwany_stan}', ostatni stan przed końcem to '{stan_przed_koncem}'")
    ostatnia = oczekiwane.get("ostatnia_komenda")
    if ostatnia and pojazd is not None and hasattr(pojazd, "nazwy_komend"):
        if pojazd.nazwy_komend()[-1] != ostatnia:
            problemy.append(f"ostatnia komenda: oczekiwano {ostatnia}, jest {pojazd.nazwy_komend()[-1]}")
    return problemy