"""Sterowanie dronem przez MAVLink.

`Pojazd` to interfejs (lista tego, co dron potrafi). Dzięki niemu logika misji
nie musi wiedzieć, czy rozmawia z prawdziwym symulatorem, czy z atrapą w testach.
`MavlinkPojazd` to implementacja rozmawiająca z autopilotem przez pymavlink.
"""
import logging
import time
from abc import ABC, abstractmethod

from pymavlink import mavutil

from mission.geo import Punkt, odleglosc_m

log = logging.getLogger(__name__)

POLECENIE_ARM = 400
POLECENIE_TAKEOFF = 22
FLAGA_UZBROJONY = 128
# Maska "interesuje mnie tylko pozycja": ignorujemy prędkość, przyspieszenie i kurs.
MASKA_TYLKO_POZYCJA = 0b0000111111111000


class BladPojazdu(Exception):
    """Nie udało się wykonać operacji na dronie (np. przekroczono limit czasu)."""


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

    def wroc_i_laduj(self, limit_s: float = 180) -> None:
        self._conn.set_mode("RTL")
        log.info("Powrót do bazy (RTL)")
        start = time.time()
        while time.time() - start < limit_s:
            if self._czy_uzbrojony(timeout=2) is False:
                log.info("Wylądowano i rozbrojono")
                return
        raise BladPojazdu(f"Nie wylądowano w ciągu {limit_s} s")