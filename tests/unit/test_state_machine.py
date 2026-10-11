import pytest

from mission.atrapy import AtrapaDrona, CzujnikZeSkryptem, DOM_DOMYSLNY
from mission.geo import odleglosc_m, przesun
from mission.planner import Obszar, trasa_kosiarka, zageszcz
from mission.sensors.base import Detekcja
from mission.sensors.simulated_camera import Cel, WirtualnaKamera
from mission.state_machine import Misja, Stan, Ustawienia, Wynik
from mission.vehicle import BladPojazdu

DOM = DOM_DOMYSLNY
OBSZAR = Obszar(przesun(DOM, 10, 10), 60, 40)
TRASA = zageszcz(trasa_kosiarka(OBSZAR, 20, 60), 5)
CEL = Cel("czerwony_kwadrat", przesun(DOM, 30, 45))


def misja_z_kamera(cele, atrapa=None, **kamera):
    ustawienia = dict(p_wykrycia=1.0, szum_m=0.0, p_falszywy_alarm=0.0, seed=1)
    ustawienia.update(kamera)
    atrapa = atrapa or AtrapaDrona(DOM)
    return atrapa, Misja(atrapa, WirtualnaKamera(cele, **ustawienia), TRASA)


def detekcja(punkt, pewnosc=0.9):
    return Detekcja(punkt, pewnosc)


def test_normalny_scenariusz_konczy_sie_sukcesem_i_zrzutem_przy_celu():
    atrapa, misja = misja_z_kamera([CEL])
    wynik = misja.uruchom()
    assert wynik.wynik is Wynik.SUKCES
    assert atrapa.zrzucono
    assert odleglosc_m(atrapa.pozycja_zrzutu, CEL.polozenie) < 2.0
    assert wynik.historia == (
        Stan.PRZYGOTOWANIE, Stan.STARTOWANIE, Stan.SZUKANIE, Stan.POTWIERDZANIE, Stan.ZRZUT, Stan.POWROT, Stan.KONIEC,
    )


def test_po_zrzucie_dron_wraca_i_laduje_jako_ostatnia_komenda():
    atrapa, misja = misja_z_kamera([CEL])
    misja.uruchom()
    assert atrapa.nazwy_komend()[-2:] == ["zrzut", "wroc_i_laduj"]
    assert not atrapa.uzbrojony


def test_kolejnosc_komend_to_uzbroj_start_loty_zrzut_powrot():
    atrapa, misja = misja_z_kamera([CEL])
    misja.uruchom()
    nazwy = atrapa.nazwy_komend()
    assert nazwy[:2] == ["uzbroj", "wystartuj"]
    assert nazwy.index("zrzut") > nazwy.index("lec_do")
    assert nazwy.count("zrzut") == 1


def test_brak_celu_przeszukuje_cala_trase_nie_zrzuca_i_wraca():
    atrapa, misja = misja_z_kamera([])
    wynik = misja.uruchom()
    assert wynik.wynik is Wynik.NIE_ZNALEZIONO
    assert not atrapa.zrzucono
    assert atrapa.nazwy_komend().count("lec_do") == len(TRASA)
    assert wynik.historia[-2:] == (Stan.POWROT, Stan.KONIEC)


def test_cel_poza_obszarem_nie_jest_znaleziony():
    daleko = Cel("daleko", przesun(DOM, 200, 200))
    atrapa, misja = misja_z_kamera([daleko])
    assert misja.uruchom().wynik is Wynik.NIE_ZNALEZIONO
    assert not atrapa.zrzucono


def test_falszywy_alarm_jest_odrzucony_a_misja_szuka_dalej():
    falszywy = przesun(DOM, 15, 15)
    czujnik = CzujnikZeSkryptem([[detekcja(falszywy)], [], [], []])
    atrapa = AtrapaDrona(DOM)
    wynik = Misja(atrapa, czujnik, TRASA).uruchom()
    assert wynik.wynik is Wynik.NIE_ZNALEZIONO
    assert not atrapa.zrzucono
    assert Stan.POTWIERDZANIE in wynik.historia
    assert wynik.historia.count(Stan.SZUKANIE) == 2


def test_po_odrzuceniu_falszywego_alarmu_misja_potrafi_znalezc_prawdziwy_cel():
    falszywy = przesun(DOM, 15, 15)
    prawdziwy = przesun(DOM, 30, 45)
    czujnik = CzujnikZeSkryptem(
        [[detekcja(falszywy)], [], [], [], [detekcja(prawdziwy)], [detekcja(prawdziwy)], [detekcja(prawdziwy)], [detekcja(prawdziwy)]]
    )
    atrapa = AtrapaDrona(DOM)
    wynik = Misja(atrapa, czujnik, TRASA).uruchom()
    assert wynik.wynik is Wynik.SUKCES
    assert odleglosc_m(atrapa.pozycja_zrzutu, prawdziwy) < 0.1


def test_wystarcza_dwa_potwierdzenia_z_trzech():
    cel = przesun(DOM, 30, 45)
    czujnik = CzujnikZeSkryptem([[detekcja(cel)], [detekcja(cel)], [], [detekcja(cel)]])
    assert Misja(AtrapaDrona(DOM), czujnik, TRASA).uruchom().wynik is Wynik.SUKCES


def test_jedno_potwierdzenie_z_trzech_to_za_malo():
    cel = przesun(DOM, 30, 45)
    czujnik = CzujnikZeSkryptem([[detekcja(cel)], [detekcja(cel)], [], []])
    assert Misja(AtrapaDrona(DOM), czujnik, TRASA).uruchom().wynik is Wynik.NIE_ZNALEZIONO


def test_potwierdzenie_w_innym_miejscu_niz_kandydat_sie_nie_liczy():
    cel = przesun(DOM, 30, 45)
    gdzie_indziej = przesun(cel, 0, 15)
    czujnik = CzujnikZeSkryptem([[detekcja(cel)], [detekcja(gdzie_indziej)], [detekcja(gdzie_indziej)], [detekcja(gdzie_indziej)]])
    assert Misja(AtrapaDrona(DOM), czujnik, TRASA).uruchom().wynik is Wynik.NIE_ZNALEZIONO


def test_zrzut_nastepuje_w_usrednionej_pozycji_potwierdzen():
    cel = przesun(DOM, 30, 45)
    a, b = przesun(cel, 1, 0), przesun(cel, -1, 0)
    czujnik = CzujnikZeSkryptem([[detekcja(cel)], [detekcja(a)], [detekcja(b)], []])
    atrapa = AtrapaDrona(DOM)
    wynik = Misja(atrapa, czujnik, TRASA).uruchom()
    assert odleglosc_m(wynik.cel, cel) < 0.05


def test_z_kilku_wykryc_naraz_misja_sprawdza_najpewniejsze():
    slabe = przesun(DOM, 15, 15)
    mocne = przesun(DOM, 30, 45)
    czujnik = CzujnikZeSkryptem([[detekcja(slabe, 0.4), detekcja(mocne, 0.95)]])
    atrapa = AtrapaDrona(DOM)
    Misja(atrapa, czujnik, TRASA).uruchom()
    loty = [komenda for komenda in atrapa.komendy if komenda[0] == "lec_do"]
    assert odleglosc_m(loty[1][1], mocne) < 0.1


def test_czujnik_dostaje_pozycje_i_wysokosc_z_drona():
    czujnik = CzujnikZeSkryptem([])
    Misja(AtrapaDrona(DOM), czujnik, TRASA).uruchom()
    assert len(czujnik.wywolania) == len(TRASA)
    assert all(wysokosc == 20.0 for _, wysokosc in czujnik.wywolania)


def test_nieudane_uzbrojenie_konczy_misje_bez_startu_i_bez_proby_powrotu():
    atrapa = AtrapaDrona(DOM, awarie={"uzbroj": 0})
    wynik = Misja(atrapa, CzujnikZeSkryptem([]), TRASA).uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert "uzbroj" in wynik.powod_przerwania
    assert atrapa.nazwy_komend() == ["uzbroj"]
    assert wynik.historia == (Stan.PRZYGOTOWANIE, Stan.KONIEC)


def test_awaria_w_trakcie_lotu_konczy_sie_powrotem_do_bazy():
    atrapa = AtrapaDrona(DOM, awarie={"lec_do": 3})
    wynik = Misja(atrapa, CzujnikZeSkryptem([]), TRASA).uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert atrapa.nazwy_komend()[-1] == "wroc_i_laduj"
    assert wynik.historia[-2:] == (Stan.POWROT, Stan.KONIEC)
    assert not atrapa.zrzucono


def test_awaria_zrzutu_nie_daje_sukcesu_ale_dron_i_tak_wraca():
    atrapa = AtrapaDrona(DOM, awarie={"zrzut": 0})
    _, misja = misja_z_kamera([CEL], atrapa=atrapa)
    wynik = misja.uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert not atrapa.zrzucono
    assert atrapa.nazwy_komend()[-1] == "wroc_i_laduj"


def test_awaria_powrotu_jest_zgloszona_i_misja_sie_konczy():
    atrapa = AtrapaDrona(DOM, awarie={"wroc_i_laduj": 0})
    wynik = Misja(atrapa, CzujnikZeSkryptem([]), TRASA).uruchom()
    assert wynik.wynik is Wynik.PRZERWANA
    assert wynik.historia[-1] is Stan.KONIEC
    assert atrapa.nazwy_komend().count("wroc_i_laduj") == 1


def test_pusta_trasa_to_blad():
    with pytest.raises(ValueError):
        Misja(AtrapaDrona(DOM), CzujnikZeSkryptem([]), [])


def test_niespojne_ustawienia_potwierdzen_to_blad():
    with pytest.raises(ValueError):
        Misja(AtrapaDrona(DOM), CzujnikZeSkryptem([]), TRASA, Ustawienia(liczba_potwierdzen=2, wymagane_potwierdzenia=3))


def test_atrapa_zglasza_blad_pojazdu_zgodny_z_prawdziwym_pojazdem():
    atrapa = AtrapaDrona(DOM, awarie={"wystartuj": 0})
    with pytest.raises(BladPojazdu):
        atrapa.wystartuj(20)


@pytest.mark.parametrize("seed", range(10))
def test_cel_na_trasie_jest_znajdowany_niezaleznie_od_losowosci_przy_wysokim_p_wykrycia(seed):
    _, misja = misja_z_kamera([CEL], p_wykrycia=0.9, szum_m=1.0, p_falszywy_alarm=0.02, seed=seed)
    assert misja.uruchom().wynik is Wynik.SUKCES