import pytest

from mission.geo import Punkt, odleglosc_m, przesun, wspolrzedne_lokalne

CANBERRA = Punkt(-35.363261, 149.165230)


def test_odleglosc_tego_samego_punktu_to_zero():
    assert odleglosc_m(CANBERRA, CANBERRA) == 0


def test_przesuniecie_na_polnoc_o_100_m():
    p = przesun(CANBERRA, polnoc_m=100, wschod_m=0)
    assert p.lat > CANBERRA.lat
    assert p.lon == pytest.approx(CANBERRA.lon)
    assert odleglosc_m(CANBERRA, p) == pytest.approx(100, abs=0.01)


def test_przesuniecie_na_wschod_o_50_m():
    p = przesun(CANBERRA, polnoc_m=0, wschod_m=50)
    assert p.lon > CANBERRA.lon
    assert odleglosc_m(CANBERRA, p) == pytest.approx(50, abs=0.01)


def test_przesuniecie_po_przekatnej_to_pitagoras():
    p = przesun(CANBERRA, polnoc_m=30, wschod_m=40)
    assert odleglosc_m(CANBERRA, p) == pytest.approx(50, abs=0.01)


def test_wspolrzedne_lokalne_odwracaja_przesuniecie():
    p = przesun(CANBERRA, polnoc_m=12.5, wschod_m=-7.5)
    polnoc, wschod = wspolrzedne_lokalne(CANBERRA, p)
    assert polnoc == pytest.approx(12.5)
    assert wschod == pytest.approx(-7.5)


def test_odleglosc_jest_symetryczna():
    p = przesun(CANBERRA, 20, 35)
    assert odleglosc_m(CANBERRA, p) == pytest.approx(odleglosc_m(p, CANBERRA), rel=1e-3)

def test_jeden_stopien_szerokosci_to_okolo_111_km():
    # Sprawdza wartość "wprost" (niezależnie od stałej użytej w kodzie).
    p = Punkt(CANBERRA.lat + 1, CANBERRA.lon)
    assert odleglosc_m(CANBERRA, p) == pytest.approx(111_000, rel=0.01)