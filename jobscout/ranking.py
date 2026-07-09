"""Ranking de ofertas con IA (Claude).

Para cada oferta, Claude lee el CV y la descripción y devuelve un puntaje de
0 a 100 más una razón corta. Usamos salida estructurada (Pydantic) para que la
respuesta sea siempre parseable, y el modelo Haiku porque es barato y rápido
para puntuar muchas ofertas.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

from .models import JobOffer


class RankResult(BaseModel):
    """Resultado estructurado del ranking de una oferta."""

    score: int = Field(description="Puntaje de 0 a 100 de qué tan bien encaja la oferta con el CV.")
    reason: str = Field(description="Justificación breve (1-2 frases, en español) del puntaje.")


SYSTEM_PROMPT = """Eres un asistente experto en reclutamiento técnico. Evalúas \
qué tan bien encaja una oferta de empleo con el perfil de un candidato, basándote \
en su CV. Considera: tecnologías que coinciden, nivel del puesto, modalidad y \
ubicación. Sé honesto: una oferta que no encaja debe recibir un puntaje bajo. \
Responde siempre en español."""


class Ranker:
    """Puntúa ofertas comparándolas con un CV mediante Claude."""

    def __init__(self, cv_text: str, model: str):
        self.cv_text = cv_text
        self.model = model
        self.client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

    def rank(self, offer: JobOffer) -> RankResult:
        """Devuelve el puntaje y la razón para una oferta."""
        user_prompt = (
            f"=== CV DEL CANDIDATO ===\n{self.cv_text}\n\n"
            f"=== OFERTA DE EMPLEO ===\n"
            f"Título: {offer.title}\n"
            f"Empresa: {offer.company}\n"
            f"Ubicación: {offer.location}\n"
            f"Salario: {offer.salary or 'no especificado'}\n"
            f"Descripción: {offer.description or 'no disponible'}\n\n"
            "Evalúa qué tan bien encaja esta oferta con el candidato."
        )

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=RankResult,
        )
        return response.parsed_output

    def rank_all(self, offers: list[JobOffer]) -> None:
        """Puntúa una lista de ofertas, escribiendo score y razón en cada una."""
        for offer in offers:
            try:
                result = self.rank(offer)
                offer.score = result.score
                offer.score_reason = result.reason
            except Exception as exc:  # noqa: BLE001 - una oferta no debe romper todo
                print(f"  [ranking] Error puntuando '{offer.title}': {exc}")
                offer.score = 0
                offer.score_reason = "No se pudo evaluar."
