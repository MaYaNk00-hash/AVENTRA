"""Optional language-to-tool planning. No credentials or client rows in model context."""
import json
import os
import re
import hashlib
import time
from datetime import datetime, timezone
from typing import Literal

import requests
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, PrivateAttr

_verification = None


def record_verification(ok, reason, started, attempts=1):
    global _verification
    key, model = settings()
    _verification = {"fingerprint": hashlib.sha256((key + model).encode()).hexdigest(),
                     "ok": ok, "reason": reason,
                     "checked_at": datetime.now(timezone.utc).isoformat(),
                     "duration_ms": round((time.perf_counter() - started) * 1000, 2), "attempts": attempts}


def request_plan(session, url, key, payload):
    """Retry only plan generation. No enterprise operation occurs in this helper."""
    for attempt in range(1, 4):
        try:
            response = session.post(url, headers={"x-goog-api-key": key}, json=payload,
                                    timeout=(5, 25), allow_redirects=False)
        except (requests.Timeout, requests.ConnectionError) as error:
            error.gemini_attempts = attempt
            if isinstance(error, requests.exceptions.SSLError) or attempt == 3:raise
            time.sleep(.5 * attempt)
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            retry_after = getattr(response, "headers", {}).get("Retry-After", "")
            try:delay = float(retry_after) if retry_after else .5 * attempt
            except ValueError:return response, attempt  # Long/dated quota reset needs user action.
            if not 0 <= delay <= 5:return response, attempt
            if hasattr(response, "close"):response.close()
            time.sleep(delay)
            continue
        return response, attempt


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=200)
    value_json: str = Field(max_length=2000)


class ToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["retrieve", "summary", "compare", "update", "analyze", "unsupported"]
    query: str = Field(max_length=2000)
    source_id: str = Field(max_length=100)
    resource: str = Field(max_length=300)
    record_key: str = Field(max_length=300)
    changes: list[Change] = Field(max_length=10)
    explanation: str = Field(max_length=1000)
    analysis_model: Literal["", "entity_resolution", "semantic_schema_mapper", "intent_parser", "workflow_planner", "invoice_reconciliation", "adaptation_recommender", "document_intelligence", "anomaly_detection"] = ""
    _provider_metadata: dict = PrivateAttr(default_factory=dict)


def settings():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    return key, model


def status():
    key, model = settings()
    check = _verification if _verification and _verification["fingerprint"] == hashlib.sha256((key + model).encode()).hexdigest() else None
    return {"configured": bool(key), "model": model, "provider": "gemini",
            "context": "User request and approved schema metadata only; no retrieved rows",
            "live_connection_verified": bool(check and check["ok"]),
            "verification_status": "verified" if check and check["ok"] else "failed" if check else "not_checked",
            "verification_reason": check["reason"] if check else None,
            "checked_at": check["checked_at"] if check else None,
            "duration_ms": check["duration_ms"] if check else None,
            "attempts": check["attempts"] if check else None}


def plan(goal, capabilities):
    started = time.perf_counter()
    key, model = settings()
    if not key:
        raise HTTPException(503, "Gemini is not configured. Set GEMINI_API_KEY on the backend or select the local planner")
    if not re.fullmatch(r"gemini-[a-zA-Z0-9._-]+", model):
        raise HTTPException(503, "Invalid GEMINI_MODEL configuration")
    context = json.dumps({"request": goal, "approved_capabilities": capabilities}, ensure_ascii=False)
    if len(context.encode()) > 100000:
        raise HTTPException(422, "Selected schema is too large for the planner; select fewer sources")
    instruction = (
        "Translate the user request into exactly one supported tool action from approved_capabilities. "
        "Available actions: retrieve, summary, compare, update, analyze, unsupported. "
        "For retrieve: read, search, list, browse, or query records. Use empty query string to browse or list records. "
        "If targeting a specific resource, set both its source_id and resource from approved_capabilities. "
        "If retrieving across all sources or multiple systems, leave source_id and resource empty. "
        "For summary: calculate counts, metrics and aggregates across resources. "
        "For compare: entity matching or duplicate resolution across sources. Leave source_id and resource empty. "
        "For update: prepare a single field update. Requires exact record_key, source_id, resource, and changes. "
        "For analyze: local model inference on structured input when a local_ml capability is present. "
        "Only use unsupported for unfulfillable actions like deleting data, bank payments, or sending external emails."
    )
    try:
        generation_config = {"temperature": 0, "maxOutputTokens": 2048,
                             "responseMimeType": "application/json", "responseJsonSchema": ToolPlan.model_json_schema()}
        if model.startswith("gemini-3"):
            # This planner maps one short request to one validated tool action.
            # Use the provider's supported low thinking level to reduce latency.
            generation_config["thinkingConfig"] = {"thinkingLevel": "LOW"}
        with requests.Session() as session:
            session.trust_env = False
            response, attempts = request_plan(session,
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                key, {"systemInstruction": {"parts": [{"text": instruction}]},
                      "contents": [{"role": "user", "parts": [{"text": context}]}],
                      "generationConfig": generation_config})
            if response.status_code != 200:
                # Provider bodies can echo prompts or credentials; never persist them.
                record_verification(False, f"provider_http_{response.status_code}", started, attempts)
                guidance = {400: "Google rejected the request configuration; check the configured model and structured-output support",
                            401: "Google rejected authentication; verify the backend Gemini credential",
                            403: "Google denied access; check project permissions and API-key restrictions",
                            404: "The configured model is unavailable for this key; select an accessible GEMINI_MODEL",
                            429: "Gemini quota or rate limit reached; check project quota and billing",
                            503: "Gemini is temporarily unavailable; retry later"}.get(response.status_code, "Google returned a provider error; retry later")
                raise HTTPException(502, f"{guidance} (HTTP {response.status_code}); no fallback or write was performed")
            body = response.json()
        candidate = body["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete plan")
        content = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
        result = ToolPlan.model_validate_json(content)
        record_verification(True, "validated_structured_response", started, attempts)
        result._provider_metadata = {"attempts": attempts, "model": model}
    except HTTPException:
        raise
    except requests.RequestException as error:
        record_verification(False, "network_or_timeout", started, getattr(error, "gemini_attempts", 1))
        raise HTTPException(502, "Gemini was unreachable or timed out; no fallback or write was performed")
    except (ValueError, KeyError, IndexError, TypeError, ValidationError):
        record_verification(False, "invalid_or_incomplete_response", started)
        raise HTTPException(502, "Gemini returned an invalid or incomplete tool plan; no fallback or write was performed")
    if result.action == "unsupported":
        raise HTTPException(422, "Gemini could not map this request to the supported tools. Rephrase with one explicit retrieval, summary, comparison or field update")
    return result
