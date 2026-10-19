"""Planning Assy Packing - plan shift 1 & 2 dari Excel, actual diisi leader, rekap untuk PPIC."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import config
import db
import recap
import ui
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
    return db.make_engine(url), url.startswith("sqlite")


@st.cache_resource
def ensure_schema(_engine, version: str):
    """Buat tabel yang belum ada. Dijalankan ulang otomatis saat daftar tabel (SCHEMA_VERSION) berubah."""
    db.init_db(_engine)
    return version


# ------------------------------------------------------------------ login
def login_view():
    ui.header("Planning Assy Packing", "Masuk dulu")
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
def _wkey(prefix, sid, ver, item_key):
    return f"{prefix}_{sid}_{ver}_{hashlib.md5(item_key.encode()).hexdigest()[:10]}"


def idn_(n):
    return ui.idn(n)


def _render_item(r, sid, ver, reasons, fields, prio=False):
    """Satu kartu item: Sesuai plan, penyebab 4M, Actual, Ket. 4M. Item prioritas berwarna ungu."""
    ik, plan = r["item_key"], int(r["qty_plan"])
    sa = None if pd.isna(r["qty_actual"]) else int(r["qty_actual"])
    rs0 = r["reason"] if isinstance(r["reason"], str) and r["reason"] in reasons else None
    box = st.container(border=True, key=_wkey("prio", sid, ver, ik)) if prio else st.container(border=True)
    with box:
        st.markdown(ui.item_head(r["part_name"], r["remarks"], plan, ui.status_html(plan, sa), prio), unsafe_allow_html=True)
        ok = st.checkbox("✓ Sesuai plan", value=(rs0 is None and sa is not None and sa == plan), key=_wkey("ok", sid, ver, ik))
        st.caption("Kurang dari plan? Pilih penyebab 4M, lalu isi Actual:")
        r4 = st.segmented_control("Penyebab 4M", reasons, default=rs0, key=_wkey("m4", sid, ver, ik),
                                  label_visibility="collapsed")
        v = st.number_input("Actual", min_value=0, step=1, value=sa if sa is not None and sa != plan else None,
                            placeholder="Actual (kalau beda dari plan)", key=_wkey("act", sid, ver, ik),
                            label_visibility="collapsed")
        note = st.text_input("Ket. 4M", value=clean(r["note"]) or "", placeholder="Ket. 4M: jelaskan penyebabnya",
                             key=_wkey("note", sid, ver, ik), label_visibility="collapsed")
    fields[ik] = (r["part_name"], plan, sa, rs0, clean(r["note"]), ok, r4, v, note)


def page_input(engine):
    top = st.container()
    dates = db.list_dates(engine)
    if not dates:
        with top:
            ui.header("Input Actual", "Belum ada plan")
        st.info("Belum ada plan. PPIC perlu upload Excel planning dulu.")
        return
    today = today_local().isoformat()
    default_idx = next((i for i, d in enumerate(dates) if d >= today), len(dates) - 1)

    c1, c2 = st.columns([3, 2])
    d = c1.selectbox("Tanggal", dates, index=default_idx, format_func=fmt_date)
    shift = c2.radio("Shift", [1, 2], horizontal=True, format_func=lambda s: f"Shift {s}")
    sid = f"{d}_{shift}"
    with top:
        ui.header("Input Actual", f"{fmt_date(d)} · Shift {shift}")

    df_all = db.load_shift_sheet(engine, d, shift)
    if df_all.empty:
        st.info("Tidak ada plan untuk tanggal & shift ini.")
        return

    act = df_all["qty_actual"]
    n_belum = int(act.isna().sum())
    n_kurang = int((act < df_all["qty_plan"]).sum())
    n_ok = len(df_all) - n_belum - n_kurang
    ui.board(n_ok, n_kurang, n_belum)
    prio_all = df_all[df_all["is_priority"] == 1]
    if len(prio_all):
        ui.prio_callout(len(prio_all), int(prio_all["qty_actual"].notna().sum()),
                        sub="Kartu ungu di bawah. Wajib dikerjakan dan diisi.")

    ver = st.session_state.get(f"ver_{sid}", 0)
    f1, f2 = st.columns([3, 3])
    view_default = "Belum diisi" if n_belum else "Per customer"
    view = f1.segmented_control("Tampilkan", ["Belum diisi", "Per customer", "Daftar semua"], default=view_default,
                                key=f"view_{sid}") or view_default
    q = f2.text_input("Cari customer / part", key=f"q_{sid}", placeholder="Ketik lalu Enter")
    df = df_all
    if view == "Belum diisi":
        df = df[df["qty_actual"].isna()]
    if q.strip():
        mask = (df["customer"].fillna("").str.contains(q, case=False, regex=False)
                | df["part_name"].fillna("").str.contains(q, case=False, regex=False))
        df = df[mask]
    df = df.reset_index(drop=True)
    msg = st.container()
    if df.empty:
        st.success("Semua item sudah terisi. Pilih 'Per customer' atau 'Daftar semua' untuk melihat atau mengubah.") \
            if not q.strip() and view == "Belum diisi" else st.info("Tidak ada item yang cocok.")
        return
    st.caption("Sesuai plan: centang. Kurang: pilih 4M, isi Actual, jelaskan di Ket. 4M. "
               "Simpan dulu sebelum ganti pencarian atau tanggal.")

    reasons = list(config.REASONS)
    fields = {}
    with st.form(f"form_{sid}_{ver}", border=False):
        top_submit = st.form_submit_button("Simpan semua", type="primary", key=f"s1_{sid}_{ver}", width="stretch")

        prio_df = df[df["is_priority"] == 1]
        rest = df[df["is_priority"] != 1]
        if len(prio_df):
            done = int(prio_all["qty_actual"].notna().sum())
            with st.expander(f"⭐ PRIORITAS: jangan di-skip ({done}/{len(prio_all)} terisi)", expanded=True):
                for _, r in prio_df.iterrows():
                    _render_item(r, sid, ver, reasons, fields, prio=True)

        if view == "Daftar semua":
            for _, r in rest.iterrows():
                _render_item(r, sid, ver, reasons, fields)
        else:
            for cust in dict.fromkeys(rest["customer"].fillna("").tolist()):
                sub = rest[rest["customer"].fillna("") == cust]
                full = df_all[df_all["customer"].fillna("") == cust]
                dn = int(full["qty_actual"].notna().sum())
                low = bool((full["qty_actual"] < full["qty_plan"]).any())
                lamp = "🔴" if low else ("🟢" if dn == len(full) else "🟡")
                with st.expander(f"{lamp} {cust or '(tanpa customer)'}  ({dn}/{len(full)} terisi)", expanded=True):
                    for _, r in sub.iterrows():
                        _render_item(r, sid, ver, reasons, fields)
        bottom_submit = st.form_submit_button("Simpan semua", type="primary", key=f"s2_{sid}_{ver}", width="stretch")

    if top_submit or bottom_submit:
        errors, out = [], []
        for ik, (part, plan, sa, rs0, note0, ok, r4, v, note) in fields.items():
            v = None if v is None else int(v)
            note = (clean(note) or "")
            note = note.upper() if note else None
            qa, rs = None, None
            if ok and r4:
                errors.append(f"{part}: pilih salah satu, Sesuai plan atau penyebab 4M.")
                continue
            if ok:
                if v is not None and v < plan:
                    errors.append(f"{part}: Actual {idn_(v)} lebih kecil dari plan, hilangkan centang Sesuai plan dan pilih 4M.")
                    continue
                qa = v if v is not None else plan
            elif r4:
                if v is None:
                    errors.append(f"{part}: isi Actual (kurang dari {idn_(plan)}).")
                    continue
                if v >= plan:
                    errors.append(f"{part}: penyebab 4M dipilih tapi Actual {idn_(v)} tidak kurang dari plan.")
                    continue
                qa, rs = v, r4
            elif v is not None:
                if v < plan:
                    errors.append(f"{part}: Actual {idn_(v)} < plan {idn_(plan)}, pilih penyebab 4M.")
                    continue
                qa = v
            new = (qa, rs, note)
            old = (sa, rs0, (note0.upper() if note0 else None))
            if new != old:
                out.append({"item_key": ik, "qty_actual": qa, "reason": rs, "note": note})
        with msg:
            if errors:
                st.error("Belum bisa disimpan:\n\n" + "\n".join(f"- {e}" for e in errors[:12])
                         + (f"\n- ... dan {len(errors) - 12} lainnya" if len(errors) > 12 else ""))
            elif not out:
                st.info("Tidak ada perubahan untuk disimpan.")
            else:
                n = db.save_actuals(engine, d, shift, out, st.session_state.get("user", "?"))
                st.session_state[f"ver_{sid}"] = ver + 1
                st.toast(f"Tersimpan ({n} item)", icon="✅")
                st.rerun()


# ------------------------------------------------------------------ halaman: prioritas (PPIC)
def page_priority(engine):
    top = st.container()
    dates = db.list_dates(engine)
    if not dates:
        with top:
            ui.header("Prioritas Packing", "Belum ada plan")
        st.info("Belum ada plan. Upload Excel planning dulu.")
        return
    today = today_local().isoformat()
    c1, c2 = st.columns([3, 2])
    d = c1.selectbox("Tanggal", dates, index=next((i for i, x in enumerate(dates) if x >= today), len(dates) - 1),
                     format_func=fmt_date, key="pr_date")
    shift = c2.radio("Shift", [1, 2], horizontal=True, format_func=lambda s: f"Shift {s}", key="pr_shift")
    sid = f"{d}_{shift}"
    with top:
        ui.header("Prioritas Packing", f"{fmt_date(d)} · Shift {shift}")

    df_all = db.load_shift_sheet(engine, d, shift)
    df_all = df_all[df_all["qty_plan"] > 0].reset_index(drop=True)
    if df_all.empty:
        st.info("Tidak ada plan untuk tanggal & shift ini.")
        return
    n_prio = int((df_all["is_priority"] == 1).sum())
    st.markdown(f'<div class="pcall"><div><div class="pcall-t">Tandai item yang wajib di-packing</div>'
                f'<div class="pcall-s">Di halaman leader, item ini muncul paling atas dengan warna ungu.</div></div>'
                f'<div class="pcall-n">{n_prio}<small>item prioritas</small></div></div>', unsafe_allow_html=True)

    ver = st.session_state.get(f"prver_{sid}", 0)
    f1, f2 = st.columns([2, 3])
    only = f1.segmented_control("Tampilkan", ["Semua", "Hanya prioritas"], default="Semua", key=f"pronly_{sid}")
    q = f2.text_input("Cari customer / part", key=f"prq_{sid}", placeholder="Ketik lalu Enter")
    df = df_all
    if only == "Hanya prioritas":
        df = df[df["is_priority"] == 1]
    if q.strip():
        mask = (df["customer"].fillna("").str.contains(q, case=False, regex=False)
                | df["part_name"].fillna("").str.contains(q, case=False, regex=False))
        df = df[mask]
    df = df.reset_index(drop=True)
    if df.empty:
        st.info("Tidak ada item yang cocok.")
        return

    other = 2 if shift == 1 else 1
    both = st.checkbox(f"Berlaku juga untuk Shift {other} di tanggal ini (perubahan centang ikut diterapkan)", key=f"prboth_{sid}")
    view = pd.DataFrame({
        "Prioritas": df["is_priority"] == 1,
        "Customer": df["customer"].fillna(""),
        "Part": df["part_name"],
        "Ket.": df["remarks"].fillna(""),
        "Plan": df["qty_plan"].astype(int),
    })
    edited = st.data_editor(view, hide_index=True, key=f"pred_{sid}_{ver}_{only}_{q}",
                            disabled=["Customer", "Part", "Ket.", "Plan"], height=min(720, 40 + 35 * len(view)),
                            column_config={"Prioritas": st.column_config.CheckboxColumn("⭐ Prioritas", width="small"),
                                           "Plan": st.column_config.NumberColumn(format="%d")})
    st.caption("Centang item yang prioritas, lalu Simpan. Simpan dulu sebelum mengganti pencarian atau tanggal.")
    if st.button("💾 Simpan prioritas", type="primary"):
        edited = edited.reset_index(drop=True)
        checked = [df.loc[i, "item_key"] for i in range(len(edited)) if bool(edited.loc[i, "Prioritas"])]
        in_view = list(df["item_key"])
        db.save_priorities(engine, d, [shift, other] if both else [shift], checked, in_view,
                           st.session_state.get("user", "PPIC"))
        st.session_state[f"prver_{sid}"] = ver + 1
        st.toast(f"Tersimpan ({len(checked)} item prioritas)", icon="⭐")
        st.rerun()


# ------------------------------------------------------------------ halaman: rekap
def page_recap(engine):
    dates = db.list_dates(engine)
    if not dates:
        ui.header("Rekap Shift 1 → Shift 2", "Belum ada plan")
        st.info("Belum ada plan.")
        return
    today = today_local().isoformat()
    top = st.container()
    d = st.selectbox("Tanggal", dates, index=next((i for i, x in enumerate(dates) if x >= today), len(dates) - 1),
                     format_func=fmt_date)
    with top:
        ui.header("Rekap Shift 1 → Shift 2", fmt_date(d))
    rec = recap.build_recap(db.load_day(engine, d))
    s = recap.summary(rec)
    ui.strip(s["plan_s1"], s["actual_s1"], s["belum_diisi"], s["items_s1"], s["kurang"], s["dikejar_total"],
             s["plan_s2"], s["target_s2"])

    if s["prio_items"]:
        st.markdown(f'<div class="pcall"><div><div class="pcall-t">{s["prio_items"]} item prioritas hari ini</div>'
                    f'<div class="pcall-s">{s["prio_masalah"]} bermasalah: kurang di shift 1 atau belum diisi leader.</div></div>'
                    f'<div class="pcall-n">{s["prio_masalah"]}<small>perlu dicek</small></div></div>', unsafe_allow_html=True)
    kurang = rec[rec["dikejar_s2"] > 0].sort_values(["prioritas", "dikejar_s2"], ascending=[False, False])
    belum = rec[rec["status"] == "S1 belum diisi"].sort_values("prioritas", ascending=False)
    t1, t2, t3 = st.tabs([f"Perlu dikejar ({len(kurang)})", f"Belum diisi ({len(belum)})", "Semua item"])

    with t1:
        if kurang.empty:
            st.markdown('<div class="empty">Tidak ada kekurangan di shift 1. Plan shift 2 bisa jalan apa adanya.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="sec">Penyebab kekurangan (4M)</div>' + ui.m4_bars(kurang, config.REASONS),
                        unsafe_allow_html=True)
            st.markdown('<div class="sec">Item yang harus dikejar di shift 2</div>', unsafe_allow_html=True)
            st.markdown("".join(ui.shortfall_row(r) for _, r in kurang.iterrows()), unsafe_allow_html=True)
            st.caption("Merah tua = item kurang yang belum ada di plan shift 2, jadi perlu ditambahkan ke planning.")
    with t2:
        if belum.empty:
            st.markdown('<div class="empty">Semua item shift 1 sudah diisi leader.</div>', unsafe_allow_html=True)
        else:
            st.caption("Leader belum mengisi item berikut:")
            st.markdown("".join(
                f'<div class="row{" prio" if r["prioritas"] else ""}" style="border-left-color:{"#6A2FB5" if r["prioritas"] else "#F0A800"}"><div class="row-l"><div class="row-p">{ui.esc(r["part_name"])}{" <span class=pbadge>PRIORITAS</span>" if r["prioritas"] else ""}</div>'
                f'<div class="row-c">{ui.esc(r["customer"]) or "(tanpa customer)"}</div></div>'
                f'<div class="row-r"><div class="row-big" style="color:#1C2B39">{ui.idn(r["plan_s1"])}</div>'
                f'<div class="row-s2">plan S1</div></div></div>' for _, r in belum.iterrows()), unsafe_allow_html=True)
    with t3:
        names = {"customer": "Customer", "part_name": "Part", "remarks": "Remarks", "prioritas": "Prioritas", "plan_s1": "Plan S1",
                 "actual_s1": "Actual S1", "sisa_s1": "Sisa S1", "alasan_s1": "Alasan S1", "ket_s1": "Ket. 4M S1",
                 "plan_s2": "Plan S2", "dikejar_s2": "Dikejar di S2", "target_s2": "Target S2", "status": "Status"}
        show = rec.assign(prioritas=rec["prioritas"].map({True: "⭐", False: ""})).rename(columns=names)

        def color(row):
            st_ = row["Status"]
            bg = ("rgba(214,64,64,0.16)" if st_.startswith("Kurang") else
                  "rgba(240,168,0,0.18)" if st_ == "S1 belum diisi" else "")
            return [f"background-color: {bg}" if bg else ""] * len(row)

        num = ["Plan S1", "Actual S1", "Sisa S1", "Plan S2", "Dikejar di S2", "Target S2"]
        st.dataframe(show.style.apply(color, axis=1).format({c: ui.idn for c in num}, na_rep="-"),
                     hide_index=True, height=min(700, 40 + 35 * max(len(show), 3)))
    st.download_button("⬇️ Unduh rekap (Excel)", recap.to_excel(rec), file_name=f"rekap_{d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ------------------------------------------------------------------ halaman: upload plan
@st.cache_data(show_spinner="Membaca Excel...", max_entries=3)
def cached_parse(data: bytes, sheet: str, excl: tuple, mode: str, from_date):
    return parse_assy(data, sheet, list(excl), mode, from_date)


def page_upload(engine):
    ui.header("Upload Plan", "PPIC · baca Excel planning")
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
    ui.inject_css()
    if "role" not in st.session_state:
        login_view()
        return
    engine, is_sqlite = get_engine()
    ensure_schema(engine, db.SCHEMA_VERSION)
    role = st.session_state["role"]

    with st.sidebar:
        st.markdown(f"**{st.session_state.get('user', '')}** ({role})")
        if st.button("Keluar"):
            for k in ("role", "user", "dev_mode"):
                st.session_state.pop(k, None)
            st.rerun()
        page = "Input Actual"
        if role == "ppic":
            page = st.radio("Halaman", ["Input Actual", "Rekap Shift", "Prioritas", "Upload Plan"])

    if role == "ppic" and is_sqlite:
        st.warning("Database masih SQLite lokal: data bisa hilang saat app restart/redeploy. "
                   "Isi DATABASE_URL di Secrets supaya data permanen.")
    if st.session_state.get("dev_mode"):
        st.info("Mode lokal: belum ada PPIC_PASSWORD / LEADER_PIN di Secrets, jadi tanpa login.")

    {"Input Actual": page_input, "Rekap Shift": page_recap, "Prioritas": page_priority,
     "Upload Plan": page_upload}[page](engine)


main()
