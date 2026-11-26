import json
from pathlib import Path
import httpx
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="FreightGuard Ops Console", layout="wide")
st.title("FreightGuard Ops — Deterministic-First Compliance & Document AI")
st.caption("Multi-Tenant Document Intake • Evidence-Backed Extraction • Policy Guardrails • CargoWise & Logi-sys Dispatch")

tab_intake, tab_hitl, tab_evals = st.tabs(
    ["1. Document Intake & Trace", "2. Human Approval Queue (HITL)", "3. Ops Metrics & Golden Evals"]
)

with tab_intake:
    col_left, col_right = st.columns([1, 1.4])
    with col_left:
        st.subheader("Submit Document")
        tenant_id = st.selectbox("Client Tenant", ["tenant_freight", "tenant_bank"])
        source_mode = st.radio("Source", ["Pick from sample_docs/", "Upload new file"], horizontal=True)

        selected_bytes = None
        selected_name = None

        if source_mode == "Pick from sample_docs/":
            samples = sorted(Path("sample_docs").glob("*"))
            if samples:
                chosen = st.selectbox("Sample Document", samples, format_func=lambda p: p.name)
                selected_bytes = chosen.read_bytes()
                selected_name = chosen.name
        else:
            uploaded = st.file_uploader("Upload PDF or Image", type=["pdf", "png", "jpg", "jpeg"])
            if uploaded:
                selected_bytes = uploaded.getvalue()
                selected_name = uploaded.name

        if st.button("Run Agentic Pipeline", type="primary", disabled=selected_bytes is None):
            with st.spinner("Running OCR -> Security Guard -> Deterministic Rules -> Model Gateway -> Policy Engine..."):
                resp = httpx.post(
                    f"{API_BASE}/api/process",
                    files={"file": (selected_name, selected_bytes)},
                    data={"tenant_id": tenant_id},
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    st.session_state["last_result"] = resp.json()
                else:
                    st.error(f"API Error {resp.status_code}: {resp.text}")

    with col_right:
        res = st.session_state.get("last_result")
        if res:
            action = res["route_action"]
            badge_color = {
                "AUTO_EXECUTE": "green",
                "CLARIFY": "orange",
                "HUMAN_APPROVAL": "orange",
                "QUARANTINED": "red",
            }.get(action, "blue")
            st.markdown(f"### Routing Decision: :{badge_color}[**{action}**]")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("OCR Engine", res["ocr_engine_used"])
            m2.metric("LLM Calls", res["llm_calls_made"])
            m3.metric("Latency", f"{res['total_latency_ms']:.0f} ms")
            m4.metric("Est. Cost", f"${res['estimated_cost_usd']:.5f}")

            if res.get("clarification_question"):
                st.warning(f"**Clarification Question:** {res['clarification_question']}")

            if res.get("flags"):
                st.subheader("Validation & Security Flags")
                for flg in res["flags"]:
                    st.error(f"**[{flg['code']}]** ({flg['severity']}): {flg['message']}")

            st.subheader("Evidence-Backed Structured Extraction")
            rec = res["record"]
            evidence_rows = []
            for key in (
                "reference_number",
                "issuer_or_shipper",
                "consignee_or_payee",
                "document_date",
                "currency",
                "total_amount",
                "origin_port",
                "destination_port",
                "incoterms",
                "ifsc_code",
            ):
                val_obj = rec.get(key)
                if val_obj:
                    evidence_rows.append(
                        {
                            "Field": key,
                            "Value": str(val_obj["value"]),
                            "Confidence": f"{val_obj['confidence']:.2f}",
                            "Method": val_obj["extraction_method"],
                            "Verbatim Evidence Quote": val_obj["evidence_quote"],
                        }
                    )
            for idx, hs in enumerate(rec.get("hs_codes", []), start=1):
                evidence_rows.append(
                    {
                        "Field": f"hs_code_{idx}",
                        "Value": str(hs["value"]),
                        "Confidence": f"{hs['confidence']:.2f}",
                        "Method": hs["extraction_method"],
                        "Verbatim Evidence Quote": hs["evidence_quote"],
                    }
                )
            st.dataframe(evidence_rows, use_container_width=True)

            with st.expander("LangGraph Execution Trace", expanded=True):
                for step in res.get("execution_trace", []):
                    st.write(step)

            if res.get("erp_payload"):
                with st.expander("Generated ERP Output (CargoWise XML & Logi-sys JSON)", expanded=True):
                    if isinstance(res["erp_payload"], dict) and "cargowise_xml" in res["erp_payload"]:
                        st.markdown("**CargoWise eAdaptor UniversalShipment XML**")
                        st.code(res["erp_payload"]["cargowise_xml"], language="xml")
                        st.markdown("**Logi-sys Job Intake JSON**")
                        st.json(res["erp_payload"]["logisys_job"])
                    else:
                        st.json(res["erp_payload"])

with tab_hitl:
    st.subheader("Operator Review & Correction Queue")
    if st.button("Refresh Queue"):
        st.rerun()

    docs_resp = httpx.get(f"{API_BASE}/api/documents", timeout=10.0)
    all_docs = docs_resp.json() if docs_resp.status_code == 200 else []
    pending_docs = [d for d in all_docs if d["reviewer_status"] == "PENDING"]

    if not pending_docs:
        st.info("No pending items in the HITL queue. Submit a math-error, high-value, or missing-HS document in Tab 1.")
    else:
        for doc in pending_docs:
            with st.expander(
                f"{doc['doc_id']} | {doc['file_name']} | Tenant: {doc['tenant_id']} | Route: {doc['route_action']}",
                expanded=True,
            ):
                flags = json.loads(doc["flags_json"])
                for f in flags:
                    st.warning(f"[{f['code']}] {f['message']}")

                rec = json.loads(doc["record_json"])
                c1, c2, c3 = st.columns(3)
                new_ref = c1.text_input(
                    "Reference Number",
                    value=str(rec["reference_number"]["value"]) if rec.get("reference_number") else "",
                    key=f"ref_{doc['doc_id']}",
                )
                new_amt = c2.number_input(
                    "Total Amount",
                    value=float(rec["total_amount"]["value"]) if rec.get("total_amount") else 0.0,
                    key=f"amt_{doc['doc_id']}",
                )
                existing_hs = rec["hs_codes"][0]["value"] if rec.get("hs_codes") else ""
                new_hs = c3.text_input(
                    "Primary HS Code",
                    value=str(existing_hs),
                    key=f"hs_{doc['doc_id']}",
                )
                notes = st.text_input("Reviewer Audit Note", key=f"note_{doc['doc_id']}")

                if st.button("Approve & Dispatch to CargoWise / Logi-sys", key=f"btn_{doc['doc_id']}", type="primary"):
                    if rec.get("reference_number"):
                        rec["reference_number"]["value"] = new_ref
                    if rec.get("total_amount"):
                        rec["total_amount"]["value"] = new_amt
                    if new_hs:
                        rec["hs_codes"] = [
                            {
                                "value": new_hs,
                                "confidence": 1.0,
                                "extraction_method": "deterministic_rule",
                                "source_file": doc["file_name"],
                                "source_page": 1,
                                "evidence_quote": f"Operator verified HS Code: {new_hs}",
                            }
                        ]
                    app_resp = httpx.post(
                        f"{API_BASE}/api/documents/{doc['doc_id']}/approve",
                        json={"corrected_record": rec, "reviewer_notes": notes},
                        timeout=15.0,
                    )
                    if app_resp.status_code == 200:
                        st.success(f"Approved {doc['doc_id']} and logged correction to Golden Eval feedback table!")
                        st.code(app_resp.json()["erp_payload"], language="json")

with tab_evals:
    st.subheader("Live Platform Metrics")
    m_resp = httpx.get(f"{API_BASE}/api/metrics", timeout=10.0)
    if m_resp.status_code == 200:
        m = m_resp.json()
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Processed", m["total_processed"])
        k2.metric("Auto-Executed", m["auto_executed"])
        k3.metric("Pending HITL", m["human_review_queue"])
        k4.metric("Quarantined", m["quarantined"])
        k5.metric("Avg Latency", f"{m['avg_latency_ms']} ms")

    st.subheader("Processed Audit History")
    docs_resp = httpx.get(f"{API_BASE}/api/documents", timeout=10.0)
    if docs_resp.status_code == 200 and docs_resp.json():
        st.dataframe(
            [
                {
                    "Doc ID": d["doc_id"],
                    "Tenant": d["tenant_id"],
                    "File": d["file_name"],
                    "Type": d["doc_type"],
                    "OCR": d["ocr_engine_used"],
                    "LLM Calls": d["llm_calls_made"],
                    "Route": d["route_action"],
                    "Status": d["reviewer_status"],
                }
                for d in docs_resp.json()
            ],
            use_container_width=True,
        )
