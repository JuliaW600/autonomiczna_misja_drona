import math

import pytest

from mission.geo import Punkt, wspolrzedne_lokalne
from mission.planner import (
    Obszar,
    dlugosc_trasy_m,
    rozstaw_pasow_m,
    szerokosc_pola_widzenia_m,
    trasa_kosiarka,
    zapisz_waypoints,
)

START = Punkt(-35.363261, 149.165230)
OBSZAR = Obszar(START, szerokosc_m=60, glebokosc_m=40)


def test_szerokosc_pola_widzenia_dla_20_m_i_60_stopni():
    assert szerokosc_pola_widzenia_m(20, 60) == pytest.approx(2 * 20 * math.tan(math.radians(30)))
    assert szerokosc_pola_widzenia_m(20, 60) == pytest.approx(23.094, abs=0.001)


def test_rozstaw_uwzglednia_zakladke():
    pelna = szerokosc_pola_widzenia_m(20, 60)
    assert rozstaw_pasow_m(20, 60, zakladka=0.2) == pytest.approx(pelna * 0.8)


@pytest.mark.parametrize(
    "wysokosc, fov, zakladka",
    [(0, 60, 0.2), (-5, 60, 0.2), (20, 0, 0.2), (20, 180, 0.2), (20, 60, 1.0), (20, 60, -0.1)],
)
def test_bledne_parametry_zglaszaja_blad(wysokosc, fov, zakladka):
    with pytest.raises(ValueError):
        rozstaw_pasow_m(wysokosc, fov, zakladka)


def test_bledny_obszar_zglasza_blad():
    with pytest.raises(ValueError):
        trasa_kosiarka(Obszar(START, 0, 40), 20, 60)


def test_liczba_punktow_to_dwa_na_pas():
    trasa = trasa_kosiarka(OBSZAR, wysokosc_m=20, fov_stopnie=60, zakladka=0.2)
    # rozstaw 18,5 m, obszar 60 m szeroki -> 4 pasy -> 8 punktów
    assert len(trasa) == 8


def test_wszystkie_punkty_leza_w_obszarze():
    trasa = trasa_kosiarka(OBSZAR, 20, 60)
    for p in trasa:
        polnoc, wschod = wspolrzedne_lokalne(START, p)
        assert -0.01 <= polnoc <= OBSZAR.glebokosc_m + 0.01
        assert 0 <= wschod <= OBSZAR.szerokosc_m


def test_pasy_leca_na_zmiane_na_polnoc_i_na_poludnie():
    trasa = trasa_kosiarka(OBSZAR, 20, 60)
    pasy = [(trasa[i], trasa[i + 1]) for i in range(0, len(trasa), 2)]
    kierunki = [wspolrzedne_lokalne(START, koniec)[0] > wspolrzedne_lokalne(START, poczatek)[0] for poczatek, koniec in pasy]
    assert kierunki == [True, False, True, False]


def test_odstep_miedzy_pasami_nie_przekracza_rozstawu():
    trasa = trasa_kosiarka(OBSZAR, 20, 60, zakladka=0.2)
    wschody = sorted({round(wspolrzedne_lokalne(START, p)[1], 3) for p in trasa})
    maks = rozstaw_pasow_m(20, 60, 0.2)
    assert all(b - a <= maks + 1e-6 for a, b in zip(wschody, wschody[1:]))


def test_trasa_jest_powtarzalna():
    assert trasa_kosiarka(OBSZAR, 20, 60) == trasa_kosiarka(OBSZAR, 20, 60)


def test_waski_obszar_daje_jeden_pas():
    trasa = trasa_kosiarka(Obszar(START, 5, 40), 20, 60)
    assert len(trasa) == 2


def test_dlugosc_trasy_jest_dodatnia_i_rozsadna():
    trasa = trasa_kosiarka(OBSZAR, 20, 60)
    # 4 pasy po 40 m + 3 przejścia po ok. 15 m
    assert dlugosc_trasy_m(trasa) == pytest.approx(4 * 40 + 3 * 15, abs=1)


def test_zapis_pliku_waypoints(tmp_path):
    trasa = trasa_kosiarka(OBSZAR, 20, 60)
    plik = tmp_path / "wyjscie" / "trasa.waypoints"
    zapisz_waypoints(trasa, START, 20, plik)

    linie = plik.read_text(encoding="utf-8").splitlines()
    assert linie[0] == "QGC WPL 110"
    assert len(linie) == 1 + 1 + 1 + len(trasa) + 1  # nagłówek, dom, start, punkty, RTL
    komendy = [int(l.split("\t")[3]) for l in linie[1:]]
    assert komendy[0] == 16 and komendy[1] == 22 and komendy[-1] == 20
    assert all(len(l.split("\t")) == 12 for l in linie[1:])