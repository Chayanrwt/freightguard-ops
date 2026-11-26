import hashlib
import json
import re
import sqlite3
from pathlib import Path
import numpy as np

DB_PATH = Path("data/freightguard.db")
DIM = 256


def _embed_text(text: str) -> np.ndarray:
    """Deterministic 256-d L2-normalized dense embedding over word & trigram features."""
    vec = np.zeros(DIM, dtype=np.float32)
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    features = list(tokens)
    for tok in tokens:
        if len(tok) >= 3:
            features.extend(tok[i : i + 3] for i in range(len(tok) - 2))
    for feat in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(digest, "little") % DIM
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def _ensure_table() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_sop_vectors (
            doc_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def seed_tenant_rules() -> None:
    docs = [
        (
            "freight_rule_1",
            "tenant_freight",
            "SOP-FR-01: Any commercial invoice or customs permit above USD 10,000 requires Senior Customs Broker approval before CargoWise XML dispatch.",
        ),
        (
            "freight_rule_2",
            "tenant_freight",
            "SOP-FR-02: All commercial invoices and customs import permits must contain a valid 6-to-8 digit HS Code. Missing HS Codes must trigger a CLARIFY request to the shipper.",
        ),
        (
            "freight_rule_3",
            "tenant_freight",
            "SOP-FR-03: Line item totals must reconcile exactly with the declared invoice total before generating Logi-sys job records.",
        ),
        (
            "bank_rule_1",
            "tenant_bank",
            "SOP-BK-01: Bank cheques must include a valid 11-character Indian IFSC code and payee name. Cheques above INR 50,000 require maker-checker human sign-off.",
        ),
    ]
    conn = _ensure_table()
    for doc_id, tenant_id, content in docs:
        emb = json.dumps(_embed_text(content).tolist())
        conn.execute(
            """
            INSERT INTO tenant_sop_vectors (doc_id, tenant_id, content, embedding_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                tenant_id=excluded.tenant_id,
                content=excluded.content,
                embedding_json=excluded.embedding_json
            """,
            (doc_id, tenant_id, content, emb),
        )
    conn.commit()
    conn.close()


def retrieve_tenant_rules(tenant_id: str, query: str, top_k: int = 2) -> list[str]:
    """Retrieves approved SOPs strictly filtered by tenant_id using cosine similarity."""
    conn = _ensure_table()
    rows = conn.execute(
        "SELECT content, embedding_json FROM tenant_sop_vectors WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchall()
    conn.close()

    if not rows:
        seed_tenant_rules()
        conn = _ensure_table()
        rows = conn.execute(
            "SELECT content, embedding_json FROM tenant_sop_vectors WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()
        conn.close()

    q_vec = _embed_text(query)
    scored: list[tuple[float, str]] = []
    for content, emb_json in rows:
        d_vec = np.array(json.loads(emb_json), dtype=np.float32)
        score = float(np.dot(q_vec, d_vec))
        scored.append((score, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [content for _, content in scored[:top_k]]
