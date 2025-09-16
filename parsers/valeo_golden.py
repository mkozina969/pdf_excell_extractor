
import re
from typing import Dict, List, Tuple

EU_MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
EU_MONEY_RE = re.compile(EU_MONEY)
QTY_RE = re.compile(r"^\s*(\d{1,5})\s*$")
ITEM_NUM_RE = re.compile(r"^\s*(\d{5,10})\s*$")
PARCEL_RE = re.compile(r"^\s*(\d{3,5}-Z-H\d{2}-\d{2})\s*$", re.I)

def _eu_to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))

def _find_bounds(text: str, start_markers, end_markers):
    t = text.upper()
    start = None
    for m in start_markers:
        i = t.find(m.upper())
        if i != -1:
            start = i; break
    end = len(text)
    for m in end_markers:
        j = t.find(m.upper(), start or 0)
        if j != -1:
            end = j; break
    return start, end

def parse_packing(full_text: str) -> List[Dict]:
    if not full_text: return []
    s, e = _find_bounds(full_text, ["PACKING LIST", "PARCEL N°"], ["INVOICE", "OUR P/N", "YOUR P/N"])
    if s is None: return []
    segment = full_text[s:e]
    lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]
    rows: List[Dict] = []
    current_parcel = None
    pending_qty = None
    pending_item = None
    for ln in lines:
        mp = PARCEL_RE.match(ln)
        if mp:
            current_parcel = mp.group(1)
            continue
        if re.search(r"[A-Za-z]", ln):  # drop headers, 'PALLET', etc.
            continue
        if re.search(r"\d+\.\d", ln):   # decimals => dims/weights
            continue
        mi = ITEM_NUM_RE.match(ln)
        mq = QTY_RE.match(ln)
        if mi and not mq:
            pending_item = mi.group(1)
        elif mq:
            try: pending_qty = int(mq.group(1))
            except: pending_qty = None
        if current_parcel and pending_item and (pending_qty is not None):
            rows.append({"Parcel N°": current_parcel, "Valeo Material N": pending_item, "Quantity": pending_qty})
            pending_item = None; pending_qty = None
    return rows

def parse_invoice(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {"Supplier": "Valeo"}
    if not full_text: return header, []
    m = re.search(r"\bInvoice\s+(\d+)\b", full_text, re.I)
    if m: header["Invoice Number"] = m.group(1)
    m = re.search(r"INVOICE\s*DATE\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full_text, re.I)
    if m: header["Invoice Date"] = m.group(1)
    m = re.search(r"\b(EUR|USD|GBP|PLN|HRK)\b", full_text)
    if m: header["Currency"] = m.group(1)

    s, e = _find_bounds(full_text, ["OUR P/N", "YOUR P/N", "INVOICE"], ["RECAP", "TOTAL", "PAYMENT TERMS"])
    text = full_text[s:e] if s is not None else full_text
    lines = [ln.rstrip() for ln in text.splitlines()]
    items: List[Dict] = []
    i = 0
    while i < len(lines):
        ln = lines[i]; nxt = lines[i+1] if i+1 < len(lines) else ""
        window = (ln + " " + nxt).strip()
        m_item = re.match(r"^\s*(\d{4,})\b", ln.strip())
        if m_item:
            item = m_item.group(1)
            tail = ln[m_item.end():] + " " + nxt
            qty = None
            for mqty in re.finditer(r"\b(\d{1,5})\b", tail):
                try: qty = int(mqty.group(1)); break
                except: pass
            monies = re.findall(EU_MONEY, window)
            unit_price = amount = None
            if len(monies) >= 2:
                unit_price = _eu_to_float(monies[-2]); amount = _eu_to_float(monies[-1])
            elif len(monies) == 1 and qty is not None:
                unit_price = _eu_to_float(monies[0]); amount = round(qty*unit_price, 2)
            if item and qty is not None and unit_price is not None and amount is not None:
                items.append({"Item": item,"Qty": qty,"UoM": "PC","Unit Price": unit_price,"Amount": amount,"VAT": None})
        i += 1
    return header, items

def parse(full_text: str):
    return parse_invoice(full_text)
