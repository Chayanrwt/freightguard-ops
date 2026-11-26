import re
from app.schemas import ValidationFlag

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+override",
    r"set\s+status\s*=\s*auto_execute",
    r"bypass\s+(human\s+)?approval",
    r"reveal\s+(your\s+)?system\s+prompt",
    r"<\s*/?\s*system\s*>",
]


def inspect_untrusted_text(raw_text: str) -> tuple[str, list[ValidationFlag]]:
    """
    Treats all OCR/PDF text as untrusted data.
    Detects prompt injection attempts and neutralizes control-like tags before LLM exposure.
    """
    flags: list[ValidationFlag] = []
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            flags.append(
                ValidationFlag(
                    code="PROMPT_INJECTION_DETECTED",
                    severity="critical",
                    message=f"Adversarial instruction pattern detected in document: '{match.group(0)}'",
                )
            )
            break

    sanitized = re.sub(
        r"<\s*/?\s*(system|assistant|tool_call)\s*>",
        "[REDACTED_TAG]",
        raw_text,
        flags=re.IGNORECASE,
    )
    return sanitized, flags
