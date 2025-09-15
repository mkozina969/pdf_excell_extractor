
import re
from typing import Dict, List, Tuple
from ._common import parse_eu_number, grab, to_erp_item, EU_RE, UOM_RE

START = re.compile(r"^\s*\d{5,6}\s+\S+")

def parse(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {
        "Supplier": "NGK / Niterra",
        "Invoice Number": grab(r"Invoice\s*No\.?\s*([A-Z0-9\-\/]+)", full_text, flags=re.I),
        "Invoice Date": grab(r"Date\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full_text, flags=re.I),
    }
    items: List[Dict] = []
    for ln in [ln.strip() for ln in full_text.splitlines() if ln.strip()]:
        if not START.match(ln):
            continue
        tokens = [t for t in ln.split() if t]
        idx_num = [i for i,t in enumerate(tokens) if EU_RE.match(t)]
        if not idx_num:
            continue
        amount_i = idx_num[-1]
        amount_s = tokens[amount_i]
        if amount_i-1 < 0 or not UOM_RE.match(tokens[amount_i-1]):
            continue
        uom = tokens[amount_i-1]
        if amount_i-2 < 0 or not EU_RE.match(tokens[amount_i-2]):
            continue
        qty_s = tokens[amount_i-2]
        # find previous numeric before qty (skip optional 'EUR')
        price_i = None
        j = amount_i-3
        while j >= 0:
            if tokens[j].upper() == "EUR":
                j -= 1
                continue
            if EU_RE.match(tokens[j]):
                price_i = j
                break
            j -= 1
        if price_i is None:
            continue
        price_s = tokens[price_i]
        item = tokens[1] if len(tokens) > 1 else None
        items.append(to_erp_item({
            "Item": item,
            "Qty": parse_eu_number(qty_s),
            "UoM": uom,
            "Unit Price": parse_eu_number(price_s),
            "Amount": parse_eu_number(amount_s),
            "VAT": None,
        }))
    return header, items
