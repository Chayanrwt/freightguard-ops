import xml.etree.ElementTree as ET
from app.schemas import ExtractedDocumentRecord

UNLOCODE_MAP = {
    "nhava sheva": "INNSA",
    "mumbai": "INBOM",
    "mundra": "INMUN",
    "chennai": "INMAA",
    "hamburg": "DEHAM",
    "rotterdam": "NLRTM",
    "los angeles": "USLAX",
    "jebel ali": "AEJEA",
    "singapore": "SGSIN",
}


def normalize_unlocode(raw_port: str | None) -> str:
    if not raw_port:
        return "UNKNW"
    cleaned = raw_port.strip()
    if len(cleaned) == 5 and cleaned.isalpha():
        return cleaned.upper()
    return UNLOCODE_MAP.get(cleaned.lower(), cleaned[:5].upper())


def build_cargowise_xml(record: ExtractedDocumentRecord) -> str:
    """Generates CargoWise eAdaptor UniversalShipment XML payload."""
    root = ET.Element("UniversalInterchange", Version="1.1")
    header = ET.SubElement(root, "Header")
    ET.SubElement(header, "SenderID").text = "FREIGHTGUARD_OPS"
    ET.SubElement(header, "RecipientID").text = "CARGOWISE_EADAPTOR"

    body = ET.SubElement(root, "Body")
    shipment = ET.SubElement(body, "UniversalShipment")
    ctx = ET.SubElement(shipment, "DataContext")
    ET.SubElement(ctx, "DataTargetType").text = "ForwardingShipment"
    ET.SubElement(ctx, "Company").text = record.tenant_id.upper()

    sub = ET.SubElement(shipment, "Shipment")
    ET.SubElement(sub, "WayBillNumber").text = str(record.reference_number.value) if record.reference_number else "PENDING"
    ET.SubElement(sub, "ShipmentIncoTerm").text = str(record.incoterms.value) if record.incoterms else "FOB"
    ET.SubElement(sub, "PortOfLoading").text = normalize_unlocode(record.origin_port.value if record.origin_port else None)
    ET.SubElement(sub, "PortOfDischarge").text = normalize_unlocode(record.destination_port.value if record.destination_port else None)

    if record.total_amount:
        ET.SubElement(sub, "GoodsValue").text = f"{float(record.total_amount.value):.2f}"
        ET.SubElement(sub, "GoodsValueCurrency").text = str(record.currency.value) if record.currency else "USD"

    if record.hs_codes:
        ET.SubElement(sub, "HarmonisedCode").text = str(record.hs_codes[0].value)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")
