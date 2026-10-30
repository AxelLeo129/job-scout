"""Tests de los parsers de cada portal, contra HTML real guardado.

Los fixtures (tests/fixtures/*.html) son páginas de resultados reales
recortadas a las tarjetas de ofertas. Si un portal cambia su HTML, se
vuelven a bajar y se ajustan los selectores hasta que estos tests pasen.
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from jobscout.scrapers import SCRAPERS

FIXTURES = Path(__file__).parent / "fixtures"


def parse(name: str):
    html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    scraper = SCRAPERS[name](country="gt")
    if name == "unmejorempleo":
        page_url = "https://www.unmejorempleo.com.gt/trabajo-programador.html"
        return scraper._parse_results(BeautifulSoup(html, "html.parser"), page_url)
    return scraper._parse_results(html)


@pytest.mark.parametrize("name", ["computrabajo", "tecoloco", "trabajosdiarios", "unmejorempleo"])
def test_campos_basicos(name):
    offers = parse(name)
    assert len(offers) >= 4
    for offer in offers:
        assert offer.source == name
        assert offer.title.strip()
        assert offer.url.startswith("https://")
        assert "#" not in offer.url
        assert offer.location not in ("", "—")
        assert offer.location != offer.company
    # Las URLs identifican a cada oferta: no deben repetirse.
    assert len({o.url for o in offers}) == len(offers)


def test_computrabajo():
    offers = parse("computrabajo")
    by_title = {o.title: o for o in offers}

    assert by_title["Analista Programador"].company == "Delivery Lab"
    assert by_title["Analista Programador"].location == "Guatemala Ciudad, Guatemala"
    # La calificación de la empresa ("4.4 ★") no forma parte del nombre.
    assert by_title["Desarrollador Backend"].company == "Multigroup"
    # Empresa confidencial: texto suelto, sin enlace.
    backend = by_title["Programador Backend Senior"]
    assert backend.company == "Importante empresa del sector"
    assert backend.salary == "16,000.00 Q (Mensual)"
    assert backend.description == "Modalidad: Presencial y remoto"
    assert all(o.company != "—" for o in offers)


def test_computrabajo_detalle():
    html = (FIXTURES / "computrabajo_detalle.html").read_text(encoding="utf-8")
    detail = SCRAPERS["computrabajo"]._parse_detail(html)

    assert detail.startswith("5,215.00 Q (Mensual) Contrato por tiempo indefinido Tiempo Completo")
    assert "Estamos en busca de un Desarrollador Junior" in detail
    assert "1 año de experiencia; Edad: A partir de 22 años" in detail
    # Fuera: títulos de sección, bloques ocultos, fecha y botones.
    for ruido in ("Descripción de la oferta", "Requerimientos", "aptitudes que faltan",
                  "Palabras clave", "Postularme", "Denunciar"):
        assert ruido not in detail


def test_tecoloco():
    offers = parse("tecoloco")
    first = offers[0]
    assert first.title == "Analista de soluciones de inteligencia artificial"
    assert first.company == "Corporación J.I. COHEN"
    assert first.location == "Ciudad Guatemala, Guatemala"
    assert first.url == "https://www.tecoloco.com.gt/1120211/analista-programador.aspx"
    assert all(o.company != "—" for o in offers)


def test_trabajosdiarios():
    offers = parse("trabajosdiarios")
    first = offers[0]
    assert first.title == "Analista Programador Web"
    assert first.company == "Servicios Logísticos Guatemala, S.A."
    assert first.location == "Guatemala, Guatemala"
    assert first.description
    assert first.url.startswith("https://gt.trabajosdiarios.com/trabajo/3090537/")


def test_unmejorempleo():
    offers = parse("unmejorempleo")
    titles = [o.title for o in offers]
    # El sitio resalta la palabra buscada en otra etiqueta; no debe quedar
    # pegada al resto del título ("ProgramadorJunior").
    assert "Programador Junior Java" in titles
    assert "Programador para la Banca hibrido" in titles
    java = offers[titles.index("Programador Junior Java")]
    assert java.salary == "7,000"
    assert java.description
