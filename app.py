import streamlit as st
import pandas as pd
import io
import re


def format_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' → 'DD/MM/YYYY'."""
    try:
        parts = str(date_str).strip()[:10].split("-")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{d:02d}/{m:02d}/{y}"
    except Exception as e:
        return f"ERR: {e}"


def extract_ref_number(inv: str) -> str:
    """Strip non-numeric prefix (e.g. 'INV-') and return digits only."""
    return re.sub(r"[^0-9]", "", str(inv))


def truncate(text: str, max_len: int = 50) -> str:
    return str(text)[:max_len]


def fmt_amount(val) -> str:
    try:
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return "0.00"


# ── Conversion logic ─────────────────────────────────────────────────
def convert_df(
    df: pd.DataFrame,
    col_date: str,
    col_invoice: str,
    col_customer: str,
    col_amount: str,
    debit_account: str,
    credit_account: str,
) -> tuple[pd.DataFrame, list[str]]:
    rows = []
    errors = []
    for idx, r in df.iterrows():
        row_num = idx + 2  # Excel row (1-based + header)

        # Validate required fields
        if pd.isna(r[col_date]) or str(r[col_date]).strip() == "":
            errors.append(f"שורה {row_num}: תאריך חסר")
            continue
        if pd.isna(r[col_amount]):
            errors.append(f"שורה {row_num}: סכום חסר")
            continue

        formatted_date = format_date(str(r[col_date]))
        if formatted_date.startswith("ERR"):
            errors.append(f"שורה {row_num}: תאריך לא תקין – {r[col_date]}")
            continue

        ref = extract_ref_number(r.get(col_invoice, ""))
        customer = truncate(str(r.get(col_customer, "")))
        amount = fmt_amount(r[col_amount])

        rows.append(
            {
                "תאריך": formatted_date,
                "חשבון חובה": debit_account,
                "חשבון זכות 1": credit_account,
                "חשבון זכות 2": "",
                "פרטים": customer,
                "אסמכתא": ref,
                "סכום חובה": amount,
                "סכום זכות": amount,
            }
        )

    return pd.DataFrame(rows), errors


# ── Streamlit UI ─────────────────────────────────────────────────────
st.set_page_config(page_title="Zoho → חשבשבת", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1100px}
    div[data-testid="stFileUploader"] {direction: ltr}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 ממיר חשבוניות Zoho → פקודת חשבשבת")
st.markdown("העלי קובץ Excel / CSV מ-Zoho Books וקבלי קובץ מוכן להעלאה לחשבשבת.")

# ── Sidebar settings ─────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ הגדרות חשבונות")
    debit_acct = st.text_input("חשבון חובה (לקוחות חו״ל)", value="200099")
    credit_acct = st.text_input("חשבון זכות (הכנסות)", value="700000")
    st.divider()
    st.markdown("**פורמט תאריך פלט:** DD/MM/YYYY")

# ── File upload ──────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "בחרי קובץ Excel (.xlsx) או CSV",
    type=["xlsx", "xls", "csv"],
    help="קובץ חשבוניות מ-Zoho Books",
)

if uploaded:
    # Read file
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"❌ שגיאה בקריאת הקובץ: {e}")
        st.stop()

    st.success(f"✅ נקלטו **{len(df)}** שורות מתוך **{uploaded.name}**")

    # ── Column mapping ───────────────────────────────────────────────
    st.subheader("🔗 מיפוי עמודות")
    cols = list(df.columns)

    def find_col(keywords, fallback_idx=0):
        """Auto-detect column by keyword match."""
        for kw in keywords:
            for c in cols:
                if kw in c.lower():
                    return cols.index(c)
        return min(fallback_idx, len(cols) - 1)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        col_date = st.selectbox("📅 תאריך", cols, index=find_col(["date"], 0))
    with c2:
        col_invoice = st.selectbox(
            "🔢 מס׳ חשבונית", cols, index=find_col(["invoice_number"], 1)
        )
    with c3:
        col_customer = st.selectbox(
            "👤 שם לקוח", cols, index=find_col(["customer_name"], 2)
        )
    with c4:
        col_amount = st.selectbox(
            "💰 סכום", cols, index=find_col(["bcy_total"], 3)
        )

    # ── Preview raw data ─────────────────────────────────────────────
    with st.expander("📋 תצוגה מקדימה – נתוני מקור", expanded=False):
        st.dataframe(
            df[[col_date, col_invoice, col_customer, col_amount]].head(10),
            use_container_width=True,
        )

    # ── Convert ──────────────────────────────────────────────────────
    if st.button("🔄 המר לפקודת חשבשבת", type="primary", use_container_width=True):
        result_df, errors = convert_df(
            df,
            col_date,
            col_invoice,
            col_customer,
            col_amount,
            debit_acct,
            credit_acct,
        )

        if errors:
            with st.expander(f"⚠️ {len(errors)} שגיאות", expanded=True):
                for e in errors:
                    st.warning(e)

        if not result_df.empty:
            st.subheader("✅ תוצאה – פקודת חשבשבת")
            st.dataframe(result_df, use_container_width=True)

            total = sum(
                float(r.replace(",", "")) for r in result_df["סכום חובה"]
            )
            st.markdown(
                f"**סה״כ שורות:** {len(result_df)}  ·  "
                f"**סכום כולל:** {total:,.2f}"
            )

            # ── Export options ────────────────────────────────────────
            st.divider()
            st.subheader("📥 הורדה")

            exp1, exp2 = st.columns(2)

            # CSV export
            csv_buf = io.StringIO()
            result_df.to_csv(csv_buf, index=False, encoding="utf-8-sig")
            with exp1:
                st.download_button(
                    "⬇️ הורד CSV",
                    csv_buf.getvalue().encode("utf-8-sig"),
                    file_name="hashavshevet_import.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            # Tab-separated TXT export
            txt_lines = []
            for _, row in result_df.iterrows():
                line = "\t".join(str(v) for v in row.values)
                txt_lines.append(line)
            txt_content = "\n".join(txt_lines)
            with exp2:
                st.download_button(
                    "⬇️ הורד TXT (טאב)",
                    txt_content.encode("utf-8-sig"),
                    file_name="hashavshevet_import.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
        else:
            st.error("❌ לא נוצרו שורות – בדקי את הנתונים ומיפוי העמודות.")

else:
    # Show example when no file uploaded
    st.info("👆 העלי קובץ כדי להתחיל")
    st.markdown("### דוגמה")
    example = pd.DataFrame(
        {
            "תאריך": ["05/01/2026"],
            "חשבון חובה": ["200099"],
            "חשבון זכות 1": ["700000"],
            "חשבון זכות 2": [""],
            "פרטים": ["Xebia USA INC."],
            "אסמכתא": ["2540000081"],
            "סכום חובה": ["11,000.00"],
            "סכום זכות": ["11,000.00"],
        }
    )
    st.dataframe(example, use_container_width=True)
