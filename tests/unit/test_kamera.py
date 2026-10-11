import math

import pytest

from mission.geo import Punkt, odleglosc_m, przesun
from mission.sensors.simulated_camera import Cel, WirtualnaKamera, wczytaj_cele

DOM = Punkt(-35.363261, 149.165230)
CEL = Cel("test", przesun(DOM, 30, 45))
# Kamera 60 stopni na 20 m widzi kwadrat o połowie boku 20 * tan(30 stopni), czyli ok. 11,5 m.


def kamera(**kwargs):
    ustawienia = dict(p_wykrycia=1.0, szum_m=0.0, p_falszywy_alarm=0.0, seed=1)
    ustawienia.update(kwargs)
    return WirtualnaKamera([CEL], **ustawienia)


def test_cel_pod_dronem_jest_wykryty_w_dokladnym_miejscu():
    wykrycia = kamera().wykryj(CEL.polozenie, 20)
    assert len(wykrycia) == 1
    assert odleglosc_m(wykrycia[0].polozenie, CEL.polozenie) < 0.01


def test_cel_na_skraju_pola_widzenia_jest_widoczny_a_tuz_za_skrajem_nie():
    polowa = 20 * math.tan(math.radians(30))
    assert kamera().wykryj(przesun(CEL.polozenie, polowa - 0.1, 0), 20)
    assert not kamera().wykryj(przesun(CEL.polozenie, polowa + 0.1, 0), 20)


def test_wyzej_kamera_widzi_wiecej():
    daleko = przesun(CEL.polozenie, 20, 0)
    assert not kamera().wykryj(daleko, 20)
    assert kamera().wykryj(daleko, 40)


def test_dron_na_ziemi_nic_nie_widzi():
    assert kamera().wykryj(CEL.polozenie, 0) == []


def test_p_wykrycia_zero_nigdy_nie_wykrywa():
    k = kamera(p_wykrycia=0.0)
    assert all(not k.wykryj(CEL.polozenie, 20) for _ in range(200))


def test_p_wykrycia_polowa_wykrywa_mniej_wiecej_polowe_razy():
    k = kamera(p_wykrycia=0.5, seed=7)
    trafienia = sum(bool(k.wykryj(CEL.polozenie, 20)) for _ in range(2000))
    assert 900 < trafienia < 1100


def test_szum_przesuwa_pozycje_ale_niezbyt_daleko():
    k = kamera(szum_m=1.0, seed=3)
    bledy = [odleglosc_m(k.wykryj(CEL.polozenie, 20)[0].polozenie, CEL.polozenie) for _ in range(500)]
    assert max(bledy) > 0.1
    assert sum(bledy) / len(bledy) < 2.0


def test_ten_sam_seed_daje_te_same_wyniki():
    a = kamera(szum_m=1.0, p_wykrycia=0.5, p_falszywy_alarm=0.3, seed=11)
    b = kamera(szum_m=1.0, p_wykrycia=0.5, p_falszywy_alarm=0.3, seed=11)
    assert [a.wykryj(CEL.polozenie, 20) for _ in range(50)] == [b.wykryj(CEL.polozenie, 20) for _ in range(50)]


def test_inny_seed_daje_inne_wyniki():
    a = kamera(szum_m=1.0, seed=1)
    b = kamera(szum_m=1.0, seed=2)
    assert a.wykryj(CEL.polozenie, 20) != b.wykryj(CEL.polozenie, 20)


def test_falszywy_alarm_pojawia_sie_nawet_bez_celow_i_lezy_w_polu_widzenia():
    k = WirtualnaKamera([], p_falszywy_alarm=1.0, seed=5)
    wykrycia = k.wykryj(DOM, 20)
    assert len(wykrycia) == 1
    assert odleglosc_m(wykrycia[0].polozenie, DOM) <= 20 * math.tan(math.radians(30)) * math.sqrt(2) + 0.01
    assert wykrycia[0].pewnosc < 0.7


def test_prawdziwe_wykrycie_ma_wysoka_pewnosc():
    assert kamera().wykryj(CEL.polozenie, 20)[0].pewnosc >= 0.7


@pytest.mark.parametrize(
    "ustawienia",
    [
        dict(fov_stopnie=0),
        dict(fov_stopnie=180),
        dict(p_wykrycia=1.1),
        dict(p_wykrycia=-0.1),
        dict(p_falszywy_alarm=2),
        dict(szum_m=-1),
    ],
)
def test_niepoprawne_ustawienia_kamery_to_blad(ustawienia):
    with pytest.raises(ValueError):
        WirtualnaKamera([CEL], **ustawienia)


def test_wczytaj_cele_przelicza_metry_od_startu_na_wspolrzedne(tmp_path):
    plik = tmp_path / "cele.yaml"
    plik.write_text("cele:\n  - nazwa: a\n    polnoc_m: 30\n    wschod_m: 45\n  - polnoc_m: 0\n    wschod_m: 10\n")
    cele = wczytaj_cele(plik, DOM)
    assert [c.nazwa for c in cele] == ["a", "cel_2"]
    assert odleglosc_m(cele[0].polozenie, DOM) == pytest.approx(math.hypot(30, 45), abs=0.01)


def test_wczytaj_cele_pusta_lista_jest_dozwolona(tmp_path):
    plik = tmp_path / "cele.yaml"
    plik.write_text("cele: []\n")
    assert wczytaj_cele(plik, DOM) == []


@pytest.mark.parametrize(
    "tresc",
    ["inne: 1\n", "cele:\n  - nazwa: a\n    polnoc_m: 30\n", "cele:\n  - polnoc_m: abc\n    wschod_m: 1\n"],
)
def test_wczytaj_cele_zly_plik_to_czytelny_blad(tmp_path, tresc):
    plik = tmp_path / "cele.yaml"
    plik.write_text(tresc)
    with pytest.raises(ValueError):
        wczytaj_cele(plik, DOM)