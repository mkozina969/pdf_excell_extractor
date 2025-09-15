import re
from typing import Dict, List, Tuple
from ._common import parse_eu_number

# patterns
MONEY_RE = re.compile(r"\b(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}\b")  # must have comma + 2 decimals
RBR_RE = re.compile(r"^\s*(\d{1,4})\b")
UOM_RE = re.compile(r"\b(KOM|PC|PCS|STK|SET|KOMADA|PAR|M|KM|KG|L)\b", re.I)
KAT_RE = re.compile(r"^Katalo[šs]ki\s+broj\s*:\s*(.+)$", re.I)
KAT_ARTIKLA_RE = re.compile(r"^Katalo[šs]ki\s+broj\s+artikla\s*:\s*(.+)$", re.I)

def _eu_to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))

def _shorten_artikla(s: str) -> str:
    # reduce long 4-group to the last 3 groups (ERP code shape)
    g = re.findall(r"\d{1,3}", s.replace(".", " "))
    return ".".join(g[-3:]) if len(g) >= 3 else s.strip()

def _pick_item_code(block: List[str]) -> str:
    for ln in block:
        m = KAT_RE.search(ln)
        if m:
            return m.group(1).strip()
    for ln in block:
        m = KAT_ARTIKLA_RE.search(ln)
        if m:
            return _shorten_artikla(m.group(1))
    # last resort: any dotted 3×3 code in the block
    for ln in block:
        m = re.search(r"\b\d{3}\.\d{3}\.\d{3}\b", ln)
        if m: return m.group(0)
    return None

def parse(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {"Supplier": "Bosch"}
    items: List[Dict] = []
    if not full_text:
        return header, items

    lines = [ln.rstrip() for ln in full_text.splitlines()]

    # header bits
    m_no = re.search(r"(?:Broj\s+ra[cč]una|Invoice\s*No\.?)\s*[:#]?\s*([A-Z0-9\-/]+)", full_text, re.I)
    if m_no: header["Invoice Number"] = m_no.group(1)
    m_dt = re.search(r"(?:Datum|Date)\s*[:#]?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full_text, re.I)
    if m_dt: header["Invoice Date"] = m_dt.group(1)
    m_curr = re.search(r"\b(EUR|USD|PLN|HRK)\b", full_text, re.I)
    if m_curr: header["Currency"] = m_curr.group(1).upper()

    # --- segment by Rbr anchors ---
    anchors = [i for i, ln in enumerate(lines) if RBR_RE.match(ln)]
    anchors.append(len(lines))

    for a, b in zip(anchors, anchors[1:]):
        block = lines[a:b]
        if not block:
            continue

        # Rbr line and small window for wrapped numbers
        rbr_line = block[0]
        window = " ".join(block[:2])  # rbr line + next line

        # Qty + UoM (word = UoM, integer immediately on the left = Qty)
        qty, uom = None, None
        mu = UOM_RE.search(window)
        if mu:
            uom = mu.group(1).upper()
            pre = window[:mu.start()]
            mqty = re.findall(r"\b\d{1,5}\b", pre)
            if mqty:
                try: qty = int(mqty[-1])
                except: qty = None

        # Unit Price + Amount: prefer two MONEY tokens on Rbr window
        money = MONEY_RE.findall(window)
        unit_price = amount = None
        if len(money) >= 2:
            unit_price = _eu_to_float(money[-2])
            amount = _eu_to_float(money[-1])
        elif len(money) == 1 and qty is not None:
            unit_price = _eu_to_float(money[0])
            amount = round(qty * unit_price, 2)
        else:
            # fallback: scan the whole block for the last two money tokens
            money_block = MONEY_RE.findall(" ".join(block[:3]))
            if len(money_block) >= 2:
                unit_price = _eu_to_float(money_block[-2])
                amount = _eu_to_float(money_block[-1])

        item = _pick_item_code(block)

        # Skip malformed blocks
        if item and qty is not None and unit_price is not None and amount is not None:
            items.append({
                "Item": item,
                "Qty": qty,
                "UoM": uom,
                "Unit Price": unit_price,
                "Amount": amount,
                "VAT": None,
            })

    return header, items
