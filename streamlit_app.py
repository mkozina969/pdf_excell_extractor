
import io, json, zipfile
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Invoice PDF -> Excel (PLUS v3.3.20)", layout="wide")

# Parsers
from parsers import diesel_golden, ngk_golden, bosch_golden, conti_golden, valeo_golden

PARSERS = {
    "diesel_golden": diesel_golden,
    "ngk_golden": ngk_golden,
    "bosch_golden": bosch_golden,
    "conti_golden": conti_golden,
    "valeo_golden": valeo_golden,
}

# ----- Helpers -----
def to_xlsx_bytes(header, items) -> bytes:
    import datetime
    from openpyxl import load_workbook
    buf = io.BytesIO()
    hdr = dict(header or {}); hdr["Parsed on"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame([hdr]).to_excel(xw, sheet_name="Header", index=False)
        cols = ["Item","Qty","UoM","Unit Price","Amount","VAT"]
        df = pd.DataFrame(items or [], columns=cols)
        for c in ["Qty","Unit Price","Amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.to_excel(xw, sheet_name="ERP_Import", index=False)
    buf.seek(0)
    wb = load_workbook(buf); wb.active = wb["ERP_Import"]
    out = io.BytesIO(); wb.save(out); out.seek(0); return out.getvalue()

def extract_text_pdfplumber(b: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return ""

def extract_text_pypdf(b: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(b))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""

def extract_text_pymupdf(b: bytes) -> str:
    try:
        import fitz
        doc = fitz.open(stream=b, filetype="pdf")
        return "\n".join(page.get_text("text") for page in doc)
    except Exception:
        return ""

def extract_text_by_setting(b: bytes, extractor: str) -> str:
    if extractor == "pdfplumber": return extract_text_pdfplumber(b)
    if extractor == "pypdf": return extract_text_pypdf(b)
    if extractor == "pymupdf": return extract_text_pymupdf(b)
    for fn in (extract_text_pdfplumber, extract_text_pypdf, extract_text_pymupdf):
        t = fn(b)
        if t.strip(): return t
    return ""

def detect_parser(text: str) -> str:
    t = (text or "").lower()
    if "valeo service" in t or "our p/n" in t: return "valeo_golden"
    if "diesel technic" in t: return "diesel_golden"
    if "niterra" in t or "ngk" in t: return "ngk_golden"
    if "contitech" in t or "continental" in t: return "conti_golden"
    if "bosch" in t or "katalo" in t: return "bosch_golden"
    return "diesel_golden"

def choose_best_bosch_conti(b: bytes, vendor_key: str):
    if vendor_key not in ("bosch_golden", "conti_golden"):
        return None
    texts = {"pdfplumber": extract_text_pdfplumber(b), "pymupdf": extract_text_pymupdf(b)}
    parser = PARSERS[vendor_key]
    best = ("", "", 0)
    for name, txt in texts.items():
        if not txt.strip(): continue
        try:
            _, items = parser.parse(txt); n = len(items or [])
        except Exception:
            n = 0
        if n > best[2]:
            best = (name, txt, n)
    return best if best[2] > 0 else None

# ----- UI -----
st.sidebar.header("Controls")
vendor_override = st.sidebar.selectbox("Vendor override", ["auto","diesel_golden","ngk_golden","bosch_golden","conti_golden","valeo_golden"], index=0)
extractor = st.sidebar.selectbox("Extractor", ["auto","pdfplumber","pypdf","pymupdf"], index=0)
show_debug = st.sidebar.checkbox("Show debug (raw text + parsed)", value=False)

# Goldens self-test
def run_goldens():
    gpath = Path("goldens/goldens.json")
    if not gpath.exists():
        st.info("Put sample PDFs into ./goldens and define tests in goldens.json")
        return
    tests = json.loads(gpath.read_text(encoding="utf-8"))
    rows = []
    for fname, spec in tests.items():
        fpath = Path("goldens")/fname
        if not fpath.exists():
            rows.append((fname, spec.get("override"), 0, "missing"))
            continue
        b = fpath.read_bytes()
        chosen = spec.get("preferred_extractor","auto")
        text = extract_text_by_setting(b, chosen if chosen!="auto" else "auto")
        key = spec.get("override") or detect_parser(text)
        try:
            _, items = PARSERS[key].parse(text)
            n = len(items)
            nmin = spec.get("expected_count_min")
            ok = (nmin is None) or (n >= nmin)
            rows.append((fname, key, n, "OK" if ok else f"FAIL: {n} < {nmin}"))
        except Exception as e:
            rows.append((fname, key, 0, f"ERR: {e}"))
    st.dataframe(pd.DataFrame(rows, columns=["file","parser","items","status"]))

if st.sidebar.button("Run self-tests (goldens/)"):
    run_goldens()

st.title("Invoice PDF -> Excel (PLUS v3.3.20)")
files = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)

if files:
    zbuffer = io.BytesIO()
    zf = zipfile.ZipFile(zbuffer, mode="w", compression=zipfile.ZIP_DEFLATED)
    for f in files:
        data = f.read()

        baseline_text = extract_text_by_setting(data, extractor if extractor!="auto" else "auto")
        vendor_key = vendor_override if vendor_override != "auto" else detect_parser(baseline_text)
        chosen_extractor = extractor
        best = choose_best_bosch_conti(data, vendor_key)
        text = baseline_text
        if best:
            chosen_extractor, text = best[0], best[1]

        parser = PARSERS.get(vendor_key, diesel_golden)
        try:
            header, items = parser.parse(text)
        except Exception as e:
            st.error(f"Parser error: {e}"); header, items = {}, []

        st.subheader(f.name)
        st.caption(f"Parser: **{vendor_key}** · Extractor: **{chosen_extractor}** · Parsed items: **{len(items)}**")
        st.write("Header"); st.dataframe(pd.DataFrame([header]))
        st.write("ERP_Import"); st.dataframe(pd.DataFrame(items))

        xbytes = to_xlsx_bytes(header, items)
        zf.writestr(f"{f.name}.xlsx", xbytes)
        st.download_button(f"⬇️ Download XLSX — {f.name}.xlsx", data=xbytes, file_name=f"{f.name}.xlsx")

        if show_debug:
            st.write("Debug (first 200 lines)")
            st.text("\n".join((text or '').splitlines()[:200]))

    zf.close()
    st.download_button("📦 Download all as ZIP", data=zbuffer.getvalue(), file_name="converted_invoices.zip")
else:
    st.info("Upload one or more PDFs.")
