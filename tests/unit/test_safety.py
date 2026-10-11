import pytest

from mission.geo import Punkt, przesun
from mission.safety import Alarm, Limity, Strefa, sprawdz
from mission.vehicle import Telemetria

DOM = Punkt(-35.363261, 149.165230)
ZDROWA = Telemetria(bateria_proc=100, napiecie_v=12.6, fix_gps=3, wiek_heartbeat_s=0.5)
LIMITY = Limity()


def alarm(telemetria=ZDROWA, pozycja=DOM, czas_s=10.0, limity=LIMITY):
    return sprawdz(telemetria, pozycja, DOM, czas_s, limity)


def test_zdrowy_dron_nie_wywoluje_alarmu():
    assert alarm() is None


@pytest.mark.parametrize("proc, oczekiwany", [(100, None), (31, None), (30, None), (29, Alarm.SLABA_BATERIA), (0, Alarm.SLABA_BATERIA)])
def test_prog_baterii_w_procentach(proc, oczekiwany):
    assert alarm(Telemetria(bateria_proc=proc, fix_gps=3)) is oczekiwany


@pytest.mark.parametrize("napiecie, oczekiwany", [(12.6, None), (10.8, None), (10.79, Alarm.SLABA_BATERIA), (9.0, Alarm.SLABA_BATERIA)])
def test_prog_napiecia_baterii(napiecie, oczekiwany):
    assert alarm(Telemetria(napiecie_v=napiecie, fix_gps=3)) is oczekiwany


@pytest.mark.parametrize("fix, oczekiwany", [(6, None), (4, None), (3, None), (2, Alarm.UTRATA_GPS), (1, Alarm.UTRATA_GPS), (0, Alarm.UTRATA_GPS)])
def test_gps_wymaga_co_najmniej_fixa_3d(fix, oczekiwany):
    assert alarm(Telemetria(fix_gps=fix)) is oczekiwany


@pytest.mark.parametrize("wiek, oczekiwany", [(0, None), (5.0, None), (5.1, Alarm.UTRATA_LACZNOSCI), (60, Alarm.UTRATA_LACZNOSCI)])
def test_utrata_lacznosci_gdy_heartbeat_jest_za_stary(wiek, oczekiwany):
    assert alarm(Telemetria(fix_gps=3, wiek_heartbeat_s=wiek)) is oczekiwany


@pytest.mark.parametrize("czas, oczekiwany", [(0, None), (600, None), (600.1, Alarm.PRZEKROCZONY_CZAS)])
def test_limit_czasu_misji(czas, oczekiwany):
    assert alarm(czas_s=czas) is oczekiwany


def test_wlasny_limit_czasu():
    assert alarm(czas_s=50, limity=Limity(czas_misji_s=40)) is Alarm.PRZEKROCZONY_CZAS


def test_brak_wiedzy_o_baterii_i_gps_nie_jest_alarmem():
    assert alarm(Telemetria()) is None


STREFA = Strefa(polnoc_min_m=-10, polnoc_max_m=50, wschod_min_m=-10, wschod_max_m=40)


@pytest.mark.parametrize(
    "polnoc, wschod, oczekiwany",
    [(0, 0, None), (49.9, 39.9, None), (-9.9, -9.9, None), (50.1, 0, Alarm.POZA_OBSZAREM), (0, 40.1, Alarm.POZA_OBSZAREM), (-10.1, 0, Alarm.POZA_OBSZAREM), (0, -10.1, Alarm.POZA_OBSZAREM)],
)
def test_strefa_dozwolona(polnoc, wschod, oczekiwany):
    assert alarm(pozycja=przesun(DOM, polnoc, wschod), limity=Limity(strefa=STREFA)) is oczekiwany


def test_bez_strefy_nie_ma_alarmu_poza_obszarem():
    assert alarm(pozycja=przesun(DOM, 5000, 5000)) is None


def test_niepoprawna_strefa_to_blad():
    with pytest.raises(ValueError):
        Strefa(10, 0, 0, 10)


def test_gps_jest_wazniejszy_niz_bateria_i_czas():
    t = Telemetria(bateria_proc=5, napiecie_v=9.0, fix_gps=0)
    assert alarm(t, czas_s=9999) is Alarm.UTRATA_GPS


def test_utrata_lacznosci_jest_wazniejsza_niz_gps():
    t = Telemetria(fix_gps=0, wiek_heartbeat_s=30)
    assert alarm(t) is Alarm.UTRATA_LACZNOSCI


def test_bateria_jest_wazniejsza_niz_strefa_i_czas():
    t = Telemetria(bateria_proc=5, fix_gps=3)
    assert alarm(t, pozycja=przesun(DOM, 5000, 0), czas_s=9999, limity=Limity(strefa=STREFA)) is Alarm.SLABA_BATERIA


def test_strefa_jest_wazniejsza_niz_czas():
    assert alarm(pozycja=przesun(DOM, 5000, 0), czas_s=9999, limity=Limity(strefa=STREFA)) is Alarm.POZA_OBSZAREM