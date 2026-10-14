"""Logika rekap: sisa shift 1 -> kebutuhan shift 2."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from config import DROP_REASONS

COLS = ["customer", "part_name", "remarks", "prioritas", "plan_s1", "actual_s1", "sisa_s1", "alasan_s1", "ket_s1",
        "plan_s2", "dikejar_s2", "target_s2", "status"]


def build_recap(day: pd.DataFrame) -> pd.DataFrame:
    """day: keluaran db.load_day (baris per item per shift)."""
    if day.empty:
        return pd.DataFrame(columns=COLS)
    s1 = day[day["shift"] == 1].set_index("item_key")
    s2 = day[day["shift"] == 2].set_index("item_key")
    info = day.drop_duplicates("item_key").set_index("item_key")[["customer", "part_name", "remarks", "sort_order"]]
    out = info.copy()
    out["plan_s1"] = s1["qty_plan"].reindex(out.index).fillna(0).astype(int)
    out["actual_s1"] = s1["qty_actual"].reindex(out.index)
    out["alasan_s1"] = s1["reason"].reindex(out.index)
    out["ket_s1"] = s1["note"].reindex(out.index)
    out["plan_s2"] = s2["qty_plan"].reindex(out.index).fillna(0).astype(int)
    p1 = s1["is_priority"].reindex(out.index).fillna(0).astype(int) if "is_priority" in s1 else 0
    p2 = s2["is_priority"].reindex(out.index).fillna(0).astype(int) if "is_priority" in s2 else 0
    out["prioritas"] = (p1 + p2) > 0

    filled = out["actual_s1"].notna()
    out["sisa_s1"] = np.where(out["plan_s1"] > 0, np.where(filled, out["plan_s1"] - out["actual_s1"], np.nan), np.nan)
    dropped = out["alasan_s1"].isin(DROP_REASONS)
    short = out["sisa_s1"].fillna(0) > 0
    out["dikejar_s2"] = np.where(short & ~dropped, out["sisa_s1"], 0).astype(int)
    out["target_s2"] = out["plan_s2"] + out["dikejar_s2"]

    def status(r):
        if r["plan_s1"] > 0 and pd.isna(r["actual_s1"]):
            return "S1 belum diisi"
        if r["plan_s1"] > 0 and r["alasan_s1"] in DROP_REASONS and r["sisa_s1"] > 0:
            return "Di-drop"
        if r["dikejar_s2"] > 0 and r["plan_s2"] == 0:
            return "Kurang S1, belum ada plan S2"
        if r["dikejar_s2"] > 0:
            return "Kurang S1, tambah di S2"
        if r["plan_s1"] > 0 and r["sisa_s1"] < 0:
            return "Lebih"
        return "Sesuai" if r["plan_s1"] > 0 else ""

    out["status"] = out.apply(status, axis=1)
    return out.sort_values("sort_order")[COLS].reset_index(drop=True)


def summary(rec: pd.DataFrame) -> dict:
    s1 = rec[rec["plan_s1"] > 0]
    pr = rec[rec["prioritas"].astype(bool)]
    return {
        "prio_items": len(pr),
        "prio_masalah": int(((pr["dikejar_s2"] > 0) | (pr["status"] == "S1 belum diisi")).sum()),
        "items_s1": len(s1),
        "belum_diisi": int((s1["actual_s1"].isna()).sum()),
        "kurang": int((rec["dikejar_s2"] > 0).sum()),
        "dikejar_total": int(rec["dikejar_s2"].sum()),
        "plan_s1": int(rec["plan_s1"].sum()),
        "actual_s1": int(rec.loc[rec["plan_s1"] > 0, "actual_s1"].fillna(0).sum()),
        "plan_s2": int(rec["plan_s2"].sum()),
        "target_s2": int(rec["target_s2"].sum()),
    }


def to_excel(rec: pd.DataFrame) -> bytes:
    names = {"customer": "Customer", "part_name": "Part", "remarks": "Remarks", "prioritas": "Prioritas", "plan_s1": "Plan S1",
             "actual_s1": "Actual S1", "sisa_s1": "Sisa S1", "alasan_s1": "Alasan S1", "ket_s1": "Ket. 4M S1",
             "plan_s2": "Plan S2", "dikejar_s2": "Dikejar di S2", "target_s2": "Target S2", "status": "Status"}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out = rec.copy()
        out["prioritas"] = out["prioritas"].map({True: "YA", False: ""})
        out.rename(columns=names).to_excel(xw, index=False, sheet_name="Rekap")
        ws = xw.sheets["Rekap"]
        for col, w in zip("ABCDEFGHIJKLM", (30, 36, 24, 10, 10, 10, 10, 32, 28, 10, 13, 11, 28)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "E2"
    return buf.getvalue()
