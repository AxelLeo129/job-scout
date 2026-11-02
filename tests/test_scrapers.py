"""Parser tests against real board HTML.

Fixtures (tests/fixtures/*.html) are real result pages trimmed to the offer
cards, without images. When a board changes its markup, download a new page,
replace the fixture and adjust the selectors until these tests pass.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from jobscout.models import JobOffer
from jobscout.scrapers import SCRAPERS

FIXTURES = Path(__file__).parent / "fixtures"


def parse(name: str) -> list[JobOffer]:
    html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    scraper = SCRAPERS[name](country="gt")
    if name == "unmejorempleo":
        page_url = "https://www.unmejorempleo.com.gt/trabajo-programador.html"
        return scraper._parse_results(BeautifulSoup(html, "html.parser"), page_url)
    return scraper._parse_results(html)


@pytest.mark.parametrize("name", ["computrabajo", "tecoloco", "trabajosdiarios", "unmejorempleo"])
def test_basic_fields(name):
    offers = parse(name)
    assert len(offers) >= 4
    for offer in offers:
        assert offer.source == name
        assert offer.title.strip()
        assert offer.url.startswith("https://")
        assert "#" not in offer.url
        assert offer.location not in ("", "—")
        assert offer.location != offer.company
    assert len({o.url for o in offers}) == len(offers)


def test_computrabajo():
    by_title = {o.title: o for o in parse("computrabajo")}

    assert by_title["Analista Programador"].company == "Delivery Lab"
    assert by_title["Analista Programador"].location == "Guatemala Ciudad, Guatemala"
    # The employer rating ("4.4 ★") is not part of the name.
    assert by_title["Desarrollador Backend"].company == "Multigroup"
    # Confidential employer: plain text instead of a link.
    backend = by_title["Programador Backend Senior"]
    assert backend.company == "Importante empresa del sector"
    assert backend.salary == "16,000.00 Q (Mensual)"
    assert backend.description == "Modalidad: Presencial y remoto"
    assert all(o.company != "—" for o in by_title.values())


def test_computrabajo_detail():
    html = (FIXTURES / "computrabajo_detail.html").read_text(encoding="utf-8")
    detail = SCRAPERS["computrabajo"]._parse_detail(html)

    assert detail.startswith("5,215.00 Q (Mensual) Contrato por tiempo indefinido Tiempo Completo")
    assert "Estamos en busca de un Desarrollador Junior" in detail
    assert "1 año de experiencia; Edad: A partir de 22 años" in detail
    # Section headings, hidden blocks, date and buttons are left out.
    for noise in (
        "Descripción de la oferta",
        "Requerimientos",
        "aptitudes que faltan",
        "Palabras clave",
        "Postularme",
        "Denunciar",
    ):
        assert noise not in detail


def test_tecoloco():
    offers = parse("tecoloco")
    first = offers[0]
    assert first.title == "Analista de soluciones de inteligencia artificial"
    assert first.company == "Corporación J.I. COHEN"
    assert first.location == "Ciudad Guatemala, Guatemala"
    assert first.url == "https://www.tecoloco.com.gt/1120211/analista-programador.aspx"
    assert all(o.company != "—" for o in offers)


def test_trabajosdiarios():
    first = parse("trabajosdiarios")[0]
    assert first.title == "Analista Programador Web"
    assert first.company == "Servicios Logísticos Guatemala, S.A."
    assert first.location == "Guatemala, Guatemala"
    assert first.description
    assert first.url.startswith("https://gt.trabajosdiarios.com/trabajo/3090537/")


def test_unmejorempleo():
    offers = parse("unmejorempleo")
    titles = [o.title for o in offers]
    # The highlighted search word must not stick to the next one ("ProgramadorJunior").
    assert "Programador Junior Java" in titles
    assert "Programador para la Banca hibrido" in titles
    java = offers[titles.index("Programador Junior Java")]
    assert java.salary == "7,000"
    assert java.description


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Sueldo Q5,000 - Q7,000 mensual", "Q5,000 - Q7,000"),
        ("16,000.00 Q (Mensual)", "16,000.00 Q"),
        ("$1,200", "$1,200"),
        ("Quetzaltenango, sin salario", ""),
    ],
)
def test_find_salary(text, expected):
    from jobscout.scrapers.base import find_salary

    assert find_salary(text) == expected
