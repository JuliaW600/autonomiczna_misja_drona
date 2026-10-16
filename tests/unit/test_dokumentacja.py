"""Testy dokumentacji"""
import re
from pathlib import Path

import pytest

KORZEN = Path(__file__).resolve().parents[2]
README = KORZEN / "README.md"
SCENARIUSZE = sorted((KORZEN / "config" / "scenarios").glob("*.yaml"))



@pytest.fixture(scope="module")
def tresc() -> str:
    return README.read_text(encoding="utf-8")


def _lokalne_linki(tresc: str) -> list[str]:
    cele = re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", tresc)
    return [c for c in cele if not c.startswith(("http://", "https://", "#", "mailto:"))]


def test_readme_istnieje():
    assert README.is_file()


def test_linki_do_plikow_istnieja(tresc):
    brakujace = [c for c in _lokalne_linki(tresc) if not (KORZEN / c).exists()]
    assert brakujace == [], f"README odsyła do nieistniejących plików: {brakujace}"


def test_readme_ma_przynajmniej_jeden_lokalny_link(tresc):
    assert _lokalne_linki(tresc), "README powinno zawierać zrzuty ekranu lub linki do plików z docs/"


@pytest.mark.parametrize("numer", range(1, 12))
def test_sekcje_wymagane_przez_zadanie(tresc, numer):
    assert re.search(rf"^## {numer}\. ", tresc, re.MULTILINE), f"brak sekcji '## {numer}. ...' w README"


@pytest.mark.parametrize("plik", SCENARIUSZE, ids=lambda p: p.stem)
def test_kazdy_scenariusz_jest_opisany(tresc, plik):
    nazwa = plik.stem.split("_", 1)[1]
    assert f"`{nazwa}`" in tresc, f"scenariusz '{nazwa}' nie jest opisany w README"


def test_sa_scenariusze():
    assert len(SCENARIUSZE) >= 8

