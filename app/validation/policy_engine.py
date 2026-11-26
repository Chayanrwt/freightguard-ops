import re
from app.config import settings
from app.schemas import ExtractedDocumentRecord, LineItem, RouteAction, ValidationFlag


def _extract_line_items_fallback(raw_text: str) -> list[LineItem]:
    items: list[LineItem] = []
    pattern = re.compile(
        r"Item\s*\d+:\s*([^|]+)\|\s*Qty:\s*([0-9.]+)\s*\|\s*Unit\s*Price:\s*([0-9.]+)\s*\|\s*Line\s*Total:\s*([0-9.]+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(raw_text):
        items.append(
            LineItem(
                description=m.group(1).strip(),
                quantity=float(m.group(2)),
                unit_price=float(m.group(3)),
                line_total=float(m.group(4)),
            )
        )
    return items


def validate_and_route(
    record: ExtractedDocumentRecord,
    raw_text: str,
    existing_flags: list[ValidationFlag],
) -> tuple[RouteAction, list[ValidationFlag], str | None]:
    """
    Deterministic Server-Side Guardrail:
    Agent proposes structured extraction; Python policy engine validates math,
    evidence grounding, compliance thresholds, and routing state.
    """
    flags = list(existing_flags)

    if any(f.code == "PROMPT_INJECTION_DETECTED" for f in flags):
        return "QUARANTINED", flags, None

    normalized_text = " ".join(raw_text.lower().split())
    for field_name in ("reference_number", "issuer_or_shipper", "total_amount", "incoterms", "ifsc_code"):
        field_obj = getattr(record, field_name)
        if field_obj and field_obj.evidence_quote:
            quote_norm = " ".join(field_obj.evidence_quote.lower().split())
            if quote_norm not in normalized_text:
                flags.append(
                    ValidationFlag(
                        code="UNGROUNDED_EVIDENCE",
                        severity="warning",
                        message=f"Evidence quote for '{field_name}' not verbatim in source text.",
                    )
                )

    if record.doc_type in ("commercial_invoice", "customs_permit") and not record.hs_codes:
        flags.append(
            ValidationFlag(
                code="MISSING_MANDATORY_HS_CODE",
                severity="warning",
                message="Customs/Invoice document is missing a mandatory HS Code.",
            )
        )
        ref = record.reference_number.value if record.reference_number else "this document"
        return (
            "CLARIFY",
            flags,
            f"Please provide the 6-to-8 digit HS Code(s) for {ref} before customs filing can proceed.",
        )

    if record.doc_type == "bank_cheque" and not record.ifsc_code:
        flags.append(
            ValidationFlag(
                code="MISSING_IFSC",
                severity="warning",
                message="Bank cheque is missing a valid 11-character IFSC code.",
            )
        )
        return "CLARIFY", flags, "Please confirm the issuing branch 11-character IFSC code for this cheque."

    line_items = record.line_items or _extract_line_items_fallback(raw_text)
    if line_items and record.total_amount:
        calc_sum = round(sum(item.line_total for item in line_items), 2)
        declared = round(float(record.total_amount.value), 2)
        if abs(calc_sum - declared) > 0.01:
            flags.append(
                ValidationFlag(
                    code="MATH_MISMATCH",
                    severity="critical",
                    message=f"Line items sum ({calc_sum:.2f}) does not match declared total ({declared:.2f}).",
                )
            )

    if record.total_amount:
        amt = float(record.total_amount.value)
        curr = (record.currency.value if record.currency else "USD").upper()
        usd_equiv = amt / 84.0 if curr == "INR" else amt
        if usd_equiv > settings.high_value_threshold_usd:
            flags.append(
                ValidationFlag(
                    code="HIGH_VALUE_THRESHOLD",
                    severity="warning",
                    message=f"Amount ({curr} {amt:,.2f}) exceeds auto-execution limit (${settings.high_value_threshold_usd:,.0f}).",
                )
            )
        if curr == "INR" and amt > 50000:
            flags.append(
                ValidationFlag(
                    code="HIGH_VALUE_INR_CHECK",
                    severity="warning",
                    message=f"INR amount ({amt:,.2f}) requires maker-checker human approval.",
                )
            )

    confidences = [
        f.confidence
        for f in [
            record.reference_number,
            record.issuer_or_shipper,
            record.total_amount,
            record.incoterms,
            record.ifsc_code,
            *record.hs_codes,
        ]
        if f is not None
    ]
    if confidences and min(confidences) < settings.confidence_threshold:
        flags.append(
            ValidationFlag(
                code="LOW_CONFIDENCE_FIELD",
                severity="warning",
                message=f"Minimum field confidence ({min(confidences):.2f}) is below {settings.confidence_threshold:.2f}.",
            )
        )

    if any(f.severity in ("warning", "critical") for f in flags):
        return "HUMAN_APPROVAL", flags, None

    return "AUTO_EXECUTE", flags, None
