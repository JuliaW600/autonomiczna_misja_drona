import json

from mission.geo import Punkt
from mission.raport import podsumowanie, raport_jako_slownik, zapisz_raport
from mission.safety import Alarm
from mission.state_machine import Stan, Wynik, WynikMisji

SUKCES = WynikMisji(
    Wynik.SUKCES,
    (Stan.PRZYGOTOWANIE, Stan.POWROT, Stan.KONIEC),
    cel=Punkt(-35.3630, 149.1656),
    pozycja_zrzutu=Punkt(-35.36301, 149.16561),
    czas_misji_s=123.456,
)
PRZERWANA = WynikMisji(
    Wynik.PRZERWANA,
    (Stan.PRZYGOTOWANIE, Stan.LADOWANIE_AWARYJNE, Stan.KONIEC),
    powod_przerwania="alarm bezpieczeństwa: utrata GPS",
    alarm=Alarm.UTRATA_GPS,
    czas_misji_s=10,
)


def test_raport_sukcesu_zawiera_cel_i_zrzut_ale_nie_ma_alarmu():
    r = raport_jako_slownik(SUKCES, "normalny")
    assert r["scenariusz"] == "normalny"
    assert r["wynik"] == "SUKCES"
    assert r["alarm"] is None
    assert r["cel"] == {"lat": -35.363, "lon": 149.1656}
    assert r["pozycja_zrzutu"]["lat"] == -35.36301
    assert r["czas_misji_s"] == 123.5


def test_raport_przerwania_zawiera_alarm_i_powod():
    r = raport_jako_slownik(PRZERWANA)
    assert r["wynik"] == "PRZERWANA"
    assert r["alarm"] == "UTRATA_GPS"
    assert "GPS" in r["powod_przerwania"]
    assert r["cel"] is None and r["pozycja_zrzutu"] is None
    assert r["historia_stanow"] == ["przygotowanie", "lądowanie awaryjne", "koniec"]


def test_plik_json_jest_poprawny_i_zachowuje_polskie_znaki(tmp_path):
    sciezka = tmp_path / "podfolder" / "raport.json"
    zapisz_raport(PRZERWANA, sciezka, "utrata_gps")
    tekst = sciezka.read_text(encoding="utf-8")
    assert "lądowanie awaryjne" in tekst
    assert json.loads(tekst)["scenariusz"] == "utrata_gps"


def test_podsumowanie_dla_czlowieka_wymienia_alarm_i_stany():
    tekst = podsumowanie(PRZERWANA)
    assert "PRZERWANA" in tekst
    assert "UTRATA_GPS" in tekst
    assert "przygotowanie -> lądowanie awaryjne -> koniec" in tekst


def test_podsumowanie_sukcesu_nie_mowi_o_alarmie():
    assert "Alarm" not in podsumowanie(SUKCES)