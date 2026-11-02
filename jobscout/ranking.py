"""Ranking de ofertas con Claude.

Cada oferta se puntúa de 0 a 100 contra el CV usando salida estructurada,
de modo que la respuesta siempre se convierte en :class:`RankResult`.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

from .models import JobOffer

MAX_OUTPUT_TOKENS = 512

SYSTEM_PROMPT = (
    "Eres un asistente experto en reclutamiento técnico. Evalúas qué tan bien "
    "encaja una oferta de empleo con el perfil de un candidato, basándote en su "
    "CV. Considera: tecnologías que coinciden, nivel del puesto, modalidad y "
    "ubicación. Sé honesto: una oferta que no encaja debe recibir un puntaje "
    "bajo. Responde siempre en español."
)


class RankResult(BaseModel):
    """Resultado estructurado del ranking de una oferta."""

    score: int = Field(description="Puntaje de 0 a 100 de qué tan bien encaja la oferta con el CV.")
    reason: str = Field(description="Justificación breve (1-2 frases, en español) del puntaje.")


class Ranker:
    """Puntúa ofertas contra un CV con Claude.

    Args:
        cv_text: CV en texto plano.
        model: ID del modelo de Claude.
        preferred_modalities: Modalidades (p.ej. "remoto") cuyas ofertas deben
            puntuar más alto; las presenciales bajan, pero no se descartan.
    """

    def __init__(self, cv_text: str, model: str, preferred_modalities: list[str] | None = None):
        self.cv_text = cv_text
        self.model = model
        self.preferred_modalities = preferred_modalities or []
        self.client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

    @property
    def system_prompt(self) -> str:
        """Prompt de sistema con la preferencia de modalidad, si la hay."""
        if not self.preferred_modalities:
            return SYSTEM_PROMPT
        modalities = " o ".join(self.preferred_modalities)
        return (
            f"{SYSTEM_PROMPT} IMPORTANTE: el candidato prefiere trabajo {modalities}; "
            "sube el puntaje a las ofertas con esa modalidad y baja el de las "
            "presenciales, pero sin descartarlas del todo si encajan muy bien."
        )

    def rank(self, offer: JobOffer) -> RankResult:
        """Puntúa una oferta.

        Raises:
            anthropic.APIError: si falla la API (sin saldo, límite de peticiones, caída).
        """
        user_prompt = (
            f"=== CV DEL CANDIDATO ===\n{self.cv_text}\n\n"
            "=== OFERTA DE EMPLEO ===\n"
            f"Título: {offer.title}\n"
            f"Empresa: {offer.company}\n"
            f"Ubicación: {offer.location}\n"
            f"Salario: {offer.salary or 'no especificado'}\n"
            f"Descripción: {offer.description or 'no disponible'}\n\n"
            "Evalúa qué tan bien encaja esta oferta con el candidato."
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=RankResult,
        )
        return response.parsed_output

    def rank_all(self, offers: list[JobOffer]) -> list[JobOffer]:
        """Puntúa ``offers`` en su lugar y devuelve las que se pudieron puntuar.

        Las que fallan quedan fuera para que se reintenten en la próxima
        ejecución. El puntaje se limita a 0-100.
        """
        ranked: list[JobOffer] = []
        for offer in offers:
            try:
                result = self.rank(offer)
            except Exception as exc:  # noqa: BLE001 - una oferta no debe detener la ejecución
                print(f"  [ranking] Error puntuando '{offer.title}': {exc}")
                continue
            offer.score = max(0, min(100, result.score))
            offer.score_reason = result.reason
            ranked.append(offer)
        return ranked
