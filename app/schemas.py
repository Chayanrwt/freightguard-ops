from typing import Any, Literal
from pydantic import BaseModel, Field

TenantId = Literal["tenant_freight", "tenant_bank"]
DocType = Literal[
    "commercial_invoice",
    "bill_of_lading",
    "customs_permit",
    "bank_cheque",
    "unknown",
]
RouteAction = Literal["AUTO_EXECUTE", "CLARIFY", "HUMAN_APPROVAL", "QUARANTINED"]


class EvidenceField(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: Literal["deterministic_rule", "ocr_regex", "llm_fallback"]
    source_file: str
    source_page: int = 1
    evidence_quote: str


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    line_total: float
    hs_code: str | None = None


class ExtractedDocumentRecord(BaseModel):
    tenant_id: TenantId
    doc_type: DocType
    reference_number: EvidenceField | None = None
    issuer_or_shipper: EvidenceField | None = None
    consignee_or_payee: EvidenceField | None = None
    document_date: EvidenceField | None = None
    currency: EvidenceField | None = None
    total_amount: EvidenceField | None = None
    origin_port: EvidenceField | None = None
    destination_port: EvidenceField | None = None
    incoterms: EvidenceField | None = None
    hs_codes: list[EvidenceField] = []
    ifsc_code: EvidenceField | None = None
    line_items: list[LineItem] = []


class ValidationFlag(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    message: str


class ProcessingResult(BaseModel):
    doc_id: str
    tenant_id: TenantId
    file_name: str
    ocr_engine_used: str
    llm_calls_made: int
    total_latency_ms: float
    estimated_cost_usd: float
    record: ExtractedDocumentRecord
    flags: list[ValidationFlag] = []
    route_action: RouteAction
    clarification_question: str | None = None
    erp_payload: dict[str, Any] | str | None = None
    execution_trace: list[str] = []
