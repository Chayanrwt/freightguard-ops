from app.knowledge.rag_store import retrieve_tenant_rules, seed_tenant_rules
from app.knowledge.sql_store import init_db, lookup_shipper_records
from scripts.seed_data import main as seed_all


def test_tenant_isolation_rag_and_sql():
    init_db()
    seed_tenant_rules()
    seed_all()

    freight_rules = retrieve_tenant_rules("tenant_freight", "IFSC cheque approval", top_k=3)
    assert all("IFSC" not in r for r in freight_rules)

    bank_rules = retrieve_tenant_rules("tenant_bank", "CargoWise customs HS code", top_k=3)
    assert all("CargoWise" not in r for r in bank_rules)

    freight_shipments = lookup_shipper_records("tenant_freight", "Sharma Logistics")
    assert freight_shipments == []
