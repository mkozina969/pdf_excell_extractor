
# -*- coding: utf-8 -*-
from __future__ import annotations
import io, zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

from parsers import diesel_golden, ngk_golden
from parsers.valeo_golden import parse_invoice as valeo_parse_invoice, parse_packing as valeo_parse_packing

def extract_text_auto(data: bytes) -> str:
    def _pl():
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            return ""
    def _fz():
        try:
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            return "\\n".join(page.get_text("text") for page in doc)
        except Exception:
            return ""
    txt = _pl()
    if not txt.strip():
        txt = _fz()
    return txt

def detect_vendor(text: str) -> str:
    t = text.lower()
    if "valeo" in t or "packing list" in t:
        return "valeo_golden"
    if "ngk" in t or "niterra" in t:
        return "ngk_golden"
    if "diesel technic" in t:
        return "diesel_golden"
    return "diesel_golden"

def to_xlsx_bytes(header: Dict, items: List[Dict], name="ERP_Import") -> bytes:
    dfh = pd.DataFrame([header or {}])
    dfi = pd.DataFrame(items or [])
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        dfh.to_excel(xw, index=False, sheet_name="Header")
        dfi.to_excel(xw, index=False, sheet_name=name)
    return bio.getvalue()

st.set_page_config(page_title="Invoice PDF -> Excel (PLUS v3.3.20)", layout="wide")
st.title("Invoice PDF -> Excel (PLUS v3.3.20)")
vendor_override = st.sidebar.selectbox("Vendor override", ["auto","valeo_golden","ngk_golden","diesel_golden"], index=0)
show_debug = st.sidebar.checkbox("Show debug", value=False)

files = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)
if not files:
    st.stop()

zip_buf = io.BytesIO()
zf = zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED)

for f in files:
    data = f.read()
    text = extract_text_auto(data)
    vendor = vendor_override if vendor_override != "auto" else detect_vendor(text)

    if vendor == "valeo_golden":
        header, items = valeo_parse_invoice(text)
    elif vendor == "ngk_golden":
        header, items = ngk_golden(text)
    else:
        header, items = diesel_golden(text)

    st.subheader(f.name)
    st.caption(f"Vendor: {vendor} · Parsed items: {len(items)}")

    st.write("Header")
    st.dataframe(pd.DataFrame([header]), use_container_width=True)

    st.write("ERP_Import")
    st.dataframe(pd.DataFrame(items), use_container_width=True)

    # Invoice XLSX
    inv_xlsx = to_xlsx_bytes(header, items)
    st.download_button(f"⬇️ Download XLSX — {Path(f.name).stem}.xlsx", data=inv_xlsx, file_name=f"{Path(f.name).stem}.xlsx")
    zf.writestr(f"{Path(f.name).stem}.xlsx", inv_xlsx)

    # Valeo packing list extra
    if vendor == "valeo_golden":
        pk = valeo_parse_packing(text) or []
        st.write("Valeo Packing List")
        dfp = pd.DataFrame(pk, columns=["Parcel N°","Valeo Material N","Quantity"])
        st.dataframe(dfp, use_container_width=True)
        if not dfp.empty:
            bio = io.BytesIO()
            with pd.ExcelWriter(bio, engine="openpyxl") as xw:
                dfp.to_excel(xw, index=False, sheet_name="PackingList")
            fname = f"{Path(f.name).stem}_PackingList.xlsx"
            st.download_button(f"⬇️ Download {fname}", data=bio.getvalue(), file_name=fname)
            zf.writestr(fname, bio.getvalue())

    if show_debug:
        st.text(text[:4000])

zf.close()
st.download_button("📦 Download all as ZIP", data=zip_buf.getvalue(), file_name="exports.zip")
