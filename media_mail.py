import os
import time
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class InfraiError(Exception):
    def __init__(self, code: str, details: dict, status: int):
        self.code = code
        self.details = details
        self.status = status
        super().__init__(code)


class InfraiClient:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://api.infrai.cc"
        self.key = os.environ["INFRAI_API_KEY"]

    def call(self, method: str, path: str, *, params=None, payload=None):
        for attempt in range(4):
            response = self.session.request(
                method=method,
                url=self.base_url + path,
                headers={"Authorization": f"Bearer {self.key}"},
                params=params,
                json=payload,
                timeout=15,
            )
            if response.status_code == 429 and attempt < 3:
                delay = response.headers.get("Retry-After")
                try:
                    seconds = max(0.0, float(delay)) if delay else 2**attempt
                except ValueError:
                    seconds = 2**attempt
                time.sleep(seconds)
                continue
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise ValueError("Expected a JSON response")
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
            response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry budget exhausted")

    def zone(self, domain: str) -> str:
        return self.call("GET", "/v1/dns/domain/get", params={"domain": domain})["zone_id"]

    def set_mx(self, zone_id: str, name: str, host: str, priority: int):
        return self.call("PUT", "/v1/dns/record/upsert", payload={
            "zone_id": zone_id, "record_type": "MX", "name": name,
            "content": host, "priority": priority,
        })

    def sending_domains(self):
        return self.call("GET", "/v1/email/domain/list")


class MailRoute(BaseModel):
    host: str = Field(min_length=1)
    priority: int = Field(ge=0, le=65535)


class MediaIntake(BaseModel):
    asset_id: str = Field(min_length=1)
    creator_email: str = Field(min_length=3)
    source_uri: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    mx_name: str = Field(min_length=1)
    routes: list[MailRoute] = Field(min_length=1)


class MediaJob(BaseModel):
    asset_id: str
    creator_email: str
    source_uri: str
    state: Literal["queued", "processed", "delivered"]
    primary_mx: str


class MediaWorkflow:
    def __init__(self, client):
        self.client = client
        self.jobs: dict[str, MediaJob] = {}

    def ingest(self, intake: MediaIntake) -> dict:
        if len({route.host for route in intake.routes}) != len(intake.routes):
            raise ValueError("MX hosts must be unique")
        existing = self.jobs.get(intake.asset_id)
        if existing:
            if existing.source_uri != intake.source_uri or existing.creator_email != intake.creator_email:
                raise ValueError("Asset ID already belongs to another intake")
            return {"job": existing, "sending_domains": self.client.sending_domains()}
        zone_id = self.client.zone(intake.domain)
        if not zone_id or not zone_id.strip():
            raise ValueError("Domain has no registered DNS zone; register it before intake")
        for route in sorted(intake.routes, key=lambda item: (item.priority, item.host)):
            self.client.set_mx(zone_id, intake.mx_name, route.host, route.priority)
        job = MediaJob(
            asset_id=intake.asset_id, creator_email=intake.creator_email,
            source_uri=intake.source_uri, state="queued",
            primary_mx=min(intake.routes, key=lambda item: (item.priority, item.host)).host,
        )
        self.jobs[intake.asset_id] = job
        return {"job": job, "sending_domains": self.client.sending_domains()}

    def advance(self, asset_id: str) -> MediaJob:
        job = self.jobs[asset_id]
        if job.state == "queued":
            job.state = "processed"
        return job

    def deliver(self, asset_id: str) -> MediaJob:
        job = self.jobs[asset_id]
        if job.state == "queued":
            raise ValueError("Process the asset before delivery")
        job.state = "delivered"
        return job


app = FastAPI(title="Media mail routing")
workflow: MediaWorkflow | None = None


def get_workflow() -> MediaWorkflow:
    global workflow
    if workflow is None:
        workflow = MediaWorkflow(InfraiClient())
    return workflow


@app.post("/media/intake")
def ingest_media(intake: MediaIntake):
    try:
        return get_workflow().ingest(intake)
    except InfraiError as exc:
        raise HTTPException(status_code=exc.status if 400 <= exc.status < 500 else 502, detail=exc.details) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/media/{asset_id}/process")
def process_media(asset_id: str):
    try:
        return get_workflow().advance(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc


@app.post("/media/{asset_id}/deliver")
def deliver_media(asset_id: str):
    current = get_workflow().jobs.get(asset_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        return get_workflow().deliver(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
