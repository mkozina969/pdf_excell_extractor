
import io, json, zipfile
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Invoice PDF -> Excel (PLUS v3.3.20 stable)", 
    layout="wide"
)

from parsers import diesel_golden, ngk_golden, bosch_golden, conti_golden

PARSERS = {
    "diesel_golden": diesel_golden,
    "ngk_golden": ngk_golden,
    "bosch_golden": bosch_golden,
    "conti_golden": conti_golden,
}

def to_xlsx_bytes(header, items) -> bytes:
    """
    Convert header and items data to Excel format bytes.
    
    Args:
        header: Dictionary containing header information
        items: List of dictionaries containing item data
        
    Returns:
        Excel file as bytes
    """
    import datetime
    from openpyxl import load_workbook
    buf = io.BytesIO()
    hdr = dict(header or {})
    hdr["Parsed on"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame([hdr]).to_excel(xw, sheet_name="Header", index=False)
        cols = ["Item", "Qty", "UoM", "Unit Price", "Amount", "VAT"]
        df = pd.DataFrame(items or [], columns=cols)
        for c in ["Qty", "Unit Price", "Amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.to_excel(xw, sheet_name="ERP_Import", index=False)
    buf.seek(0)
    from openpyxl import load_workbook
    wb = load_workbook(buf)
    wb.active = wb["ERP_Import"]
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()

def extract_text_pdfplumber(b: bytes) -> str:
    """Extract text from PDF using pdfplumber library."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            return "\\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return ""


def extract_text_pypdf(b: bytes) -> str:
    """Extract text from PDF using pypdf library."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(b))
        return "\\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""


def extract_text_pymupdf(b: bytes) -> str:
    """Extract text from PDF using PyMuPDF library."""
    try:
        import fitz
        doc = fitz.open(stream=b, filetype="pdf")
        return "\\n".join(page.get_text("text") for page in doc)
    except Exception:
        return ""

def extract_text_by_setting(b: bytes, extractor: str) -> str:
    """
    Extract text from PDF using specified extractor or auto-detection.
    
    Args:
        b: PDF file as bytes
        extractor: Name of extractor to use or 'auto'
        
    Returns:
        Extracted text content
    """
    if not b:
        return ""
    
    if extractor == "pdfplumber":
        return extract_text_pdfplumber(b)
    if extractor == "pypdf":
        return extract_text_pypdf(b)
    if extractor == "pymupdf":
        return extract_text_pymupdf(b)
    for fn in (extract_text_pdfplumber, extract_text_pypdf, extract_text_pymupdf):
        t = fn(b)
        if t.strip():
            return t
    return ""

def detect_parser(text: str) -> str:
    """
    Detect which parser to use based on text content.
    
    Args:
        text: Text content from PDF
        
    Returns:
        Parser key name
    """
    t = (text or "").lower()
    if "diesel technic" in t:
        return "diesel_golden"
    if "niterra" in t or "ngk" in t:
        return "ngk_golden"
    if "contitech" in t or "continental" in t:
        return "conti_golden"
    if "bosch" in t or "katalo" in t:
        return "bosch_golden"
    return "diesel_golden"

def choose_best_bosch_conti(b: bytes, vendor_key: str):
    """
    Choose best extractor for Bosch and Continental parsers.
    
    Args:
        b: PDF file as bytes
        vendor_key: Parser key ('bosch_golden' or 'conti_golden')
        
    Returns:
        Tuple of (extractor_name, text, item_count) or None
    """
    if vendor_key not in ("bosch_golden", "conti_golden"):
        return None
    if not b:
        return None
    
    texts = {
        "pdfplumber": extract_text_pdfplumber(b),
        "pymupdf": extract_text_pymupdf(b)
    }
    parser = PARSERS[vendor_key]
    best = ("", "", 0)
    for name, txt in texts.items():
        if not txt.strip():
            continue
        try:
            _, items = parser.parse(txt)
            n = len(items or [])
        except Exception:
            n = 0
        if n > best[2]:
            best = (name, txt, n)
    return best if best[2] > 0 else None

st.sidebar.header("Controls")
vendor_override = st.sidebar.selectbox(
    "Vendor override",
    ["auto", "diesel_golden", "ngk_golden", "bosch_golden", "conti_golden"], 
    index=0
)
extractor = st.sidebar.selectbox(
    "Extractor",
    ["auto", "pdfplumber", "pypdf", "pymupdf"],
    index=0
)
show_debug = st.sidebar.checkbox(
    "Show debug (raw text + parsed items)",
    value=False
)

st.title("Invoice PDF -> Excel (PLUS v3.3.20 clean)")
files = st.file_uploader(
    "Upload one or more PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

if files:
    zbuffer = io.BytesIO()
    zf = zipfile.ZipFile(zbuffer, mode="w", compression=zipfile.ZIP_DEFLATED)
    for f in files:
        if f is None:
            st.error("Invalid file uploaded")
            continue
            
        data = f.read()
        if not data:
            st.error(f"File {f.name} is empty")
            continue
            
        baseline_text = extract_text_by_setting(
            data, extractor if extractor != "auto" else "auto"
        )
        
        if not baseline_text.strip():
            st.warning(f"No text could be extracted from {f.name}")
            
        vendor_key = (vendor_override if vendor_override != "auto" 
                     else detect_parser(baseline_text))
        chosen_extractor = extractor
        best = choose_best_bosch_conti(data, vendor_key)
        text = baseline_text
        if best:
            chosen_extractor, text = best[0], best[1]
        parser = PARSERS.get(vendor_key, diesel_golden)
        try:
            header, items = parser.parse(text)
        except Exception as e:
            st.error(f"Parser error for {f.name}: {e}")
            header, items = {}, []
        st.subheader(f.name)
        st.caption(
            f"Parser: **{vendor_key}** · Extractor: **{chosen_extractor}** "
            f"· Parsed items: **{len(items)}**"
        )
        st.write("Header")
        st.dataframe(pd.DataFrame([header]))
        st.write("ERP_Import")
        df = pd.DataFrame(items)
        st.dataframe(df)
        xbytes = to_xlsx_bytes(header, items)
        st.download_button(
            f"⬇️ Download XLSX — {f.name}.xlsx",
            data=xbytes,
            file_name=f"{f.name}.xlsx"
        )
        zf.writestr(f"{f.name}.xlsx", xbytes)
        if show_debug:
            st.write("Debug (first 200 lines)")
            st.text("\\n".join((text or "").splitlines()[:200]))
    zf.close()
    st.download_button(
        "📦 Download all as ZIP",
        data=zbuffer.getvalue(),
        file_name="converted_invoices.zip"
    )
else:
    st.info("Upload one or more PDFs.")
