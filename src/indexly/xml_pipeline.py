from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import xml.etree.ElementTree as ET
import re
from datetime import datetime
import json
from .export_utils import safe_export
# --------------------------------------------------------------------------
# XML Helpers
# --------------------------------------------------------------------------
def _sanitize_xml_input(xml_text: str) -> str:
    if not xml_text or not isinstance(xml_text, str):
        return xml_text
    xml_text = xml_text.encode("utf-8", "ignore").decode("utf-8", "ignore")
    xml_text = re.sub(r"^[^<]+", "", xml_text, count=1).lstrip()
    xml_text = re.sub(r"<!--.*?-->", "", xml_text, flags=re.DOTALL)
    return xml_text


def _parse_xml_element(elem) -> dict:
    parsed: dict = {}
    if elem.attrib:
        for key, val in elem.attrib.items():
            parsed[f"@{key}"] = val
    text = (elem.text or "").strip()
    if text:
        parsed["#text"] = text
    for child in elem:
        tag = child.tag.split("}", 1)[-1]
        child_dict = _parse_xml_element(child)
        if tag in parsed:
            if not isinstance(parsed[tag], list):
                parsed[tag] = [parsed[tag]]
            parsed[tag].append(child_dict)
        else:
            parsed[tag] = child_dict
    return parsed


def _xml_to_records(root) -> list[dict]:
    records = []
    if isinstance(root, ET.Element):
        records.append(_parse_xml_element(root))
    else:
        for elem in root:
            records.append(_parse_xml_element(elem))
    return records


def _flatten_for_preview(obj: Any) -> dict:
    if isinstance(obj, dict):
        return {k: _flatten_for_preview(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return json.dumps([_flatten_for_preview(x) for x in obj])
    else:
        return obj


def _build_tree_view(data: Any, max_depth: int = 4, max_items: int = 2) -> str:
    lines = []

    def recurse(d, prefix="", depth=0):
        if depth > max_depth:
            lines.append(f"{prefix}└─ ...")
            return
        if isinstance(d, dict):
            keys = list(d.keys())
            for i, k in enumerate(keys):
                connector = "└─ " if i == len(keys) - 1 else "├─ "
                if isinstance(d[k], dict):
                    lines.append(f"{prefix}{connector}{k}:")
                    recurse(d[k], prefix + ("    " if i == len(keys) - 1 else "│   "), depth + 1)
                elif isinstance(d[k], list):
                    lines.append(f"{prefix}{connector}{k}: [list of {len(d[k])}]")
                    for idx, item in enumerate(d[k][:max_items]):
                        recurse(item, prefix + ("    " if i == len(keys) - 1 else "│   "), depth + 1)
                else:
                    val = str(d[k])[:60].replace("\n", " ")
                    lines.append(f"{prefix}{connector}{k}: {val}")
        elif isinstance(d, list):
            for idx, item in enumerate(d[:max_items]):
                recurse(item, prefix, depth)

    data_list = data if isinstance(data, list) else [data]
    for r in data_list[:1]:
        recurse(r)
    return "\n".join(lines)


def _infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    inferred = {}
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(10).tolist()
        if not sample:
            inferred[col] = "unknown"
            continue
        if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in sample):
            inferred[col] = "date"
        elif all(re.fullmatch(r"\d+(\.\d+)?", v) for v in sample):
            inferred[col] = "numeric"
        elif all(re.fullmatch(r"(?i)(true|false|yes|no)", v) for v in sample):
            inferred[col] = "boolean"
        elif re.search(r"id$", col.lower()):
            inferred[col] = "identifier"
        else:
            inferred[col] = "text"
    return inferred


# --------------------------------------------------------------------------
# Markdown Invoice Generator
# --------------------------------------------------------------------------
def _generate_invoice_md(invoice_data: dict) -> str:
    """Generate a formatted Markdown invoice summary."""
    lines = [f"# 🧾 Invoice Summary — {invoice_data.get('Invoice ID', 'Unknown')}"]

    # Header table
    header_fields = [
        "Invoice ID", "Issue Date", "Seller", "Buyer",
        "Seller Email", "Buyer Email", "IBAN", "BIC", "Currency"
    ]
    lines.append("\n| Field | Value |")
    lines.append("|-------|--------|")
    for key in header_fields:
        val = invoice_data.get(key, "")
        lines.append(f"| **{key}** | {val} |")

    # Line Items table
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
            except ValueError:
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
        if file_path and raw is None:
            with open(file_path, "r", encoding="utf-8") as f:
                xml_text = _sanitize_xml_input(f.read())
            root = ET.fromstring(xml_text)
            raw = _xml_to_records(root)

        if raw is None:
            return None, {"error": "No XML data provided"}, {"rows": 0, "cols": 0}

        root_rec = raw[0] if isinstance(raw, list) else raw
        invoice_data = {}
        invoice_format = "Unknown"

        def _get_recursive(d: dict, keys: list[str], default=""):
            for key in keys:
                if key in d:
                    d = d[key]
                else:
                    return default
            if isinstance(d, dict) and "#text" in d:
                return d["#text"]
            return d if isinstance(d, str) else default

        # Detect invoice type
        doc_id = _get_recursive(root_rec, ["ExchangedDocument", "ID", "#text"]) or \
                 _get_recursive(root_rec, ["CrossIndustryInvoice", "ExchangedDocument", "ID", "#text"])

        # ------------------------- INVOICE PARSING -------------------------
        if doc_id:
            invoice_format = doc_id
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
            invoice_rows = []
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
                row = {**{k: invoice_data.get(k, "") for k in ["Invoice ID", "Issue Date", "Seller", "Buyer", "Currency"]}, **line}
                invoice_rows.append(row)
            df_preview = pd.DataFrame(invoice_rows) if invoice_rows else pd.DataFrame()

            # Generate Markdown Invoice
            md_invoice = _generate_invoice_md(invoice_data)

        # --------------------- NON-INVOICE HANDLING ------------------------
        else:
            md_invoice = ""
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
            else:
                preview_list = [_flatten_for_preview(r) for r in raw] if isinstance(raw, list) else [_flatten_for_preview(raw)]
                df_preview = pd.json_normalize(preview_list) if preview_list else pd.DataFrame()

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
            "tree": _build_tree_view(raw),
        }

        return df_preview if not df_preview.empty else None, summary, metadata

    except Exception as e:
        return None, {"error": str(e)}, {"rows": 0, "cols": 0}
