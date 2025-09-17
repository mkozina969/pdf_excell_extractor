import streamlit as st
import pdfplumber, re, pandas as pd, io, unicodedata

st.set_page_config(page_title="Valeo → XLSX (Invoice / Packing)", layout="wide")
st.title("Valeo PDF → XLSX (lines only)")

mode = st.radio("Choose document type", ["Invoice", "Packing list"], horizontal=True)
uploads = st.file_uploader("Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)

combine = st.checkbox("Also produce a combined XLSX for all uploads", value=True)

# ---------- Utilities ----------
def normalize(s: str) -> str:
    if s is None: return ""
    return unicodedata.normalize("NFKC", str(s)).replace("\xa0", " ").strip()

def eu_to_float(s: str):
    s = normalize(s).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def read_pdf_text(upload) -> str:
    # pdfplumber sometimes returns None for empty pages—guard it.
    with pdfplumber.open(upload) as pdf:
        return "\n".join([normalize(p.extract_text() or "") for p in pdf.pages])

# ---------- Parsing: Invoice ----------
def parse_valeo_invoice_text(text: str) -> pd.DataFrame:
    rows = []
    current_inv = None
    inv_re = re.compile(r"\b(695\d{6})\b")
    skip_prefixes = tuple(p.lower() for p in [
        "your order:", "delivery note:", "goods value", "vat rate",
        "transport cost", "currency", "total gross value",
        "net price without vat", "surcharge", "goods value per customs code",
        "weight by customs code"
    ])

    for raw_line in (l for l in text.splitlines() if l.strip()):
        # Track invoice number that appears in headers
        m_inv = inv_re.search(raw_line)
        if m_inv:
            current_inv = m_inv.group(1)

        low = raw_line.lower().strip()
        if low.startswith(skip_prefixes):
            continue

        tok = normalize(raw_line).split()
        if not tok:
            continue

        # Item line must start with Valeo part number (all digits, >=3 chars)
        part = tok[0]
        if not re.fullmatch(r"\d{3,}", part):
            continue

        # Find (Qty, Country, Customs) triplet anywhere in the line
        j = None
        for k in range(2, len(tok) - 2):
            if re.fullmatch(r"[A-Z]{2}", tok[k]) and re.fullmatch(r"\d{6,8}", tok[k + 1]):
                if re.fullmatch(r"\d+", tok[k - 1]):  # Qty just before country
                    j = k
        if j is None:
            continue

        qty = int(tok[j - 1])

        # Take the last two numeric tokens as Net Unit and Total Net
        nums = [t for t in tok if re.fullmatch(r"[\d\.,]+", t)]
        if len(nums) < 2:
            continue
        net_price = eu_to_float(nums[-2])
        tot_net   = eu_to_float(nums[-1])

        rows.append([part, qty, net_price, tot_net, current_inv])

    df = pd.DataFrame(rows, columns=["Supplier_ID","Qty","Net Price","Tot. Net Value","InvoiceNo"])
    return df.drop_duplicates().reset_index(drop=True)

# ---------- Parsing: Packing list ----------
def parse_valeo_packing_text(text: str) -> pd.DataFrame:
    # Example rows (see your PDF):
    # 19471318 PALLET ... 826522 24  ... ; sometimes an extra "1" line follows same material.
    parcel_pat = re.compile(r"^\s*(?P<parcel>\d{6,})\s+PALLET\b")
    # Capture Valeo material and Qty at end of a content line
    item_pat = re.compile(r"(?P<valeo>\d{3,})\s+(?P<qty>\d+)(?:\s+\d+)?(?:\s+[A-Z0-9\-\/]+)?\s*$")

    lines = [normalize(l) for l in text.splitlines() if l.strip()]
    parcels = [(i, parcel_pat.match(ln).group("parcel")) for i, ln in enumerate(lines) if parcel_pat.match(ln)]
    if not parcels:
        return pd.DataFrame(columns=["Parcel N°","VALEO Material N°","Quantity"])

    rows = []
    for idx, ln in enumerate(lines):
        m = item_pat.search(ln)
        if not m:
            continue
        # Map each item line to nearest parcel header above/below
        nearest = min(parcels, key=lambda t: abs(t[0] - idx))
        rows.append([nearest[1], m.group("valeo"), int(m.group("qty"))])

    df = pd.DataFrame(rows, columns=["Parcel N°","VALEO Material N°","Quantity"])
    return df.drop_duplicates().reset_index(drop=True)

# ---------- Run ----------
if uploads:
    all_frames = []
    for up in uploads:
        st.divider()
        st.write(f"**File:** {up.name}")
        with st.spinner("Reading PDF..."):
            text = read_pdf_text(up)

        if mode == "Invoice":
            df = parse_valeo_invoice_text(text)
            st.subheader(f"Invoice lines: {up.name} ({len(df)} rows)")
            st.dataframe(df, use_container_width=True)

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                df.to_excel(xw, index=False, sheet_name="InvoiceLines")
            st.download_button(
                label=f"Download XLSX (Invoice) – {up.name}",
                data=buf.getvalue(),
                file_name=f"{up.name.rsplit('.',1)[0]}_invoice_lines.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            df = parse_valeo_packing_text(text)
            st.subheader(f"Packing lines: {up.name} ({len(df)} rows)")
            st.dataframe(df, use_container_width=True)

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                df.to_excel(xw, index=False, sheet_name="PackingLines")
            st.download_button(
                label=f"Download XLSX (Packing) – {up.name}",
                data=buf.getvalue(),
                file_name=f"{up.name.rsplit('.',1)[0]}_packing_lines.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        # prepare combined export if requested
        df.insert(0, "SourceFile", up.name)
        all_frames.append(df)

    if combine and all_frames:
        st.divider()
        combined = pd.concat(all_frames, ignore_index=True)
        st.subheader(f"Combined export ({len(combined)} rows)")
        st.dataframe(combined.head(1000), use_container_width=True)  # show at most 1000 rows

        buf_all = io.BytesIO()
        with pd.ExcelWriter(buf_all, engine="openpyxl") as xw:
            combined.to_excel(xw, index=False, sheet_name="AllLines")
        st.download_button(
            label="Download combined XLSX",
            data=buf_all.getvalue(),
            file_name=f"valeo_{mode.replace(' ', '_').lower()}_lines_all.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Upload one or more Valeo PDFs to begin.")
