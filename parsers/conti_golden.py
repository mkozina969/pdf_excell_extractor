import re
from typing import Dict, List, Tuple, Optional
from ._common import parse_eu_number

EU_NUM = r"(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?"
EU_RE = re.compile(rf"^{EU_NUM}$")

def _eu_float(s: str) -> float:
    """Convert European number format to float."""
    return float(s.replace(".", "").replace(",", "."))


def parse(full_text: str) -> Tuple[Dict, List[Dict]]:
    """
    Parse ContiTech/Continental invoice PDF text content.
    
    Args:
        full_text: Full text content extracted from PDF
        
    Returns:
        Tuple of (header_dict, items_list) containing parsed invoice data
    """
    header: Dict = {"Supplier": "ContiTech / Continental"}
    items: List[Dict] = []
    if not full_text:
        return header, items
    lines = [ln.rstrip() for ln in full_text.splitlines()]

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        # Item reference line (e.g., CT1000 or 7PK1236 or 10X1000)
        if re.fullmatch(r"[A-Z0-9][A-Z0-9\-/\.]{2,}", ln):
            code = ln

            # Look back a few lines for Qty and UoM (often split across lines)
            qty, uom = None, None
            for j in range(max(0, i-3), i):
                sj = lines[j].strip()
                if re.fullmatch(r"\d{1,5}", sj):
                    try:
                        qty = int(sj)
                    except Exception:
                        pass
                if re.fullmatch(r"[A-Z]{2,4}", sj):
                    uom = sj

            # Look forward for Unit Price and Amount — the "EUR" line is
            # separated and the amount appears on a later line with the UoM.
            unit_price, amount = None, None
            for j in range(i+1, min(i+10, len(lines))):
                s = lines[j]
                if "EUR" in s and unit_price is None:
                    m = re.search(rf"({EU_NUM})\s*EUR", s)
                    if m:
                        unit_price = _eu_float(m.group(1))
                m2 = re.search(
                    rf"\b([A-Z]{{2,4}})\b.*?({EU_NUM})\s*$", s
                )
                if m2:
                    if uom is None:
                        uom = m2.group(1)
                    amount = _eu_float(m2.group(2))

            if (code and qty is not None and uom and 
            unit_price is not None and amount is not None):
                items.append({
                    "Item": code,
                    "Qty": qty,
                    "UoM": uom,
                    "Unit Price": unit_price,
                    "Amount": amount,
                    "VAT": None,
                })
                i += 1
                continue
        i += 1

    # Best-effort header
    m_no = re.search(
        r"\b(?:Number|Invoice)\s+([0-9]{5,})\b", full_text, re.I
    )
    if m_no:
        header["Invoice Number"] = m_no.group(1)
    m_dt = re.search(
        r"\b(?:Date|Datum)\s*[:#]?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        full_text,
        re.I
    )
    if m_dt:
        header["Invoice Date"] = m_dt.group(1)
    header.setdefault("Currency", "EUR")

    return header, items
