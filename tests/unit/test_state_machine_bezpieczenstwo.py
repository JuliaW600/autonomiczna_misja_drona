import pytest

from mission.atrapy import AtrapaDrona, CzujnikZeSkryptem, DOM_DOMYSLNY
from mission.geo import przesun
from mission.planner import Obszar, trasa_kosiarka, zageszcz
from mission.safety import Alarm, Limity, Strefa
from mission.sensors.base import Detekcja
from mission.sensors.simulated_camera import Cel, WirtualnaKamera
from mission.state_machine import Misja, Stan, Wynik
from mission.vehicle import BladPojazdu
from mission.zegar import ZegarSztuczny

DOM = DOM_DOMYSLNY
TRASA = zageszcz(trasa_kosiarka(Obszar(przesun(DOM, 10, 10), 60, 40), 20, 60), 5)
CEL = Cel("cel", przesun(DOM, 30, 45))


def kamera(cele=(CEL,)):
    return WirtualnaKamera(list(cele), p_wykrycia=1.0, szum_m=0.0, p_falszywy_alarm=0.0, seed=1)


class AtrapaPsujacaSie(AtrapaDrona):
    """Atrapa, która po N-tym locie psuje wybrany element, tak jak scenariusz w pliku YAML."""

    def __init__(self, typ, po_lotach, **opcje):
        super().__init__(DOM, **opcje)
        self._typ, self._po_lotach, self._loty = typ, po_lotach, 0

    def lec_do(self, *argumenty, **opcje):
        super().lec_do(*argumenty, **opcje)
        self._loty += 1
        if self._loty == self._po_lotach:
            self.wstrzyknij_awarie(self._typ)


@pytest.mark.parametrize(
    "typ, alarm, stan_reakcji, ostatnia_komenda",
    [
        ("bateria", Alarm.SLABA_BATERIA, Stan.POWROT, "wroc_i_laduj"),
        ("lacznosc", Alarm.UTRATA_LACZNOSCI, Stan.POWROT, "wroc_i_laduj"),
        ("gps", Alarm.UTRATA_GPS, Stan.LADOWANIE_AWARYJNE, "laduj_awaryjnie"),
    ],
)
def test_alarm_przerywa_szukanie_i_wywoluje_wlasciwa_reakcje(typ, alarm, stan_reakcji, ostatnia_komenda):
    atrapa = AtrapaPsujacaSie(typ, po_lotach=5)
    wynik = Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert wynik.alarm is alarm
    assert wynik.historia[-2:] == (stan_reakcji, Stan.KONIEC)
    assert atrapa.nazwy_komend()[-1] == ostatnia_komenda
    assert not atrapa.zrzucono


def test_alarm_zatrzymuje_loty_zaraz_po_awarii():
    atrapa = AtrapaPsujacaSie("bateria", po_lotach=5)
    Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert atrapa.nazwy_komend().count("lec_do") == 5


def test_przy_utracie_gps_dron_nie_probuje_rtl():
    atrapa = AtrapaPsujacaSie("gps", po_lotach=5)
    Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert "wroc_i_laduj" not in atrapa.nazwy_komend()


def test_powod_przerwania_zawiera_nazwe_alarmu():
    atrapa = AtrapaPsujacaSie("bateria", po_lotach=5)
    wynik = Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert "alarm" in wynik.powod_przerwania
    assert Alarm.SLABA_BATERIA.value in wynik.powod_przerwania


def test_zdrowy_dron_konczy_misje_bez_alarmu_i_z_czasem_misji():
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(DOM, zegar=zegar, czas_komendy_s=1.0)
    wynik = Misja(atrapa, kamera(), TRASA, zegar=zegar).uruchom()
    assert wynik.wynik is Wynik.SUKCES
    assert wynik.alarm is None
    assert wynik.czas_misji_s == pytest.approx(len(atrapa.komendy))


def test_przekroczenie_czasu_misji_na_sztucznym_zegarze():
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(DOM, zegar=zegar, czas_komendy_s=2.0)
    wynik = Misja(atrapa, kamera(), TRASA, limity=Limity(czas_misji_s=30), zegar=zegar).uruchom()
    assert wynik.alarm is Alarm.PRZEKROCZONY_CZAS
    assert 30 < wynik.czas_misji_s < 40
    assert atrapa.nazwy_komend()[-1] == "wroc_i_laduj"


def test_dlugi_czas_nie_przeszkadza_gdy_limit_jest_wiekszy():
    zegar = ZegarSztuczny()
    atrapa = AtrapaDrona(DOM, zegar=zegar, czas_komendy_s=2.0)
    wynik = Misja(atrapa, kamera(), TRASA, limity=Limity(czas_misji_s=3600), zegar=zegar).uruchom()
    assert wynik.wynik is Wynik.SUKCES


def test_wyjscie_poza_strefe_przerywa_misje():
    strefa = Strefa(-30, 80, -30, 40)
    atrapa = AtrapaDrona(DOM)
    wynik = Misja(atrapa, kamera(), TRASA, limity=Limity(strefa=strefa), zegar=ZegarSztuczny()).uruchom()
    assert wynik.alarm is Alarm.POZA_OBSZAREM
    assert not atrapa.zrzucono


def test_alarm_w_trakcie_potwierdzania_tez_przerywa_misje():
    czujnik = CzujnikZeSkryptem([[Detekcja(przesun(DOM, 30, 45), 0.9)]])
    atrapa = AtrapaPsujacaSie("bateria", po_lotach=1)
    wynik = Misja(atrapa, czujnik, TRASA, zegar=ZegarSztuczny()).uruchom()
    assert wynik.alarm is Alarm.SLABA_BATERIA
    assert Stan.POTWIERDZANIE in wynik.historia
    assert Stan.ZRZUT not in wynik.historia
    assert not atrapa.zrzucono


def test_alarm_nie_psuje_dzialania_po_awarii_powrotu():
    atrapa = AtrapaPsujacaSie("bateria", po_lotach=5, awarie={"wroc_i_laduj": 0})
    wynik = Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert wynik.historia[-1] is Stan.KONIEC


def test_awaria_ladowania_awaryjnego_konczy_misje_bez_petli():
    atrapa = AtrapaPsujacaSie("gps", po_lotach=5, awarie={"laduj_awaryjnie": 0})
    wynik = Misja(atrapa, kamera(), TRASA, zegar=ZegarSztuczny()).uruchom()
    assert wynik.alarm is Alarm.UTRATA_GPS
    assert atrapa.nazwy_komend().count("laduj_awaryjnie") == 1
    assert wynik.historia[-1] is Stan.KONIEC


def test_atrapa_nie_zna_nieznanej_awarii():
    with pytest.raises(ValueError):
        AtrapaDrona(DOM).wstrzyknij_awarie("wiatr")


def test_atrapa_zglasza_blad_przy_ladowaniu_awaryjnym_gdy_tak_ustawiono():
    with pytest.raises(BladPojazdu):
        AtrapaDrona(DOM, awarie={"laduj_awaryjnie": 0}).laduj_awaryjnie()