
import re
from typing import Dict, List, Tuple
from ._common import parse_eu_number, grab, to_erp_item, EU_RE, UOM_RE, INT_RE

def parse(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {
        "Supplier": "Diesel Technic",
        "Invoice Number": grab(r"INVOICE\s+NO\.?\s*([A-Z0-9\-\/]+)", full_text, flags=re.I),
        "Invoice Date": grab(r"DATE\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full_text, flags=re.I),
    }
    items: List[Dict] = []
    for ln in [ln.strip() for ln in full_text.splitlines() if ln.strip()]:
        if re.search(r"ART\.?\s*NO\.?|DESCRIPTION|QTY\.|UNIT\b|PRICE\b|AMOUNT\b|CARRIED OVER", ln, re.I):
            continue
        tokens = [t for t in ln.split() if t]
        if len(tokens) < 6:
            continue
        # last two numeric tokens are Unit Price and Amount
        num_idx = [i for i,t in enumerate(tokens) if EU_RE.match(t)]
        if len(num_idx) < 2:
            continue
        price_i, amount_i = num_idx[-2], num_idx[-1]
        price_s, amount_s = tokens[price_i], tokens[amount_i]
        # before price could be PACK, before that UOM, before that QTY
        if price_i-3 >= 0 and INT_RE.match(tokens[price_i-1]) and UOM_RE.match(tokens[price_i-2]) and EU_RE.match(tokens[price_i-3]):
            qty_s = tokens[price_i-3]; uom = tokens[price_i-2]
        elif price_i-2 >= 0 and UOM_RE.match(tokens[price_i-1]) and EU_RE.match(tokens[price_i-2]):
            qty_s = tokens[price_i-2]; uom = tokens[price_i-1]
        else:
            continue
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
