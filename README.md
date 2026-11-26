# FreightGuard Ops — Deterministic-First Compliance & Document AI

A multi-tenant document intelligence and compliance automation platform built for **Global Freight Forwarding** and **Banking/Institutional Operations**. It ingests PDFs and noisy scans, extracts evidence-grounded records, enforces deterministic policy guardrails, and dispatches validated payloads to **CargoWise eAdaptor (XML)** and **Logi-sys (JSON)**—or routes exceptions to a **Human-in-the-Loop (HITL)** console.

## Architecture ("Agent Proposes, Platform Validates")

```mermaid
flowchart TD
    A[Document Intake] --> B[PyMuPDF / Vision OCR]
    B --> C[Prompt-Injection Guard]
    C --> D[Deterministic Regex Extractor]
    D --> E{Missing Fields?}
    E -- No --> G[Tenant SQL + Vector SOPs]
    E -- Yes --> F[Tiered Gateway: Groq -> Gemini]
    F --> G
    G --> H[Server-Side Policy Engine]
    H --> I[AUTO_EXECUTE / HITL / QUARANTINED]

cat << 'EOF' >> README.md

## Architecture ("Agent Proposes, Platform Validates")

```mermaid
flowchart TD
    A[Document Intake] --> B[PyMuPDF / Vision OCR]
    B --> C[Prompt-Injection Guard]
    C --> D[Deterministic Regex Extractor]
    D --> E{Missing Fields?}
    E -- No --> G[Tenant SQL + Vector SOPs]
    E -- Yes --> F[Tiered Gateway: Groq -> Gemini]
    F --> G
    G --> H[Server-Side Policy Engine]
    H --> I[AUTO_EXECUTE / HITL / QUARANTINED]


