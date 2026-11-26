import hashlib
from app.connectors.cargowise_xml import normalize_unlocode
from app.schemas import ExtractedDocumentRecord


def build_logisys_payload(record: ExtractedDocumentRecord) -> dict:
    """Generates Logi-sys ERP Job Intake JSON with deterministic idempotency key."""
    ref = str(record.reference_number.value) if record.reference_number else "UNKNOWN"
    idem_key = hashlib.sha256(f"{record.tenant_id}:{ref}".encode()).hexdigest()[:16]

    return {
        "erp_target": "Logi-sys_v4",
        "idempotency_key": idem_key,
        "tenant_id": record.tenant_id,
        "document_type": record.doc_type,
        "job_reference": ref,
        "shipper": record.issuer_or_shipper.value if record.issuer_or_shipper else None,
        "consignee": record.consignee_or_payee.value if record.consignee_or_payee else None,
        "pol_unlocode": normalize_unlocode(record.origin_port.value if record.origin_port else None),
        "pod_unlocode": normalize_unlocode(record.destination_port.value if record.destination_port else None),
        "incoterms": record.incoterms.value if record.incoterms else None,
        "hs_codes": [h.value for h in record.hs_codes],
        "declared_value": {
            "amount": record.total_amount.value if record.total_amount else None,
            "currency": record.currency.value if record.currency else None,
        },
    }
