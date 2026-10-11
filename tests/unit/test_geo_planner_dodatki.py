import pytest

from mission.geo import Punkt, odleglosc_m, przesun, srednia_pozycja
from mission.planner import zageszcz

START = Punkt(-35.363261, 149.165230)


def test_srednia_dwoch_punktow_to_ich_srodek():
    a = START
    b = przesun(START, 20, 40)
    srodek = srednia_pozycja([a, b])
    assert odleglosc_m(srodek, a) == pytest.approx(odleglosc_m(srodek, b), abs=0.01)
    assert odleglosc_m(a, b) == pytest.approx(2 * odleglosc_m(srodek, a), abs=0.01)


def test_srednia_jednego_punktu_to_ten_punkt():
    assert srednia_pozycja([START]) == START


def test_srednia_pustej_listy_to_blad():
    with pytest.raises(ValueError):
        srednia_pozycja([])


def test_zageszcz_zachowuje_poczatek_i_koniec():
    koniec = przesun(START, 40, 0)
    wynik = zageszcz([START, koniec], krok_m=5)
    assert wynik[0] == START
    assert wynik[-1] == koniec


def test_zageszcz_40_m_krokiem_5_m_daje_9_punktow():
    wynik = zageszcz([START, przesun(START, 40, 0)], krok_m=5)
    assert len(wynik) == 9


@pytest.mark.parametrize("krok_m", [1, 3, 5, 7.5, 50])
def test_zageszcz_zadne_dwa_sasiednie_punkty_nie_sa_dalej_niz_krok(krok_m):
    trasa = [START, przesun(START, 40, 0), przesun(START, 40, 18), przesun(START, 0, 18)]
    wynik = zageszcz(trasa, krok_m)
    for a, b in zip(wynik, wynik[1:]):
        assert odleglosc_m(a, b) <= krok_m + 1e-6


def test_zageszcz_nie_zmienia_dlugosci_trasy():
    from mission.planner import dlugosc_trasy_m

    trasa = [START, przesun(START, 40, 0), przesun(START, 40, 18)]
    assert dlugosc_trasy_m(zageszcz(trasa, 5)) == pytest.approx(dlugosc_trasy_m(trasa), rel=1e-6)


def test_zageszcz_puste_wejscie_daje_pusta_liste():
    assert zageszcz([], 5) == []


@pytest.mark.parametrize("krok_m", [0, -1])
def test_zageszcz_niedodatni_krok_to_blad(krok_m):
    with pytest.raises(ValueError):
        zageszcz([START], krok_m)