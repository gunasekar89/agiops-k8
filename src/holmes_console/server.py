"""Authenticated Alertmanager webhook service for the Version 2 healer."""

import argparse
import hmac
import json
import os
from typing import Any, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status

from .analyzer import InvestigationAnalyzer
from .config import Config
from .healer import AlertError, AlertHealer
from .holmes import HolmesClient
from .kubernetes import KubernetesCollector
from .models import HealingMode
from .policy import SafetyPolicy
from .remediation import KubernetesRemediator

MAX_WEBHOOK_BYTES = 1_048_576
MAX_ALERTS_PER_REQUEST = 20


def create_app(
    healer: AlertHealer,
    webhook_token: str,
    allow_unauthenticated: bool = False,
) -> FastAPI:
    app = FastAPI(title="Aegis Holmes Alert Healer", version="0.2.0")

    def authorize(authorization: Optional[str]) -> None:
        if allow_unauthenticated:
            return
        expected = f"Bearer {webhook_token}"
        if (
            not webhook_token
            or not authorization
            or not hmac.compare_digest(authorization, expected)
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook token")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        if not healer.collector.available() or not healer.analyzer.holmes.available():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "kubectl or HolmesGPT CLI is unavailable",
            )
        return {"status": "ready"}

    @app.post("/api/v1/alerts", status_code=status.HTTP_202_ACCEPTED)
    async def receive_alerts(
        request: Request,
        background_tasks: BackgroundTasks,
        authorization: Optional[str] = Header(default=None),
    ) -> dict[str, Any]:
        authorize(authorization)
        content_length = int(request.headers.get("content-length", "0") or 0)
        if content_length > MAX_WEBHOOK_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "payload too large")
        raw_body = await request.body()
        if len(raw_body) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "payload too large")
        try:
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON payload") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid Alertmanager payload")
        if len(payload["alerts"]) > MAX_ALERTS_PER_REQUEST:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"at most {MAX_ALERTS_PER_REQUEST} alerts are accepted per request",
            )
        common_labels = payload.get("commonLabels") or {}
        if not isinstance(common_labels, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "commonLabels must be an object")
        jobs = []
        errors = []
        for alert in payload["alerts"]:
            if not isinstance(alert, dict):
                errors.append("each alert must be an object")
                continue
            try:
                job_id, created = healer.submit(alert, common_labels)
                jobs.append({"id": job_id, "created": created})
                if created:
                    background_tasks.add_task(healer.process, job_id)
            except AlertError as exc:
                errors.append(str(exc))
        if not jobs:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, errors)
        return {"jobs": jobs, "rejected": errors}

    @app.get("/api/v1/investigations/{job_id}")
    def investigation(
        job_id: str, authorization: Optional[str] = Header(default=None)
    ) -> dict[str, Any]:
        authorize(authorization)
        job = healer.get(job_id)
        if not job:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "investigation not found")
        return job

    return app


def build_healer(mode: HealingMode, max_risk_score: int) -> AlertHealer:
    config = Config.from_env()
    collector = KubernetesCollector(config.kubectl, max_log_chars=config.max_log_chars)
    holmes = HolmesClient(config.holmes, config.timeout_seconds)
    return AlertHealer(
        InvestigationAnalyzer(collector, holmes),
        collector,
        KubernetesRemediator(config.kubectl),
        SafetyPolicy(max_risk_score=max_risk_score),
        mode,
    )


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="alert-healer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--mode", choices=[item.value for item in HealingMode], default="observe")
    parser.add_argument("--max-risk-score", type=int, default=25)
    parser.add_argument("--insecure-no-auth", action="store_true")
    args = parser.parse_args(argv)
    token = os.getenv("HOLMES_HEALER_WEBHOOK_TOKEN", "")
    if not args.insecure_no_auth and not token:
        parser.error("HOLMES_HEALER_WEBHOOK_TOKEN is required unless --insecure-no-auth is set")
    mode = HealingMode(args.mode)
    try:
        healer = build_healer(mode, args.max_risk_score)
    except ValueError as exc:
        parser.error(str(exc))
    app = create_app(healer, token, args.insecure_no_auth)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
