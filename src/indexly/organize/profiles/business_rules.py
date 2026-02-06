from pathlib import Path
import re
from datetime import datetime

# -----------------------------
# Heuristic keyword sets
# -----------------------------

INVOICE_HINTS = {
    "invoice", "inv", "rechnung", "bill", "facture"
}

PAID_HINTS = {
    "paid", "bezahlt", "settled"
}

OVERDUE_HINTS = {
    "overdue", "offen", "unpaid"
}

INCOMING_HINTS = {
    "incoming", "supplier", "vendor", "lieferant"
}

RECEIPT_HINTS = {
    "receipt", "beleg", "quittung"
}

TAX_HINTS = {
    "tax", "vat", "ust", "mwst", "steuer"
}

CONTRACT_HINTS = {
    "contract", "agreement", "nda"
}

PAYROLL_HINTS = {
    "payroll", "salary", "lohn", "gehalt"
}

YEAR_PATTERN = re.compile(r"(19|20)\d{2}")


# -----------------------------
# Helpers
# -----------------------------

def _extract_variant(profile: str) -> str:
    """
    Extracts profile variant:
    business           -> default
    business:solo      -> solo
    business:employer  -> employer
    """
    if ":" in profile:
        return profile.split(":", 1)[1]
    return "default"


def _extract_year(file_name: str) -> str | None:
    match = YEAR_PATTERN.search(file_name)
    return match.group(0) if match else None


# -----------------------------
# Main rule entry
# -----------------------------

def get_destination(
    *,
    root: Path,
    file_path: Path,
    profile: str,
    project_name: str | None = None,
    **kwargs,
) -> Path:
    """
    Business profile placement rules.
    Deterministic, filename-based, stateless.
    """

    fname = file_path.name.lower()
    ext = file_path.suffix.lower()
    variant = _extract_variant(profile)

    year = _extract_year(fname) or str(datetime.utcnow().year)

    base = root / "Business"

    # -----------------------------
    # Payroll / HR (employer only)
    # -----------------------------
    if variant == "employer" and any(h in fname for h in PAYROLL_HINTS):
        return base / "Admin" / "HR" / "Payroll" / year / file_path.name

    # -----------------------------
    # Taxes
    # -----------------------------
    if any(h in fname for h in TAX_HINTS):
        return base / "Finance" / "Taxes" / year / file_path.name

    # -----------------------------
    # Receipts
    # -----------------------------
    if any(h in fname for h in RECEIPT_HINTS):
        return base / "Receipts" / "Expenses" / year / file_path.name

    # -----------------------------
    # Invoices
    # -----------------------------
    if any(h in fname for h in INVOICE_HINTS):
        # Incoming invoices
        if any(h in fname for h in INCOMING_HINTS):
            return base / "Invoices" / "Incoming" / year / file_path.name

        # Outgoing invoices
        if any(h in fname for h in PAID_HINTS):
            return base / "Invoices" / "Outgoing" / "Paid" / year / file_path.name
        if any(h in fname for h in OVERDUE_HINTS):
            return base / "Invoices" / "Outgoing" / "Overdue" / year / file_path.name

        return base / "Invoices" / "Outgoing" / "Unpaid" / year / file_path.name

    # -----------------------------
    # Contracts
    # -----------------------------
    if any(h in fname for h in CONTRACT_HINTS):
        if variant == "employer":
            return base / "Contracts" / "Employees" / file_path.name
        return base / "Contracts" / "Customers" / file_path.name

    # -----------------------------
    # Projects (optional project_name)
    # -----------------------------
    if project_name:
        return base / "Projects" / "Active" / project_name / file_path.name

    # -----------------------------
    # Fallback
    # -----------------------------
    return base / "Archive" / file_path.name
