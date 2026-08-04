from __future__ import annotations

import json
import logging
import re
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.scout.catalog import ACTION_CATALOG, build_action, prompt_catalog, sanitize_action_parameters
from app.modules.scout.prompts import ASK_SCOUT_RESPONSE_SCHEMA, SYSTEM_PROMPT
from app.modules.scout.schemas import AskScoutRequest, AskScoutResult, ScoutAction, ScoutModelOutput


LOGGER = logging.getLogger(__name__)
URL_PATTERN = re.compile(r"https?://[^\s<>\]\[(){}\"']+", re.IGNORECASE)


class AskScoutProvider(Protocol):
    def answer(self, request: AskScoutRequest, catalog: list[dict]) -> ScoutModelOutput: ...


class OpenAIAskScoutProvider:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def answer(self, request: AskScoutRequest, catalog: list[dict]) -> ScoutModelOutput:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": request.question,
                            "current_path": request.current_path,
                            "page_context": request.page_context.model_dump(mode="json"),
                            "capability_catalog": catalog,
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
            response_format={"type": "json_schema", "json_schema": ASK_SCOUT_RESPONSE_SCHEMA},
        )
        content = response.choices[0].message.content
        if not content:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ask Scout returned an empty response.")
        try:
            return ScoutModelOutput.model_validate_json(content)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ask Scout returned an invalid response. Retry the operation.",
            ) from exc


def extract_http_url(question: str) -> str | None:
    match = URL_PATTERN.search(question)
    if not match:
        return None
    value = match.group(0).rstrip(".,;:!?")
    parsed = urlsplit(value)
    if (
        len(value) > 2048
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return value


class AskScoutService:
    def __init__(self, provider: AskScoutProvider) -> None:
        self._provider = provider

    def answer(self, request: AskScoutRequest) -> AskScoutResult:
        model_output = self._provider.answer(request, prompt_catalog())
        return self._normalize(request, model_output)

    @staticmethod
    def _normalize(request: AskScoutRequest, output: ScoutModelOutput) -> AskScoutResult:
        context = request.page_context.model_dump()
        extracted_url = extract_http_url(request.question)
        action_id = output.action_id if output.action_id in ACTION_CATALOG else None
        parameters = sanitize_action_parameters(
            action_id or "",
            output.action_parameters,
            trusted_context=context,
            extracted_url=extracted_url,
        )
        built = build_action(action_id, parameters) if action_id else None
        primary = ScoutAction.model_validate(built) if built else None
        alternatives: list[ScoutAction] = []
        for alternative_id in output.alternative_action_ids:
            if alternative_id == action_id or alternative_id not in ACTION_CATALOG:
                continue
            candidate = build_action(alternative_id)
            if candidate:
                alternatives.append(ScoutAction.model_validate(candidate))
        public_status = output.status
        if public_status == "navigate" and primary is None:
            public_status = "needs_context" if action_id else "unsupported"
        if public_status != "navigate":
            primary = None
        answer = output.answer.strip()
        forbidden_claims = re.compile(r"\b(I|I've|I have)\s+(clicked|submitted|saved|deleted|imported|scraped|matched|generated|updated|created)\b", re.IGNORECASE)
        if forbidden_claims.search(answer):
            answer = "I can guide you to the relevant DaliJob page, but you will need to review and complete the action yourself."
        LOGGER.info(
            "ask_scout_result status=%s action_id=%s confidence=%s",
            public_status,
            primary.action_id if primary else None,
            output.confidence,
        )
        return AskScoutResult(
            status=public_status,
            answer=answer,
            primary_action=primary,
            alternative_actions=alternatives[:2],
            limitations=[item.strip() for item in output.limitations if item.strip()][:3],
        )

