"""Planning Assy Packing - plan shift 1 & 2 dari Excel, actual diisi leader, rekap untuk PPIC."""
from __future__ import annotations

import datetime as dt
import hmac
import os
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import config
import db
import recap
from assy_parser import ParseError, list_sheets, parse_assy

st.set_page_config(page_title="Planning Assy Packing", page_icon="📦", layout="wide")

HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ------------------------------------------------------------------ util
def secret(name: str, default=None):
    val = None
    try:
        val = st.secrets.get(name)
    except Exception:  # tidak ada file secrets sama sekali
        pass
    return val or os.environ.get(name, default)


def today_local() -> dt.date:
    return dt.datetime.now(ZoneInfo(config.TZ_NAME)).date()


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year}"


def clean(v):
    """NaN/None/'' -> None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip() if not isinstance(v, (int, float)) else v
    return s if s != "" else None


@st.cache_resource
def get_engine():
    url = secret("DATABASE_URL") or "sqlite:///planning.db"
    engine = db.make_engine(url)
    db.init_db(engine)
    return engine, url.startswith("sqlite")


# ------------------------------------------------------------------ login
def login_view():
    st.title("📦 Planning Assy Packing")
    ppic_pw, leader_pin = secret("PPIC_PASSWORD"), secret("LEADER_PIN")
    if not ppic_pw and not leader_pin:  # mode lokal / belum ada secrets
        st.session_state.update(role="ppic", user="PPIC", dev_mode=True)
        st.rerun()
    with st.form("login"):
        role = st.radio("Masuk sebagai", ["Leader", "PPIC"], horizontal=True)
        name = st.text_input("Nama leader (untuk Leader)")
        pw = st.text_input("PIN / Password", type="password")
        go = st.form_submit_button("Masuk", type="primary")
    if go:
        expected = leader_pin if role == "Leader" else ppic_pw
        ok = bool(expected) and hmac.compare_digest(str(pw), str(expected))
        if ok and role == "Leader" and not name.strip():
            st.error("Isi nama leader dulu.")
        elif ok:
            st.session_state.update(role=role.lower(), user=name.strip() if role == "Leader" else "PPIC")
            st.rerun()
        else:
            st.error("PIN / password salah.")


# ------------------------------------------------------------------ halaman: input actual
def page_input(engine):
    st.header("Input Actual")
    dates = db.list_dates(engine)
    if not dates:
        st.info("Belum ada plan. PPIC perlu upload Excel planning dulu.")
        return
    today = today_local().isoformat()
    default_idx = next((i for i, d in enumerate(dates) if d >= today), len(dates) - 1)

    c1, c2 = st.columns(2)
    d = c1.selectbox("Tanggal", dates, index=default_idx, format_func=fmt_date)
    shift = c2.radio("Shift", [1, 2], horizontal=True, format_func=lambda s: f"Shift {s}")
    sid = f"{d}_{shift}"

    df = db.load_shift_sheet(engine, d, shift)
    if df.empty:
        st.info("Tidak ada plan untuk tanggal & shift ini.")
        return
    filled = int(df["qty_actual"].notna().sum())
    st.progress(filled / len(df), text=f"Sudah diisi {filled} dari {len(df)} item")

    ver = st.session_state.get(f"ver_{sid}", 0)
    all_ok = st.checkbox("Tandai semua yang belum diisi sebagai 'sesuai plan', lalu ubah yang tidak sesuai",
                         key=f"allok_{sid}_{ver}")
    q = st.text_input("Cari customer / part", key=f"q_{sid}")
    st.caption("Simpan dulu sebelum mengganti kata pencarian, karena isian yang belum disimpan akan hilang.")
    if q.strip():
        mask = (df["customer"].fillna("").str.contains(q, case=False, regex=False)
                | df["part_name"].fillna("").str.contains(q, case=False, regex=False))
        df = df[mask]
    df = df.reset_index(drop=True)
    if df.empty:
        st.info("Tidak ada item yang cocok dengan pencarian.")
        return

    reasons = list(config.REASONS)
    reasons += [r for r in df["reason"].dropna().unique() if r not in reasons]
    view = pd.DataFrame({
        "Customer": df["customer"].fillna(""),
        "Part": df["part_name"],
        "Ket.": df["remarks"].fillna(""),
        "Plan": df["qty_plan"].astype(int),
        "✓ Sesuai plan": df["qty_actual"].isna() & all_ok,
        "Actual": df["qty_actual"].astype("float"),
        "Alasan": df["reason"],
        "Keterangan": df["note"].fillna(""),
    })
    edited = st.data_editor(
        view, hide_index=True, key=f"ed_{sid}_{ver}_{all_ok}_{q}",
        disabled=["Customer", "Part", "Ket.", "Plan"], height=min(740, 38 + 35 * len(view)),
        column_config={
            "Plan": st.column_config.NumberColumn(format="%d"),
            "✓ Sesuai plan": st.column_config.CheckboxColumn(help="Centang = actual sama dengan plan"),
            "Actual": st.column_config.NumberColumn(min_value=0, step=1, format="%d",
                                                    help="Isi kalau berbeda dari plan"),
            "Alasan": st.column_config.SelectboxColumn(options=reasons, help="Wajib kalau actual < plan"),
            "Keterangan": st.column_config.TextColumn(max_chars=200),
        })

    if st.button("💾 Simpan", type="primary"):
        errors, out = [], []
        for i, row in edited.reset_index(drop=True).iterrows():
            plan = int(df.loc[i, "qty_plan"])
            qa = None if pd.isna(row["Actual"]) else int(row["Actual"])
            if qa is None and bool(row["✓ Sesuai plan"]):
                qa = plan
            rs, nt = clean(row["Alasan"]), clean(row["Keterangan"])
            if qa is not None and qa < plan and not rs:
                errors.append(f"{row['Part']}: actual {qa:,} < plan {plan:,}, pilih alasan.")
            out.append({"item_key": df.loc[i, "item_key"], "qty_actual": qa, "reason": rs, "note": nt})
        if errors:
            st.error("Belum bisa disimpan:\n\n" + "\n".join(f"- {e}" for e in errors[:15])
                     + (f"\n- ... dan {len(errors) - 15} lainnya" if len(errors) > 15 else ""))
        else:
            n = db.save_actuals(engine, d, shift, out, st.session_state.get("user", "?"))
            st.session_state[f"ver_{sid}"] = ver + 1
            st.toast(f"Tersimpan ({n} item)", icon="✅")
            st.rerun()


# ------------------------------------------------------------------ halaman: rekap
def page_recap(engine):
    st.header("Rekap Shift 1 → Shift 2")
    dates = db.list_dates(engine)
    if not dates:
        st.info("Belum ada plan.")
        return
    today = today_local().isoformat()
    d = st.selectbox("Tanggal", dates, index=next((i for i, x in enumerate(dates) if x >= today), len(dates) - 1),
                     format_func=fmt_date)
    rec = recap.build_recap(db.load_day(engine, d))
    s = recap.summary(rec)

    m = st.columns(4)
    m[0].metric("Plan S1 → Actual S1", f"{s['actual_s1']:,}", f"dari plan {s['plan_s1']:,}", delta_color="off")
    m[1].metric("Item S1 belum diisi", s["belum_diisi"], f"dari {s['items_s1']} item", delta_color="off")
    m[2].metric("Item kurang (dikejar S2)", s["kurang"], f"{s['dikejar_total']:,} pcs", delta_color="off")
    m[3].metric("Target S2", f"{s['target_s2']:,}", f"plan S2 {s['plan_s2']:,}", delta_color="off")

    pilih = st.radio("Tampilkan", ["Semua", "Perlu perhatian", "S1 belum diisi"], horizontal=True)
    if pilih == "Perlu perhatian":
        rec = rec[rec["status"].isin(["Kurang S1, tambah di S2", "Kurang S1, belum ada plan S2", "Di-drop"])]
    elif pilih == "S1 belum diisi":
        rec = rec[rec["status"] == "S1 belum diisi"]

    names = {"customer": "Customer", "part_name": "Part", "remarks": "Remarks", "plan_s1": "Plan S1",
             "actual_s1": "Actual S1", "sisa_s1": "Sisa S1", "alasan_s1": "Alasan S1", "ket_s1": "Keterangan S1",
             "plan_s2": "Plan S2", "dikejar_s2": "Dikejar di S2", "target_s2": "Target S2", "status": "Status"}
    show = rec.rename(columns=names)

    def color(row):
        st_ = row["Status"]
        bg = ("rgba(255,70,70,0.20)" if st_.startswith("Kurang") else
              "rgba(255,200,0,0.20)" if st_ == "S1 belum diisi" else
              "rgba(150,150,150,0.20)" if st_ == "Di-drop" else "")
        return [f"background-color: {bg}" if bg else ""] * len(row)

    num = ["Plan S1", "Actual S1", "Sisa S1", "Plan S2", "Dikejar di S2", "Target S2"]
    st.dataframe(show.style.apply(color, axis=1).format({c: "{:,.0f}" for c in num}, na_rep="-"),
                 hide_index=True, height=min(760, 40 + 35 * max(len(show), 3)))
    st.caption("Target S2 = Plan S2 + sisa S1 yang masih harus dikejar. Sisa tidak dikejar kalau alasannya "
               "'Part tidak terpakai / di-drop'. Item yang kurang tapi belum ada di plan S2 ditandai merah.")
    st.download_button("⬇️ Unduh Excel", recap.to_excel(rec), file_name=f"rekap_{d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------ halaman: upload plan
@st.cache_data(show_spinner="Membaca Excel...", max_entries=3)
def cached_parse(data: bytes, sheet: str, excl: tuple, mode: str, from_date):
    return parse_assy(data, sheet, list(excl), mode, from_date)


def page_upload(engine):
    st.header("Upload Plan")
    f = st.file_uploader("File Excel planning", type=["xlsx"])
    if f is None:
        st.caption("Upload file planning (sheet ASSY). Plan lama untuk tanggal yang sama akan diperbarui; "
                   "actual yang sudah diisi leader tidak hilang.")
        last = db.last_uploads(engine)
        if len(last):
            st.subheader("Upload terakhir")
            st.dataframe(last, hide_index=True)
        return
    data = f.getvalue()
    sheets = list_sheets(data)
    sheet = st.selectbox("Sheet", sheets, index=sheets.index(config.DEFAULT_SHEET) if config.DEFAULT_SHEET in sheets else 0)
    with st.expander("Pengaturan baca", expanded=False):
        mode_label = st.radio("Kolom yang dibaca",
                              ["Yang tampil (tidak di-hide)", "Mulai tanggal tertentu", "Semua kolom"])
        mode = {"Yang tampil (tidak di-hide)": "visible", "Mulai tanggal tertentu": "from_date",
                "Semua kolom": "all"}[mode_label]
        from_date = st.date_input("Mulai tanggal", value=today_local()) if mode == "from_date" else None
        excl_text = st.text_area("Lewati baris yang nama part-nya mengandung frasa ini (satu per baris)",
                                 "\n".join(config.DEFAULT_EXCLUDE))
    excl = tuple(x.strip() for x in excl_text.splitlines() if x.strip())

    try:
        res = cached_parse(data, sheet, excl, mode, from_date)
    except ParseError as e:
        st.error(str(e))
        return
    except Exception as e:  # noqa: BLE001
        st.error(f"Gagal membaca file: {e}")
        return

    read = res.columns[res.columns["dibaca"]]
    st.caption(res.period_text)
    m = st.columns(4)
    m[0].metric("Kolom tanggal/shift", len(read))
    m[1].metric("Item ber-plan", len(res.items))
    m[2].metric("Baris plan", len(res.plans))
    m[3].metric("Baris dilewati", len(res.excluded))
    for w in res.warnings:
        st.warning(w)

    st.subheader("Validasi total per kolom")
    view = read[["kolom", "tanggal", "shift", "kode_lot", "total_excel", "total_dibaca", "total_stay_dibuang", "status"]].copy()
    view["tanggal"] = view["tanggal"].apply(lambda x: fmt_date(x.isoformat()))
    st.dataframe(view.rename(columns={"total_excel": "Total di Excel", "total_dibaca": "Total dibaca",
                                      "total_stay_dibuang": "Total dilewati"}),
                 hide_index=True, height=min(500, 40 + 35 * max(len(view), 3)))
    st.caption("'OK (selisih = baris stay)' artinya total di Excel = total dibaca + baris yang dilewati.")

    with st.expander(f"Baris yang dilewati ({len(res.excluded)})"):
        st.dataframe(res.excluded, hide_index=True)
    if len(res.duplicates):
        with st.expander(f"Part kembar ({len(res.duplicates)} baris)"):
            st.dataframe(res.duplicates, hide_index=True)
    with st.expander("Pratinjau item"):
        st.dataframe(res.items.drop(columns=["sort_order"]), hide_index=True)

    has_check = bool((read["status"] == "CEK").any())
    sure = True
    if has_check:
        sure = st.checkbox("Total ada yang tidak cocok, saya sudah cek dan tetap mau simpan")
    if st.button("💾 Simpan ke database", type="primary", disabled=not (len(res.plans) and sure)):
        stats = db.save_plan(engine, res.items, res.plans, read,
                             {"filename": f.name, "period_text": res.period_text,
                              "uploaded_by": st.session_state.get("user", "PPIC")})
        st.success(f"Tersimpan: {stats['items']} item, {stats['plan_rows']} baris plan"
                   + (f", {stats['zeroed']} plan dihapus di revisi ini (plan di-nol-kan, actual tetap aman)."
                      if stats["zeroed"] else "."))


# ------------------------------------------------------------------ main
def main():
    if "role" not in st.session_state:
        login_view()
        return
    engine, is_sqlite = get_engine()
    role = st.session_state["role"]

    with st.sidebar:
        st.markdown(f"**{st.session_state.get('user', '')}** ({role})")
        if st.button("Keluar"):
            for k in ("role", "user", "dev_mode"):
                st.session_state.pop(k, None)
            st.rerun()
        page = "Input Actual"
        if role == "ppic":
            page = st.radio("Halaman", ["Input Actual", "Rekap Shift", "Upload Plan"])

    if role == "ppic" and is_sqlite:
        st.warning("Database masih SQLite lokal: data bisa hilang saat app restart/redeploy. "
                   "Isi DATABASE_URL di Secrets supaya data permanen.")
    if st.session_state.get("dev_mode"):
        st.info("Mode lokal: belum ada PPIC_PASSWORD / LEADER_PIN di Secrets, jadi tanpa login.")

    {"Input Actual": page_input, "Rekap Shift": page_recap, "Upload Plan": page_upload}[page](engine)


main()
