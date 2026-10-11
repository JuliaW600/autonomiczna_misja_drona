import pytest

from mission.zegar import ZegarSystemowy, ZegarSztuczny


def test_sztuczny_zegar_stoi_dopoki_nie_kazemy_mu_plynac():
    zegar = ZegarSztuczny()
    assert zegar.teraz() == 0.0
    assert zegar.teraz() == 0.0


def test_sztuczny_zegar_dodaje_czas_oczekiwania():
    zegar = ZegarSztuczny(start=100.0)
    zegar.czekaj(2.5)
    zegar.czekaj(0.5)
    assert zegar.teraz() == pytest.approx(103.0)


def test_sztuczny_zegar_nie_cofa_sie():
    with pytest.raises(ValueError):
        ZegarSztuczny().czekaj(-1)


def test_systemowy_zegar_nie_cofa_sie():
    zegar = ZegarSystemowy()
    a = zegar.teraz()
    b = zegar.teraz()
    assert b >= a