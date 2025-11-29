from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
from .analyze_xml import (
    _sanitize_xml_input,
    _xml_to_records,
    _flatten_for_preview,
    _build_tree_view,
    _infer_column_types,
    summarize_generic_xml,
)

# --------------------------------------------------------------------------
# Markdown Invoice Generator (unchanged)
# --------------------------------------------------------------------------
def _generate_invoice_md(invoice_data: dict) -> str:
    lines = [f"# 🧾 Invoice Summary — {invoice_data.get('Invoice ID', 'Unknown')}"]
    header_fields = [
        "Invoice ID", "Issue Date", "Seller", "Buyer",
        "Seller Email", "Buyer Email", "IBAN", "BIC", "Currency"
    ]
    lines.append("\n| Field | Value |")
    lines.append("|-------|--------|")
    for key in header_fields:
        val = invoice_data.get(key, "")
        lines.append(f"| **{key}** | {val} |")
    items = invoice_data.get("Line Items", [])
    if items:
        lines.append("\n## 📦 Line Items\n")
        lines.append("| LineID | Product | Qty | Net € | Gross € | VAT % |")
        lines.append("|:------:|----------|----:|------:|--------:|------:|")
        subtotal = vat_total = 0.0
        for i in items:
            try:
                qty = float(i.get("Quantity", 0))
                net = float(i.get("Net Price", 0))
                vat = float(i.get("VAT %", 0))
            except Exception:
                qty = net = vat = 0.0
            subtotal += qty * net
            vat_total += qty * net * (vat / 100)
            lines.append(
                f"| {i.get('LineID','')} | {i.get('Product','')} | {qty:.2f} | {net:.2f} | {float(i.get('Gross Price',0)):.2f} | {vat:.2f} |"
            )
        grand_declared = float(invoice_data.get("Grand Total", 0) or 0)
        grand_calc = subtotal + vat_total
        check = "✅ OK" if abs(grand_declared - grand_calc) < 1 else f"⚠️ Diff {grand_declared - grand_calc:.2f}"
        lines.append("\n### 💰 Summary Totals\n")
        lines.append("| Metric | Value (€) |")
        lines.append("|---------|-----------:|")
        lines.append(f"| **Subtotal (Net)** | {subtotal:.2f} |")
        lines.append(f"| **VAT Total (Approx)** | {vat_total:.2f} |")
        lines.append(f"| **Grand Total (Given)** | {grand_declared:.2f} |")
        lines.append(f"| **Discrepancy Check** | {check} |")
    lines.append(f"\n🕓 *Generated at:* {datetime.utcnow().isoformat()}Z\n")
    return "\n".join(lines)

# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
def run_xml_pipeline(
    *,
    file_path: Optional[Path] = None,
    raw: Optional[Any] = None,
    df_preview: Optional[pd.DataFrame] = None,
    args: Optional[Any] = None
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], Dict[str, Any]]:
    try:
        xml_text = None
        if file_path and raw is None:
            xml_text = _sanitize_xml_input(Path(file_path).read_text(encoding="utf-8", errors="ignore"))
            root = ET.fromstring(xml_text)
            raw = _xml_to_records(root)

        if raw is None:
            return None, {"error": "No XML data provided"}, {"rows": 0, "cols": 0}

        # data shapes
        root_rec = raw[0] if isinstance(raw, list) else raw

        def _safe_text(elem: Optional[ET.Element]) -> str:
            return elem.text.strip() if elem is not None and elem.text and elem.text.strip() else ""

        # ------------------------- Invoice extractors (kept backward-compatible) -------------------------
        def _get_recursive(d: dict, keys: List[str], default=""):
            for key in keys:
                if isinstance(d, dict) and key in d:
                    d = d[key]
                else:
                    return default
            if isinstance(d, dict) and "#text" in d:
                return d["#text"]
            return d if isinstance(d, str) else default

        def extract_invoice_from_raw(root_rec: dict) -> Dict[str, Any]:
            invoice_data = {}
            doc_id = _get_recursive(root_rec, ["ExchangedDocument", "ID", "#text"]) or \
                     _get_recursive(root_rec, ["CrossIndustryInvoice", "ExchangedDocument", "ID", "#text"])
            if not doc_id:
                return {}
            invoice_data["Invoice ID"] = doc_id
            invoice_data["Issue Date"] = _get_recursive(root_rec, ["ExchangedDocument", "IssueDateTime", "DateTimeString", "#text"]) or \
                                        _get_recursive(root_rec, ["CrossIndustryInvoice", "ExchangedDocument", "IssueDateTime", "DateTimeString", "#text"])
            invoice_data["Seller"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeAgreement", "SellerTradeParty", "Name", "#text"])
            invoice_data["Buyer"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeAgreement", "BuyerTradeParty", "Name", "#text"])
            invoice_data["Seller Email"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeAgreement", "SellerTradeParty", "DefinedTradeContact", "EmailURIUniversalCommunication", "URIID", "#text"])
            invoice_data["Buyer Email"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeAgreement", "BuyerTradeParty", "DefinedTradeContact", "EmailURIUniversalCommunication", "URIID", "#text"])
            invoice_data["IBAN"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement", "SpecifiedTradeSettlementPaymentMeans", "PayeePartyCreditorFinancialAccount", "IBANID", "#text"])
            invoice_data["BIC"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement", "SpecifiedTradeSettlementPaymentMeans", "PayeeSpecifiedCreditorFinancialInstitution", "BICID", "#text"])
            invoice_data["Currency"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement", "InvoiceCurrencyCode", "#text"], "EUR")
            invoice_data["Grand Total"] = _get_recursive(root_rec, ["SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement", "SpecifiedTradeSettlementHeaderMonetarySummation", "GrandTotalAmount", "#text"])
            items_raw = root_rec.get("SupplyChainTradeTransaction", {}).get("IncludedSupplyChainTradeLineItem", [])
            if not isinstance(items_raw, list):
                items_raw = [items_raw]
            invoice_data["Line Items"] = []
            for item in items_raw:
                line = {
                    "LineID": _get_recursive(item, ["AssociatedDocumentLineDocument", "LineID", "#text"]),
                    "Product": _get_recursive(item, ["SpecifiedTradeProduct", "Name", "#text"]),
                    "Quantity": _get_recursive(item, ["SpecifiedLineTradeDelivery", "BilledQuantity", "#text"], "0"),
                    "Net Price": _get_recursive(item, ["SpecifiedLineTradeAgreement", "NetPriceProductTradePrice", "ChargeAmount", "#text"], "0"),
                    "Gross Price": _get_recursive(item, ["SpecifiedLineTradeAgreement", "GrossPriceProductTradePrice", "ChargeAmount", "#text"], "0"),
                    "VAT %": _get_recursive(item, ["SpecifiedLineTradeSettlement", "ApplicableTradeTax", "RateApplicablePercent", "#text"], "0")
                }
                invoice_data["Line Items"].append(line)
            return invoice_data

        def extract_invoice_from_etree(root_el: ET.Element) -> Dict[str, Any]:
            ns = {
                "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            }
            invoice_data: Dict[str, Any] = {}
            invoice_id = _safe_text(root_el.find(".//cbc:ID", ns))
            if not invoice_id:
                return {}
            invoice_data["Invoice ID"] = invoice_id
            invoice_data["Issue Date"] = _safe_text(root_el.find(".//cbc:IssueDate", ns))
            seller_name = _safe_text(root_el.find(".//cac:AccountingSupplierParty//cbc:Name", ns)) or _safe_text(root_el.find(".//cac:AccountingSupplierParty//cac:Party/cbc:Name", ns))
            buyer_name = _safe_text(root_el.find(".//cac:AccountingCustomerParty//cbc:Name", ns)) or _safe_text(root_el.find(".//cac:AccountingCustomerParty//cac:Party/cbc:Name", ns))
            invoice_data["Seller"] = seller_name
            invoice_data["Buyer"] = buyer_name
            seller_email = _safe_text(root_el.find(".//cac:AccountingSupplierParty//cbc:ElectronicMail", ns)) or _safe_text(root_el.find(".//cac:AccountingSupplierParty//cac:Contact/cbc:ElectronicMail", ns))
            buyer_email = _safe_text(root_el.find(".//cac:AccountingCustomerParty//cbc:ElectronicMail", ns)) or _safe_text(root_el.find(".//cac:AccountingCustomerParty//cac:Contact/cbc:ElectronicMail", ns))
            invoice_data["Seller Email"] = seller_email
            invoice_data["Buyer Email"] = buyer_email
            iban = _safe_text(root_el.find(".//cac:PayeeFinancialAccount/cbc:ID", ns)) or _safe_text(root_el.find(".//cac:PayeeFinancialAccount//cbc:IBAN", ns))
            bic = _safe_text(root_el.find(".//cac:PayeeFinancialAccount//cac:FinancialInstitutionBranch/cbc:ID", ns))
            invoice_data["IBAN"] = iban
            invoice_data["BIC"] = bic
            currency = _safe_text(root_el.find(".//cbc:DocumentCurrencyCode", ns)) or "EUR"
            invoice_data["Currency"] = currency
            grand = _safe_text(root_el.find(".//cac:LegalMonetaryTotal/cbc:PayableAmount", ns)) or _safe_text(root_el.find(".//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount", ns)) or _safe_text(root_el.find(".//cbc:PayableAmount", ns))
            invoice_data["Grand Total"] = grand
            invoice_data["Line Items"] = []
            for idx, line_el in enumerate(root_el.findall(".//cac:InvoiceLine", ns), start=1):
                line_id = _safe_text(line_el.find("./cbc:ID", ns)) or str(idx)
                qty = _safe_text(line_el.find(".//cbc:InvoicedQuantity", ns)) or "0"
                prod = _safe_text(line_el.find(".//cac:Item/cbc:Name", ns)) or _safe_text(line_el.find(".//cac:Item//cac:BuyersItemIdentification/cbc:ID", ns)) or _safe_text(line_el.find(".//cac:Item//cac:SellersItemIdentification/cbc:ID", ns))
                net_price = _safe_text(line_el.find(".//cac:Price/cbc:PriceAmount", ns)) or _safe_text(line_el.find(".//cbc:LineExtensionAmount", ns)) or "0"
                gross_price = _safe_text(line_el.find(".//cbc:LineExtensionAmount", ns)) or net_price
                vat_pct = _safe_text(line_el.find(".//cac:ClassifiedTaxCategory/cbc:Percent", ns)) or _safe_text(line_el.find(".//cac:ClassifiedTaxCategory//cbc:Percent", ns)) or "0"
                invoice_data["Line Items"].append({
                    "LineID": line_id,
                    "Product": prod,
                    "Quantity": qty,
                    "Net Price": net_price,
                    "Gross Price": gross_price,
                    "VAT %": vat_pct,
                })
            return invoice_data

        # Flat EN16931 extractor (kept minimal here; your existing implementation can be plugged)
        def _extract_flat_en16931(root_el: ET.Element) -> Dict[str, Any]:
            # minimal safe check for flat EN16931 namespace + InvoiceNumber
            ns = {"x": "urn:cen.eu:en16931:2017"}
            invoice_id = _safe_text(root_el.find(".//x:InvoiceNumber", ns))
            if not invoice_id:
                return {}
            # simple extraction (you can replace with your enhanced variant)
            return {
                "Invoice ID": invoice_id,
                "Issue Date": _safe_text(root_el.find(".//x:IssueDate", ns)),
                "Seller": _safe_text(root_el.find(".//x:Seller/x:Name", ns)),
                "Buyer": _safe_text(root_el.find(".//x:Buyer/x:Name", ns)),
                "Currency": _safe_text(root_el.find(".//x:Currency", ns)) or "EUR",
                "Grand Total": _safe_text(root_el.find(".//x:TotalAmount", ns)),
                "Line Items": [
                    {
                        "LineID": str(i+1),
                        "Product": _safe_text(li.find("x:ItemName", ns)),
                        "Quantity": _safe_text(li.find("x:Quantity", ns)) or "0",
                        "Net Price": _safe_text(li.find("x:UnitPrice", ns)) or "0",
                        "Gross Price": _safe_text(li.find("x:LineTotal", ns)) or _safe_text(li.find("x:UnitPrice", ns)) or "0",
                        "VAT %": _safe_text(li.find("x:TaxCategory", ns)) or "0"
                    } for i, li in enumerate(root_el.findall(".//x:LineItem", ns))
                ]
            }

        # ----------------------------------------------------------------------
        # unified invoice detection (CII -> UBL -> EN16931)
        # ----------------------------------------------------------------------
        def unified_extract_invoice(root_el: ET.Element, root_rec: dict) -> Tuple[Dict[str, Any], str]:
            invoice_data = {}
            invoice_format = "Unknown"
            if root_rec:
                invoice_data = extract_invoice_from_raw(root_rec) or {}
                if invoice_data:
                    invoice_format = "CII"
            if (not invoice_data) and root_el is not None:
                invoice_data = extract_invoice_from_etree(root_el) or {}
                if invoice_data:
                    invoice_format = "UBL"
            if (not invoice_data) and root_el is not None:
                invoice_data = _extract_flat_en16931(root_el) or {}
                if invoice_data:
                    invoice_format = "EN16931"
            if invoice_data and invoice_data.get("Invoice ID") and invoice_format == "Unknown":
                invoice_format = "Detected"
            return invoice_data, invoice_format

        # ------------------------- INVOICE EXTRACTION -------------------------
        invoice_data, invoice_format = unified_extract_invoice(root, root_rec)
        md_invoice = _generate_invoice_md(invoice_data) if invoice_data else ""

        # ------------------------- PREVIEW DATAFRAME -------------------------
        tree_str = ""
        if invoice_data.get("Line Items"):
            invoice_rows = [
                {**{k: invoice_data.get(k, "") for k in ["Invoice ID", "Issue Date", "Seller", "Buyer", "Currency"]}, **line}
                for line in invoice_data["Line Items"]
            ]
            df_preview = pd.DataFrame(invoice_rows)
            tree_str = _build_tree_view(invoice_rows)
        else:
            # ------------------------- GENERIC XML -------------------------
            def find_repeating_nodes(data):
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 1 and all(isinstance(i, dict) for i in v):
                            return v
                        result = find_repeating_nodes(v)
                        if result:
                            return result
                return None

            repeating_nodes = find_repeating_nodes(root_rec)
            if repeating_nodes:
                df_preview = pd.json_normalize(repeating_nodes)
                md_invoice = f"**Generic XML Preview:** {len(df_preview)} rows, {len(df_preview.columns)} columns."
                tree_str = _build_tree_view(repeating_nodes)
                invoice_format = "Generic XML"
                invoice_data = {}
            else:
                # Fallback to full generic XML summarizer
                summary_dict, tree_str, df_preview_full = summarize_generic_xml(
                    file_path=str(file_path) if file_path else "",
                    xml_text=xml_text,
                    show_tree=True
                )
                # ensure df_preview is a DataFrame
                df_preview = df_preview_full if isinstance(df_preview_full, pd.DataFrame) else pd.DataFrame()
                md_invoice = f"**Generic XML Summary:** {summary_dict.get('total_records', 0)} records, top-level tags: {summary_dict.get('top_level_tags', [])}"
                invoice_format = "Generic XML"
                invoice_data = {}

        # --------------------- METADATA + SUMMARY --------------------------
        if df_preview is None:
            df_preview = pd.DataFrame()

        inferred_types = _infer_column_types(df_preview)
        metadata = {
            "loaded_at": datetime.utcnow().isoformat() + "Z",
            "rows": len(df_preview),
            "cols": len(df_preview.columns),
            "file_type": "xml",
            "inferred_types": inferred_types,
        }

        db_dict = {
            "raw_json": raw,
            "preview_columns": df_preview.columns.tolist() if not df_preview.empty else [],
            "num_rows": metadata["rows"],
            "num_cols": metadata["cols"],
            "loaded_at": metadata["loaded_at"],
            "column_types": inferred_types,
            "invoice_data": invoice_data,
            "invoice_format": invoice_format
        }

        summary = {
            "md": md_invoice or "No Markdown invoice generated.",
            "metadata": metadata,
            "db_ready": db_dict,
            "tree": tree_str if tree_str else _build_tree_view(raw),
        }

        return df_preview if not df_preview.empty else None, summary, metadata

    except Exception as e:
        return None, {"error": str(e)}, {"rows": 0, "cols": 0}
