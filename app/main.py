import json
import shutil
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent.workflow import run_document_pipeline
from app.connectors.cargowise_xml import build_cargowise_xml
from app.connectors.logisys_json import build_logisys_payload
from app.knowledge.rag_store import seed_tenant_rules
from app.knowledge.sql_store import (
    approve_with_correction,
    init_db,
    list_documents,
)
from app.schemas import ExtractedDocumentRecord, ProcessingResult, TenantId

app = FastAPI(title="FreightGuard Ops — Deterministic-First Document AI", version="1.0.0")
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_tenant_rules()


class ApprovalRequest(BaseModel):
    corrected_record: dict
    reviewer_notes: str = ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/process", response_model=ProcessingResult)
async def process_uploaded_document(
    file: UploadFile = File(...),
    tenant_id: TenantId = Form("tenant_freight"),
) -> ProcessingResult:
    dest = UPLOAD_DIR / (file.filename or "upload.pdf")
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return run_document_pipeline(dest, tenant_id=tenant_id, persist=True)


@app.get("/api/documents")
def get_documents(tenant_id: str | None = None) -> list[dict]:
    rows = list_documents(tenant_id=tenant_id)
    return [r.model_dump() for r in rows]


@app.post("/api/documents/{doc_id}/approve")
def approve_document(doc_id: str, body: ApprovalRequest) -> dict:
    record = ExtractedDocumentRecord.model_validate(body.corrected_record)
    if record.tenant_id == "tenant_freight":
        erp_str = json.dumps(
            {
                "logisys_job": build_logisys_payload(record),
                "cargowise_xml": build_cargowise_xml(record),
            },
            indent=2,
        )
    else:
        erp_str = json.dumps(build_logisys_payload(record), indent=2)

    ok = approve_with_correction(
        doc_id=doc_id,
        corrected_record_json=record.model_dump_json(),
        erp_payload=erp_str,
        notes=body.reviewer_notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Document ID not found.")
    return {"status": "APPROVED", "doc_id": doc_id, "erp_payload": erp_str}


@app.get("/api/metrics")
def get_metrics() -> dict:
    docs = list_documents()
    total = len(docs)
    if total == 0:
        return {
            "total_processed": 0,
            "auto_executed": 0,
            "human_review_queue": 0,
            "quarantined": 0,
            "avg_latency_ms": 0.0,
            "total_cost_usd": 0.0,
        }
    auto_exec = sum(1 for d in docs if d.route_action == "AUTO_EXECUTE")
    quarantined = sum(1 for d in docs if d.route_action == "QUARANTINED")
    pending = sum(1 for d in docs if d.reviewer_status == "PENDING")
    avg_lat = sum(d.total_latency_ms for d in docs) / total
    tot_cost = sum(d.estimated_cost_usd for d in docs)
    return {
        "total_processed": total,
        "auto_executed": auto_exec,
        "human_review_queue": pending,
        "quarantined": quarantined,
        "avg_latency_ms": round(avg_lat, 1),
        "total_cost_usd": round(tot_cost, 5),
    }
