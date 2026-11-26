# FreightGuard Ops — Deterministic-First Document & Compliance AI

Production-oriented multi-tenant document operations platform built for compliance-heavy workflows (**Global Freight Forwarding** and **Banking/Institutional Ops**).

## Quickstart
```bash
# 1. Start FastAPI backend
uvicorn app.main:app --reload --port 8000

# 2. Start Streamlit Operator Console (in a second terminal)
streamlit run ui/dashboard.py

# 3. Run unit tests & golden dataset evaluation
pytest -v
python -m evals.run_evals

