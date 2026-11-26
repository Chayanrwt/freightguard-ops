from sqlmodel import Session, select
from app.knowledge.rag_store import seed_tenant_rules
from app.knowledge.sql_store import ShipmentMaster, engine, init_db


def main() -> None:
    init_db()
    seed_tenant_rules()

    sample_shipments = [
        ShipmentMaster(
            tenant_id="tenant_freight",
            shipment_ref="SHP-INNSA-001",
            shipper_name="Apex Precision Components Pvt Ltd",
            origin_port="INNSA",
            destination_port="DEHAM",
            kyc_verified=True,
        ),
        ShipmentMaster(
            tenant_id="tenant_freight",
            shipment_ref="SHP-INMUN-002",
            shipper_name="Bharat Agro Exports Ltd",
            origin_port="INMUN",
            destination_port="AEJEA",
            kyc_verified=True,
        ),
        ShipmentMaster(
            tenant_id="tenant_bank",
            shipment_ref="ACCT-PNB-889",
            shipper_name="Sharma Logistics Pvt Ltd",
            origin_port="N/A",
            destination_port="N/A",
            kyc_verified=True,
        ),
    ]

    with Session(engine) as session:
        for item in sample_shipments:
            exists = session.exec(
                select(ShipmentMaster).where(ShipmentMaster.shipment_ref == item.shipment_ref)
            ).first()
            if not exists:
                session.add(item)
        session.commit()

    print("Seeded SQLite master records and ChromaDB tenant SOPs successfully.")


if __name__ == "__main__":
    main()
