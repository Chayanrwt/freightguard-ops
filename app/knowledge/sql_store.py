import json
from datetime import datetime, timezone
from pathlib import Path
from sqlmodel import Field, Session, SQLModel, create_engine, select
from app.config import settings
from app.schemas import ProcessingResult


class ShipmentMaster(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    shipment_ref: str = Field(index=True)
    shipper_name: str
    origin_port: str
    destination_port: str
    kyc_verified: bool = True


class DocumentAuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: str = Field(index=True, unique=True)
    tenant_id: str = Field(index=True)
    file_name: str
    doc_type: str
    ocr_engine_used: str
    llm_calls_made: int
    total_latency_ms: float
    estimated_cost_usd: float
    route_action: str
    reviewer_status: str = "PENDING"  # AUTO_APPROVED | PENDING | APPROVED | REJECTED
    record_json: str
    flags_json: str
    clarification_question: str | None = None
    erp_payload: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HumanCorrection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    file_name: str
    original_json: str
    corrected_json: str
    reviewer_notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


Path("data").mkdir(exist_ok=True)
engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def lookup_shipper_records(tenant_id: str, shipper_query: str | None) -> list[dict]:
    """Typed SQL query over live operational master records (strictly scoped by tenant_id)."""
    with Session(engine) as session:
        stmt = select(ShipmentMaster).where(ShipmentMaster.tenant_id == tenant_id)
        rows = session.exec(stmt).all()
        if not shipper_query:
            return [r.model_dump() for r in rows[:3]]
        q = shipper_query.lower()
        matched = [r.model_dump() for r in rows if q in r.shipper_name.lower() or r.shipper_name.lower() in q]
        return matched


def save_processing_result(result: ProcessingResult) -> None:
    reviewer_status = "AUTO_APPROVED" if result.route_action == "AUTO_EXECUTE" else "PENDING"
    erp_str = (
        result.erp_payload
        if isinstance(result.erp_payload, str)
        else json.dumps(result.erp_payload, indent=2)
        if result.erp_payload is not None
        else None
    )
    row = DocumentAuditLog(
        doc_id=result.doc_id,
        tenant_id=result.tenant_id,
        file_name=result.file_name,
        doc_type=result.record.doc_type,
        ocr_engine_used=result.ocr_engine_used,
        llm_calls_made=result.llm_calls_made,
        total_latency_ms=result.total_latency_ms,
        estimated_cost_usd=result.estimated_cost_usd,
        route_action=result.route_action,
        reviewer_status=reviewer_status,
        record_json=result.record.model_dump_json(),
        flags_json=json.dumps([f.model_dump() for f in result.flags]),
        clarification_question=result.clarification_question,
        erp_payload=erp_str,
    )
    with Session(engine) as session:
        existing = session.exec(select(DocumentAuditLog).where(DocumentAuditLog.doc_id == result.doc_id)).first()
        if existing:
            session.delete(existing)
            session.commit()
        session.add(row)
        session.commit()


def list_documents(tenant_id: str | None = None) -> list[DocumentAuditLog]:
    with Session(engine) as session:
        stmt = select(DocumentAuditLog).order_by(DocumentAuditLog.id.desc())
        if tenant_id:
            stmt = stmt.where(DocumentAuditLog.tenant_id == tenant_id)
        return list(session.exec(stmt).all())


def approve_with_correction(
    doc_id: str,
    corrected_record_json: str,
    erp_payload: str,
    notes: str = "",
) -> bool:
    with Session(engine) as session:
        doc = session.exec(select(DocumentAuditLog).where(DocumentAuditLog.doc_id == doc_id)).first()
        if not doc:
            return False
        correction = HumanCorrection(
            doc_id=doc.doc_id,
            tenant_id=doc.tenant_id,
            file_name=doc.file_name,
            original_json=doc.record_json,
            corrected_json=corrected_record_json,
            reviewer_notes=notes,
        )
        doc.record_json = corrected_record_json
        doc.erp_payload = erp_payload
        doc.reviewer_status = "APPROVED"
        session.add(correction)
        session.add(doc)
        session.commit()
        return True
