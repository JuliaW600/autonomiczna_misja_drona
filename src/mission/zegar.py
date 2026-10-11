"""Zegar jako zależność: logika misji pyta zegar o czas, zamiast wołać `time.time()` wprost.

W teście podstawiamy `ZegarSztuczny`, więc "10 minut lotu" trwa ułamek sekundy
i wynik jest zawsze taki sam.
"""
import time
from abc import ABC, abstractmethod


class Zegar(ABC):
    @abstractmethod
    def teraz(self) -> float:
        """Aktualny czas w sekundach (liczy się tylko różnica między dwoma odczytami)."""

    @abstractmethod
    def czekaj(self, sekundy: float) -> None: ...


class ZegarSystemowy(Zegar):
    def teraz(self) -> float:
        return time.monotonic()

    def czekaj(self, sekundy: float) -> None:
        time.sleep(sekundy)


class ZegarSztuczny(Zegar):
    """Czas płynie tylko wtedy, gdy ktoś każe mu płynąć (`czekaj`)."""

    def __init__(self, start: float = 0.0):
        self._czas = start

    def teraz(self) -> float:
        return self._czas

    def czekaj(self, sekundy: float) -> None:
        if sekundy < 0:
            raise ValueError("sekundy nie mogą być ujemne")
        self._czas += sekundy