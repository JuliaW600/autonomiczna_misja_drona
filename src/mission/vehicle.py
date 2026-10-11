"""Sterowanie dronem przez MAVLink.

`Pojazd` to interfejs (lista tego, co dron potrafi). Dzięki niemu logika misji
nie musi wiedzieć, czy rozmawia z prawdziwym symulatorem, czy z atrapą w testach.
`MavlinkPojazd` to implementacja rozmawiająca z autopilotem przez pymavlink.
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pymavlink import mavutil

from mission.geo import Punkt, odleglosc_m

log = logging.getLogger(__name__)

POLECENIE_ARM = 400
POLECENIE_TAKEOFF = 22
POLECENIE_SERWO = 183
POLECENIE_RESET_BATERII = 42651
FLAGA_UZBROJONY = 128
# Maska "interesuje mnie tylko pozycja": ignorujemy prędkość, przyspieszenie i kurs.
MASKA_TYLKO_POZYCJA = 0b0000111111111000

# Zrzut ładunku: serwo na wyjściu nr 9, położenie "otwarte" = 1900 µs.
KANAL_ZRZUTU = 9
PWM_ZRZUTU = 1900


# Awarie, które potrafimy wywołać w symulatorze ArduPilota (parametry SITL). Nie działają na prawdziwym dronie.
AWARIE_SITL = {
    "bateria": ("SIM_BATT_VOLTAGE", 10.0),
    "gps": ("SIM_GPS1_ENABLE", 0.0),
}
USTAWIENIA_SITL_NORMALNE = {"SIM_BATT_VOLTAGE": 12.6, "SIM_GPS1_ENABLE": 1.0}
NAPIECIE_NIEZNANE_MV = 65535


class BladPojazdu(Exception):
    """Nie udało się wykonać operacji na dronie (np. przekroczono limit czasu)."""


@dataclass(frozen=True)
class Telemetria:
    """Stan zdrowia drona. `None` oznacza "nie wiem" (np. jeszcze nie przyszła wiadomość)."""

    bateria_proc: int | None = None
    napiecie_v: float | None = None
    fix_gps: int | None = None
    wiek_heartbeat_s: float = 0.0


class Pojazd(ABC):
    @abstractmethod
    def polacz(self, limit_s: float = 30) -> None: ...

    @abstractmethod
    def pozycja(self) -> tuple[Punkt, float]:
        """Aktualna pozycja i wysokość względna (m) nad miejscem startu."""

    @abstractmethod
    def uzbroj(self, limit_s: float = 120) -> None: ...

    @abstractmethod
    def wystartuj(self, wysokosc_m: float, limit_s: float = 60) -> None: ...

    @abstractmethod
    def lec_do(self, cel: Punkt, wysokosc_m: float, tolerancja_m: float = 3.0, limit_s: float = 120) -> None:
        """Leci do punktu i czeka, aż dron będzie w odległości `tolerancja_m`."""

    @abstractmethod
    def telemetria(self) -> Telemetria:
        """Bateria, GPS i świeżość łączności; używa tego monitor bezpieczeństwa."""

    @abstractmethod
    def zrzut(self, limit_s: float = 10) -> None:
        """Zwalnia ładunek i czeka na potwierdzenie, że mechanizm się poruszył."""

    @abstractmethod
    def laduj_awaryjnie(self, limit_s: float = 180) -> None:
        """Ląduje w miejscu (tryb LAND), bez wracania do bazy. Gdy GPS nie działa, RTL nie jest możliwy."""

    @abstractmethod
    def wroc_i_laduj(self, limit_s: float = 180) -> None:
        """Wraca do punktu startu (RTL), ląduje i czeka na rozbrojenie."""


class MavlinkPojazd(Pojazd):
    def __init__(self, adres: str = "tcp:127.0.0.1:5762"):
        self.adres = adres
        self._conn = None
        self._cel = None

    def polacz(self, limit_s: float = 30) -> None:
        log.info("Łączenie z %s", self.adres)
        self._conn = mavutil.mavlink_connection(self.adres)
        if self._conn.wait_heartbeat(timeout=limit_s) is None:
            raise BladPojazdu(f"Brak heartbeat z {self.adres} w ciągu {limit_s} s")
        self._cel = (self._conn.target_system, self._conn.target_component)
        self._conn.mav.request_data_stream_send(*self._cel, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
        log.info("Połączono z systemem %s", self._conn.target_system)

    def pozycja(self) -> tuple[Punkt, float]:
        # Najpierw wyrzucamy zalegające, stare wiadomości, potem czekamy na świeżą.
        while self._conn.recv_match(blocking=False) is not None:
            pass
        msg = self._conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=5)
        if msg is None:
            raise BladPojazdu("Brak telemetrii pozycji (GLOBAL_POSITION_INT)")
        return Punkt(msg.lat / 1e7, msg.lon / 1e7), msg.relative_alt / 1000.0

    def _czy_uzbrojony(self, timeout: float = 1.0) -> bool | None:
        hb = self._conn.recv_match(type="HEARTBEAT", blocking=True, timeout=timeout)
        return None if hb is None else bool(hb.base_mode & FLAGA_UZBROJONY)

    def uzbroj(self, limit_s: float = 120) -> None:
        self._conn.set_mode("GUIDED")
        start = time.time()
        while time.time() - start < limit_s:
            self._conn.mav.command_long_send(*self._cel, POLECENIE_ARM, 0, 1, 0, 0, 0, 0, 0, 0)
            koniec = time.time() + 3
            while time.time() < koniec:
                msg = self._conn.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1)
                if msg is None:
                    continue
                if msg.get_type() == "STATUSTEXT" and "Arm" in msg.text:
                    log.info("Autopilot: %s", msg.text)
                if msg.get_type() == "HEARTBEAT" and msg.base_mode & FLAGA_UZBROJONY:
                    log.info("Uzbrojony")
                    return
        raise BladPojazdu(f"Nie udało się uzbroić w ciągu {limit_s} s")

    def wystartuj(self, wysokosc_m: float, limit_s: float = 60) -> None:
        self._conn.mav.command_long_send(*self._cel, POLECENIE_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, wysokosc_m)
        log.info("Start na %.0f m", wysokosc_m)
        start = time.time()
        while time.time() - start < limit_s:
            _, wysokosc = self.pozycja()
            if wysokosc >= wysokosc_m * 0.9:
                return
        raise BladPojazdu(f"Nie osiągnięto wysokości {wysokosc_m} m w ciągu {limit_s} s")

    def lec_do(self, cel: Punkt, wysokosc_m: float, tolerancja_m: float = 3.0, limit_s: float = 120) -> None:
        self._conn.mav.set_position_target_global_int_send(
            0,
            *self._cel,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            MASKA_TYLKO_POZYCJA,
            int(cel.lat * 1e7),
            int(cel.lon * 1e7),
            wysokosc_m,
            0, 0, 0, 0, 0, 0, 0, 0,
        )
        start = time.time()
        while time.time() - start < limit_s:
            punkt, _ = self.pozycja()
            if odleglosc_m(punkt, cel) <= tolerancja_m:
                return
        raise BladPojazdu(f"Nie dotarto do punktu {cel} w ciągu {limit_s} s")

    def telemetria(self) -> Telemetria:
        while self._conn.recv_match(blocking=False) is not None:
            pass
        status = self._conn.messages.get("SYS_STATUS")
        gps = self._conn.messages.get("GPS_RAW_INT")
        bateria = None
        napiecie = None
        if status is not None:
            if status.battery_remaining >= 0:
                bateria = status.battery_remaining
            if status.voltage_battery != NAPIECIE_NIEZNANE_MV:
                napiecie = status.voltage_battery / 1000.0
        return Telemetria(
            bateria_proc=bateria,
            napiecie_v=napiecie,
            fix_gps=None if gps is None else gps.fix_type,
            wiek_heartbeat_s=self._conn.time_since("HEARTBEAT"),
        )

    def wstrzyknij_awarie(self, typ: str) -> None:
        """Tylko symulator: psuje baterię lub GPS, żeby sprawdzić reakcję misji."""
        if typ not in AWARIE_SITL:
            raise ValueError(f"W symulatorze da się wywołać tylko: {', '.join(AWARIE_SITL)} (podano '{typ}')")
        nazwa, wartosc = AWARIE_SITL[typ]
        log.warning("Wstrzykuję awarię '%s' (%s = %s)", typ, nazwa, wartosc)
        self._ustaw_parametr(nazwa, wartosc)

    def przywroc_awarie(self, limit_s: float = 10) -> None:
        """Tylko symulator: wraca do zdrowego GPS i baterii z napięciem 12,6 V i 100%.

        Ustawienia zostają w symulatorze między lotami, a każdy lot zużywa baterię (ok. 30% na misję),
        więc bez tego trzecia misja z rzędu zgłosiłaby alarm słabej baterii.
        """
        for nazwa, wartosc in USTAWIENIA_SITL_NORMALNE.items():
            self._ustaw_parametr(nazwa, wartosc)
        self._conn.mav.command_long_send(*self._cel, POLECENIE_RESET_BATERII, 0, 255, 100, 0, 0, 0, 0, 0)
        start = time.time()
        while time.time() - start < limit_s:
            bateria = self.telemetria().bateria_proc
            if bateria is not None and bateria >= 99:
                return
            time.sleep(0.5)
        raise BladPojazdu("Symulator nie przywrócił baterii do 100%")

    def _ustaw_parametr(self, nazwa: str, wartosc: float, limit_s: float = 5) -> None:
        self._conn.mav.param_set_send(*self._cel, nazwa.encode(), wartosc, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        start = time.time()
        while time.time() - start < limit_s:
            msg = self._conn.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
            if msg is not None and msg.param_id == nazwa and abs(msg.param_value - wartosc) < 1e-3:
                return
        raise BladPojazdu(f"Autopilot nie potwierdził ustawienia {nazwa} = {wartosc}")

    def zrzut(self, limit_s: float = 10) -> None:
        # Funkcja 0 = "zwykłe serwo sterowane ręcznie komendą", inaczej autopilot nadpisze nasz sygnał.
        self._ustaw_parametr(f"SERVO{KANAL_ZRZUTU}_FUNCTION", 0)
        self._conn.mav.command_long_send(*self._cel, POLECENIE_SERWO, 0, KANAL_ZRZUTU, PWM_ZRZUTU, 0, 0, 0, 0, 0)
        start = time.time()
        while time.time() - start < limit_s:
            msg = self._conn.recv_match(type="SERVO_OUTPUT_RAW", blocking=True, timeout=1)
            if msg is not None and getattr(msg, f"servo{KANAL_ZRZUTU}_raw", 0) == PWM_ZRZUTU:
                log.info("Zrzut: serwo %d ustawione na %d µs (potwierdzone)", KANAL_ZRZUTU, PWM_ZRZUTU)
                return
        raise BladPojazdu(f"Brak potwierdzenia zrzutu (serwo {KANAL_ZRZUTU}) w ciągu {limit_s} s")

    def _czekaj_na_rozbrojenie(self, limit_s: float) -> None:
        start = time.time()
        while time.time() - start < limit_s:
            if self._czy_uzbrojony(timeout=2) is False:
                log.info("Wylądowano i rozbrojono")
                return
        raise BladPojazdu(f"Nie wylądowano w ciągu {limit_s} s")

    def wroc_i_laduj(self, limit_s: float = 180) -> None:
        self._conn.set_mode("RTL")
        log.info("Powrót do bazy (RTL)")
        self._czekaj_na_rozbrojenie(limit_s)

    def laduj_awaryjnie(self, limit_s: float = 180) -> None:
        self._conn.set_mode("LAND")
        log.info("Lądowanie awaryjne w miejscu (LAND)")
        self._czekaj_na_rozbrojenie(limit_s)