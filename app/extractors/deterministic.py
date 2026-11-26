import re
from app.schemas import DocType, EvidenceField, ExtractedDocumentRecord, TenantId


def _find_evidence(pattern: str, text: str, file_name: str, method: str = "deterministic_rule") -> EvidenceField | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    val = match.group(1).strip()
    quote = match.group(0).strip()
    return EvidenceField(
        value=val,
        confidence=0.97,
        extraction_method=method,  # type: ignore[arg-type]
        source_file=file_name,
        source_page=1,
        evidence_quote=quote,
    )


def classify_deterministically(text: str, tenant_id: TenantId) -> DocType | None:
    lower = text.lower()
    if tenant_id == "tenant_bank" or "ifsc" in lower or "pay against this cheque" in lower:
        return "bank_cheque"
    if "bill of lading" in lower or "b/l no" in lower or "vessel" in lower:
        return "bill_of_lading"
    if "customs declaration" in lower or "import permit" in lower or "permit no" in lower:
        return "customs_permit"
    if "commercial invoice" in lower or "invoice no" in lower:
        return "commercial_invoice"
    return None


def run_deterministic_extraction(
    text: str,
    file_name: str,
    tenant_id: TenantId,
) -> tuple[ExtractedDocumentRecord, list[str]]:
    doc_type = classify_deterministically(text, tenant_id) or "unknown"

    ref = _find_evidence(
        r"(?:Invoice\s*No|B/L\s*No|Permit\s*No|Cheque\s*No)[:#\s]+([A-Z0-9\-/]{4,25})",
        text,
        file_name,
    )
    date_field = _find_evidence(
        r"(?:Date)[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
        text,
        file_name,
    )
    amount_match = re.search(
        r"(?:Total\s*Amount|Grand\s*Total|Amount)[:\s]*(USD|INR|EUR|\$|₹)?\s*([0-9,]+\.\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    total_amount: EvidenceField | None = None
    currency: EvidenceField | None = None
    if amount_match:
        raw_curr = (amount_match.group(1) or "USD").replace("$", "USD").replace("₹", "INR").upper()
        raw_amt = float(amount_match.group(2).replace(",", ""))
        quote = amount_match.group(0).strip()
        total_amount = EvidenceField(
            value=raw_amt,
            confidence=0.96,
            extraction_method="deterministic_rule",
            source_file=file_name,
            source_page=1,
            evidence_quote=quote,
        )
        currency = EvidenceField(
            value=raw_curr,
            confidence=0.96,
            extraction_method="deterministic_rule",
            source_file=file_name,
            source_page=1,
            evidence_quote=quote,
        )

    incoterms = _find_evidence(r"\bIncoterms?[:\s]+(FOB|CIF|EXW|DDP|DAP|FCA|CFR)\b", text, file_name)
    origin = _find_evidence(r"(?:Port\s*of\s*Loading|Origin)[:\s]+([A-Za-z\s,]{3,35})", text, file_name)
    dest = _find_evidence(r"(?:Port\s*of\s*Discharge|Destination)[:\s]+([A-Za-z\s,]{3,35})", text, file_name)
    ifsc_match = re.search(
        r"(?:I[FPE]SC|FSC|1FSC)[^\nA-Z0-9]{0,5}([A-Z0-9][A-Z0-9 \-]{9,15})|\b([A-Z]{4}[0O][0-9OIL]{6})\b",
        text,
        flags=re.IGNORECASE,
    )
    ifsc: EvidenceField | None = None
    if ifsc_match:
        matched_group = ifsc_match.group(1) or ifsc_match.group(2) or ""
        raw_code = re.sub(r"[\s\-]+", "", matched_group.upper())[:11]
        if len(raw_code) == 11:
            bank_prefix = raw_code[:4].translate(str.maketrans("0158", "OISB"))
            branch_code = raw_code[5:].translate(str.maketrans("OIL", "011"))
            norm_ifsc = f"{bank_prefix}0{branch_code}"
            if re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", norm_ifsc):
                ifsc = EvidenceField(
                    value=norm_ifsc,
                    confidence=0.95,
                    extraction_method="ocr_regex",
                    source_file=file_name,
                    source_page=1,
                    evidence_quote=ifsc_match.group(0).strip(),
                )

    hs_matches = list(re.finditer(r"\bHS\s*Code[:\s]*(\d{4}\.\d{2}(?:\.\d{2})?)\b", text, flags=re.IGNORECASE))
    hs_fields = [
        EvidenceField(
            value=m.group(1),
            confidence=0.95,
            extraction_method="deterministic_rule",
            source_file=file_name,
            source_page=1,
            evidence_quote=m.group(0).strip(),
        )
        for m in hs_matches
    ]

    record = ExtractedDocumentRecord(
        tenant_id=tenant_id,
        doc_type=doc_type,
        reference_number=ref,
        document_date=date_field,
        currency=currency,
        total_amount=total_amount,
        incoterms=incoterms,
        origin_port=origin,
        destination_port=dest,
        hs_codes=hs_fields,
        ifsc_code=ifsc,
    )

    missing: list[str] = []
    if doc_type == "unknown":
        missing.append("doc_type")
    if not ref:
        missing.append("reference_number")
    if not record.issuer_or_shipper:
        missing.append("issuer_or_shipper")
    if doc_type in ("commercial_invoice", "bank_cheque") and not total_amount:
        missing.append("total_amount")
    if doc_type in ("commercial_invoice", "customs_permit") and not hs_fields:
        missing.append("hs_codes")

    return record, missing
