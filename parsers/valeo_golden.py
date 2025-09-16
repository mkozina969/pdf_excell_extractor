
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Dict, List, Tuple

EU_MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"
EU_MONEY_RE = re.compile(EU_MONEY)
ORIG = {"FR","ES","IT","RO","CZ","TN","CN","DE","PL","PT","BE","HU","GB","SK","TR"}

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
    if start is None: return None, None
    for m in end_markers:
        j = t.find(m.upper(), start)
        if j != -1:
            end = j; break
    return start, end

def parse_packing(full_text: str) -> List[Dict]:
    if not full_text: return []
    rows: List[Dict] = []
    tU = full_text.upper()
    starts = [m.start() for m in re.finditer(r"\bPACKING LIST\b", tU)]
    if not starts:
        return rows
    for si in starts:
        next_p_m = re.search(r"\bPACKING LIST\b", tU[si+1:])
        next_p = (si + 1 + next_p_m.start()) if next_p_m else -1
        next_i = tU.find("INVOICE", si+1)
        end = min([x for x in [next_p, next_i, len(full_text)] if x != -1])
        segment = full_text[si:end]
        lines = [ln.rstrip("\n") for ln in segment.splitlines()]
        # header
        header_idx = -1
        for i, ln in enumerate(lines):
            l = ln.lower()
            if "parcel n" in l and "valeo material" in l and "quantity" in l:
                header_idx = i; break
        if header_idx == -1:
            for i, ln in enumerate(lines):
                l = ln.lower()
                if "parcel" in l and "material" in l and "quantity" in l:
                    header_idx = i; break
        if header_idx == -1: 
            continue
        header = lines[header_idx].lower()
        idx_parcel   = header.find("parcel")
        idx_material = header.find("valeo material")
        if idx_material == -1: idx_material = header.find("material")
        idx_qty      = header.find("quantity")
        # right bound for qty
        idx_after_qty = None
        idx_cust_mat = header.find("customer material")
        idx_cust_ord = header.find("customer order")
        rb = [x for x in [idx_cust_mat, idx_cust_ord] if x != -1]
        if rb: idx_after_qty = min(rb)
        if min(idx_parcel, idx_material, idx_qty) == -1: 
            continue

        current_parcel = ""
        for ln in lines[header_idx+1:]:
            if not ln.strip(): continue
            if "packing list" in ln.lower(): break
            parcel_slice   = ln[idx_parcel: idx_material] if len(ln) > idx_parcel else ""
            material_slice = ln[idx_material: idx_qty]    if len(ln) > idx_material else ""
            qty_slice = (ln[idx_qty: idx_after_qty] if (idx_after_qty is not None and len(ln) > idx_qty)
                        else (ln[idx_qty:] if len(ln) > idx_qty else ""))
            mpar = re.search(r"\b(\d{7,10})\b", parcel_slice)
            parcel = mpar.group(1) if mpar else ""
            if parcel: current_parcel = parcel
            parcel = current_parcel
            mats = re.findall(r"\d{5,12}", material_slice)
            material = mats[-1] if mats else ""
            mqty = re.findall(r"\d{1,6}", qty_slice.replace(" ", ""))
            qty = int(mqty[-1]) if mqty else None
            if parcel and material and qty is not None:
                rows.append({"Parcel N°": parcel, "Valeo Material N": material, "Quantity": qty})
    return rows

def parse_invoice(full_text: str) -> Tuple[Dict, List[Dict]]:
    header: Dict = {"Supplier": "Valeo"}
    if not full_text: return header, []
    m = re.search(r"\\bInvoice\\s+(\\d+)\\b", full_text, re.I)
    if m: header["Invoice Number"] = m.group(1)
    m = re.search(r"INVOICE\\s*DATE\\s*[:\\-]?\\s*([0-9]{2}\\.[0-9]{2}\\.[0-9]{4})", full_text, re.I)
    if m: header["Invoice Date"] = m.group(1)
    m = re.search(r"\\b(EUR|USD|GBP|PLN|HRK)\\b", full_text)
    if m: header["Currency"] = m.group(1)

    s, e = _find_bounds(full_text, ["Our p/n","OUR P/N"], ["PACKING LIST"])
    text = full_text[s:e] if s is not None else full_text
    lines = [ln.rstrip() for ln in text.splitlines()]

    def is_desc(s: str) -> bool:
        L = s.strip().lower()
        if not re.search(r"[a-z]{2}", L): return False
        if L.startswith("your order") or "goods value" in L or L.startswith("surcharge"): return False
        return True

    items: List[Dict] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if not ln: i += 1; continue
        if not is_desc(ln): i += 1; continue
        qty = None; unit = None; amount = None; code = None; customs = None
        j = i+1; limit = min(i+14, len(lines))
        while j < limit:
            s2 = lines[j].strip()
            if not s2: j += 1; continue
            if is_desc(s2): break
            if qty is None and re.fullmatch(r"\\d{1,4}", s2) and j+1 < len(lines) and lines[j+1].strip() in ORIG:
                qty = int(s2)
            if customs is None and re.fullmatch(r"\\d{8}", s2):
                customs = s2
            if code is None and re.fullmatch(r"\\d{4,8}", s2) and s2 != customs:
                code = s2
            monies = EU_MONEY_RE.findall(s2)
            if len(monies) >= 2:
                unit = _eu_to_float(monies[-2]); amount = _eu_to_float(monies[-1])
            elif len(monies) == 1 and unit is None:
                unit = _eu_to_float(monies[0])
            j += 1
        if code is None:
            mcode = re.match(r"^\\s*(\\d{4,8})\\b", ln)
            if mcode: code = mcode.group(1)
        if code and qty and unit is not None and amount is not None:
            items.append({"Item": code, "Qty": int(qty), "UoM": "PC",
                          "Unit Price": float(unit), "Amount": float(amount), "VAT": None})
        i = j
    return header, items

def parse(full_text: str):
    return parse_invoice(full_text)
