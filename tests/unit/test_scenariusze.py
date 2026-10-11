from pathlib import Path

import pytest

from mission.atrapy import AtrapaDrona
from mission.scenariusz import (
    sprawdz_oczekiwania,
    uruchom_scenariusz,
    wczytaj_scenariusz,
    wczytaj_wszystkie,
)
from mission.zegar import ZegarSztuczny

FOLDER = Path(__file__).resolve().parents[2] / "config" / "scenarios"
SCENARIUSZE = wczytaj_wszystkie(FOLDER)


def test_sa_wszystkie_wymagane_scenariusze():
    nazwy = {s.nazwa for s in SCENARIUSZE}
    assert {
        "normalny",
        "brak_celu",
        "falszywe_alarmy",
        "slaba_bateria",
        "utrata_gps",
        "utrata_lacznosci",
        "przekroczony_czas",
        "poza_obszarem",
    } <= nazwy


def test_nazwy_scenariuszy_sa_unikalne():
    nazwy = [s.nazwa for s in SCENARIUSZE]
    assert len(nazwy) == len(set(nazwy))


@pytest.mark.parametrize("scenariusz", SCENARIUSZE, ids=lambda s: s.nazwa)
def test_scenariusz_daje_oczekiwany_wynik_na_atrapie(scenariusz):
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(zegar=zegar, czas_komendy_s=scenariusz.czas_komendy_s)
    wynik = uruchom_scenariusz(scenariusz, atrapa, zegar)
    assert sprawdz_oczekiwania(scenariusz, wynik, atrapa) == []


@pytest.mark.parametrize("scenariusz", SCENARIUSZE, ids=lambda s: s.nazwa)
def test_scenariusz_jest_powtarzalny(scenariusz):
    def przebieg():
        zegar = ZegarSztuczny()
        atrapa = AtrapaDrona(zegar=zegar, czas_komendy_s=scenariusz.czas_komendy_s)
        return uruchom_scenariusz(scenariusz, atrapa, zegar), atrapa.komendy

    assert przebieg() == przebieg()


def test_scenariusz_normalny_naprawde_zrzuca_ladunek():
    scenariusz = next(s for s in SCENARIUSZE if s.nazwa == "normalny")
    atrapa = AtrapaDrona()
    uruchom_scenariusz(scenariusz, atrapa, ZegarSztuczny())
    assert atrapa.zrzucono


@pytest.mark.parametrize("nazwa", ["slaba_bateria", "utrata_gps", "utrata_lacznosci", "przekroczony_czas", "poza_obszarem"])
def test_scenariusze_awaryjne_nigdy_nie_zrzucaja_ladunku(nazwa):
    scenariusz = next(s for s in SCENARIUSZE if s.nazwa == nazwa)
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(zegar=zegar, czas_komendy_s=scenariusz.czas_komendy_s)
    uruchom_scenariusz(scenariusz, atrapa, zegar)
    assert not atrapa.zrzucono


def test_limit_czasu_z_wiersza_polecen_nadpisuje_scenariusz():
    scenariusz = next(s for s in SCENARIUSZE if s.nazwa == "normalny")
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(zegar=zegar, czas_komendy_s=2.0)
    wynik = uruchom_scenariusz(scenariusz, atrapa, zegar, limit_czasu_s=20)
    assert wynik.alarm is not None and wynik.alarm.name == "PRZEKROCZONY_CZAS"


def test_sprawdz_oczekiwania_wykrywa_rozbieznosc():
    scenariusz = next(s for s in SCENARIUSZE if s.nazwa == "normalny")
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(zegar=zegar)
    wynik = uruchom_scenariusz(next(s for s in SCENARIUSZE if s.nazwa == "brak_celu"), atrapa, zegar)
    problemy = sprawdz_oczekiwania(scenariusz, wynik, atrapa)
    assert any("wynik" in p for p in problemy)


def napisz(tmp_path, tresc):
    plik = tmp_path / "s.yaml"
    plik.write_text(tresc, encoding="utf-8")
    return plik


def test_wczytywanie_scenariusza_z_minimalnego_pliku(tmp_path):
    plik = napisz(tmp_path, "nazwa: x\nopis: y\noczekiwane: {wynik: SUKCES, alarm: null, reakcja: powrot}\n")
    s = wczytaj_scenariusz(plik)
    assert s.nazwa == "x" and s.cele_m == () and s.awaria is None and s.p_falszywy_alarm == 0.02


@pytest.mark.parametrize(
    "tresc",
    [
        "",
        "nazwa: x\nopis: y\n",
        "nazwa: x\nopis: y\noczekiwane: {wynik: SUKCES}\n",
        "nazwa: x\nopis: y\noczekiwane: {wynik: SUKCES, alarm: null, reakcja: spacer}\n",
        "nazwa: x\nopis: y\noczekiwane: {wynik: SUKCES, alarm: null, reakcja: powrot}\ncele: [{polnoc_m: 1}]\n",
        "nazwa: x\nopis: y\noczekiwane: {wynik: SUKCES, alarm: null, reakcja: powrot}\nstrefa: {polnoc_m: [5, 1], wschod_m: [0, 1]}\n",
    ],
)
def test_zly_plik_scenariusza_to_czytelny_blad(tmp_path, tresc):
    with pytest.raises(ValueError):
        wczytaj_scenariusz(napisz(tmp_path, tresc))