
import re
from typing import Dict, List, Tuple

EU_MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
EU_MONEY_RE = re.compile(EU_MONEY)
QTY_RE = re.compile(r"\b(\d{1,5})\b")
ITEM_START_RE = re.compile(r"^\s*(\d{4,})\b")

def _eu_to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))

def parse(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {"Supplier": "Valeo"}
    if not full_text:
        return header, []
    m = re.search(r"\bInvoice\s+(\d+)\b", full_text, re.I)
    if m: header["Invoice Number"] = m.group(1)
    m = re.search(r"INVOICE\s*DATE\s*:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", full_text, re.I)
    if m: header["Invoice Date"] = m.group(1)
    m = re.search(r"\b(EUR|USD|GBP|PLN|HRK)\b", full_text)
    if m: header["Currency"] = m.group(1)

    lines = [ln.rstrip() for ln in full_text.splitlines()]
    items: List[Dict] = []

    i = 0
    while i < len(lines):
        ln = lines[i]
        nxt = lines[i+1] if i+1 < len(lines) else ""
        window = (ln + " " + nxt).strip()

        m_item = ITEM_START_RE.match(ln.strip())
        if m_item:
            item = m_item.group(1)
            tail = ln[m_item.end():] + " " + nxt
            qty = None
            for mqty in QTY_RE.finditer(tail):
                try: qty = int(mqty.group(1)); break
                except: pass
            monies = EU_MONEY_RE.findall(window)
            unit_price = amount = None
            if len(monies) >= 2:
                unit_price = _eu_to_float(monies[-2])
                amount = _eu_to_float(monies[-1])
            elif len(monies) == 1 and qty is not None:
                unit_price = _eu_to_float(monies[0])
                amount = round(qty * unit_price, 2)
            if item and qty is not None and unit_price is not None and amount is not None:
                items.append({"Item": item,"Qty": qty,"UoM": "PC","Unit Price": unit_price,"Amount": amount,"VAT": None})

        if "SURCHARGE" in window.upper():
            qty2 = None
            for mqty in QTY_RE.finditer(window):
                try: qty2 = int(mqty.group(1)); break
                except: pass
            monies2 = EU_MONEY_RE.findall(window)
            if len(monies2) >= 2 and qty2 is not None:
                items.append({"Item":"SURCHARGE","Qty": qty2,"UoM":"PC","Unit Price": _eu_to_float(monies2[-2]),"Amount": _eu_to_float(monies2[-1]),"VAT": None})

        i += 1

    return header, items
