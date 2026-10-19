"""Lapisan database. SQLite (lokal/dev) atau PostgreSQL (Supabase, dll) lewat SQLAlchemy.

Semua SQL dibuat portabel: tanggal disimpan sebagai teks ISO (YYYY-MM-DD),
kunci utama berupa teks (tanpa autoincrement), upsert pakai ON CONFLICT.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pandas as pd
from sqlalchemy import create_engine, text

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS items (
        item_key TEXT PRIMARY KEY, customer TEXT, part_name TEXT, remarks TEXT, sort_order INTEGER)""",
    """CREATE TABLE IF NOT EXISTS plans (
        item_key TEXT NOT NULL, plan_date TEXT NOT NULL, shift INTEGER NOT NULL,
        qty_plan INTEGER NOT NULL, lot_code TEXT,
        PRIMARY KEY (item_key, plan_date, shift))""",
    """CREATE TABLE IF NOT EXISTS actuals (
        item_key TEXT NOT NULL, plan_date TEXT NOT NULL, shift INTEGER NOT NULL,
        qty_actual INTEGER, reason TEXT, note TEXT, input_by TEXT, updated_at TEXT,
        PRIMARY KEY (item_key, plan_date, shift))""",
    """CREATE TABLE IF NOT EXISTS priorities (
        item_key TEXT NOT NULL, plan_date TEXT NOT NULL, shift INTEGER NOT NULL,
        marked_by TEXT, updated_at TEXT,
        PRIMARY KEY (item_key, plan_date, shift))""",
    """CREATE TABLE IF NOT EXISTS locks (
        item_key TEXT NOT NULL, plan_date TEXT NOT NULL, shift INTEGER NOT NULL,
        locked_by TEXT, locked_at TEXT,
        PRIMARY KEY (item_key, plan_date, shift))""",
    """CREATE TABLE IF NOT EXISTS audit (
        log_id TEXT PRIMARY KEY, plan_date TEXT, shift INTEGER, item_key TEXT, action TEXT,
        old_actual INTEGER, new_actual INTEGER, old_reason TEXT, new_reason TEXT,
        old_note TEXT, new_note TEXT, by_user TEXT, at TEXT)""",
    """CREATE TABLE IF NOT EXISTS uploads (
        upload_id TEXT PRIMARY KEY, filename TEXT, period_text TEXT, uploaded_by TEXT,
        uploaded_at TEXT, n_items INTEGER, n_plan_rows INTEGER, date_from TEXT, date_to TEXT)""",
]


# berubah otomatis kalau daftar tabel di SCHEMA berubah, supaya app membuat tabel baru tanpa restart manual
SCHEMA_VERSION = hashlib.md5("".join(SCHEMA).encode()).hexdigest()[:8]


def make_engine(url: str):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


def init_db(engine):
    with engine.begin() as conn:
        for stmt in SCHEMA:
            conn.execute(text(stmt))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list dict dengan NaN diganti None dan tipe numpy jadi tipe Python."""
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
                    for k, v in rec.items()})
    return out


# ------------------------------------------------------------------ upload plan
def save_plan(engine, items: pd.DataFrame, plans: pd.DataFrame, columns_read: pd.DataFrame,
              meta: dict) -> dict:
    """Simpan hasil parse. Plan di kolom (tanggal, shift) yang dibaca tapi tidak ada lagi
    di file baru di-nol-kan (bukan dihapus) supaya actual yang sudah diisi tidak hilang."""
    pairs = {(d.isoformat(), int(s)) for d, s in zip(columns_read["tanggal"], columns_read["shift"])}
    new_keys = {(r.item_key, r.plan_date, int(r.shift)) for r in plans.itertuples()}
    stats = {"items": len(items), "plan_rows": len(plans), "zeroed": 0}
    with engine.begin() as conn:
        if len(items):
            conn.execute(text("""
                INSERT INTO items (item_key, customer, part_name, remarks, sort_order)
                VALUES (:item_key, :customer, :part_name, :remarks, :sort_order)
                ON CONFLICT (item_key) DO UPDATE SET customer=excluded.customer,
                    part_name=excluded.part_name, remarks=excluded.remarks, sort_order=excluded.sort_order
            """), _records(items))
        if pairs:
            dmin, dmax = min(p[0] for p in pairs), max(p[0] for p in pairs)
            old = conn.execute(text(
                "SELECT item_key, plan_date, shift FROM plans WHERE plan_date >= :a AND plan_date <= :b AND qty_plan > 0"),
                {"a": dmin, "b": dmax}).fetchall()
            gone = [{"k": k, "d": d, "s": s} for k, d, s in old
                    if (d, s) in pairs and (k, d, s) not in new_keys]
            if gone:
                conn.execute(text("UPDATE plans SET qty_plan=0 WHERE item_key=:k AND plan_date=:d AND shift=:s"), gone)
            stats["zeroed"] = len(gone)
        if len(plans):
            conn.execute(text("""
                INSERT INTO plans (item_key, plan_date, shift, qty_plan, lot_code)
                VALUES (:item_key, :plan_date, :shift, :qty_plan, :lot_code)
                ON CONFLICT (item_key, plan_date, shift) DO UPDATE SET
                    qty_plan=excluded.qty_plan, lot_code=excluded.lot_code
            """), _records(plans))
        dates = sorted(p[0] for p in pairs)
        conn.execute(text("""
            INSERT INTO uploads (upload_id, filename, period_text, uploaded_by, uploaded_at,
                                 n_items, n_plan_rows, date_from, date_to)
            VALUES (:id, :fn, :pt, :by, :at, :ni, :np, :d1, :d2)"""),
            {"id": _now() + "|" + str(len(plans)), "fn": meta.get("filename"), "pt": meta.get("period_text"),
             "by": meta.get("uploaded_by"), "at": _now(), "ni": len(items), "np": len(plans),
             "d1": dates[0] if dates else None, "d2": dates[-1] if dates else None})
    return stats


def last_uploads(engine, n=5) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text("SELECT filename, period_text, uploaded_at, n_items, date_from, date_to "
                                "FROM uploads ORDER BY uploaded_at DESC LIMIT :n"), conn, params={"n": n})


# ------------------------------------------------------------------ baca
def list_dates(engine) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT plan_date FROM plans WHERE qty_plan > 0 ORDER BY plan_date")).fetchall()
    return [r[0] for r in rows]


def load_shift_sheet(engine, plan_date: str, shift: int) -> pd.DataFrame:
    sql = """
        SELECT i.item_key, i.customer, i.part_name, i.remarks, i.sort_order, p.qty_plan,
               a.qty_actual, a.reason, a.note, a.input_by, a.updated_at,
               CASE WHEN pr.item_key IS NULL THEN 0 ELSE 1 END AS is_priority,
               CASE WHEN lk.item_key IS NULL THEN 0 ELSE 1 END AS is_locked
        FROM plans p
        JOIN items i ON i.item_key = p.item_key
        LEFT JOIN actuals a ON a.item_key = p.item_key AND a.plan_date = p.plan_date AND a.shift = p.shift
        LEFT JOIN priorities pr ON pr.item_key = p.item_key AND pr.plan_date = p.plan_date AND pr.shift = p.shift
        LEFT JOIN locks lk ON lk.item_key = p.item_key AND lk.plan_date = p.plan_date AND lk.shift = p.shift
        WHERE p.plan_date = :d AND p.shift = :s AND (p.qty_plan > 0 OR a.qty_actual IS NOT NULL)
        ORDER BY i.sort_order, i.item_key"""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"d": plan_date, "s": int(shift)})


def load_day(engine, plan_date: str) -> pd.DataFrame:
    """Gabungan plan + actual kedua shift untuk satu tanggal (format panjang)."""
    sql = """
        SELECT i.item_key, i.customer, i.part_name, i.remarks, i.sort_order, p.shift, p.qty_plan,
               a.qty_actual, a.reason, a.note, a.input_by, a.updated_at,
               CASE WHEN pr.item_key IS NULL THEN 0 ELSE 1 END AS is_priority,
               CASE WHEN lk.item_key IS NULL THEN 0 ELSE 1 END AS is_locked
        FROM plans p
        JOIN items i ON i.item_key = p.item_key
        LEFT JOIN actuals a ON a.item_key = p.item_key AND a.plan_date = p.plan_date AND a.shift = p.shift
        LEFT JOIN priorities pr ON pr.item_key = p.item_key AND pr.plan_date = p.plan_date AND pr.shift = p.shift
        LEFT JOIN locks lk ON lk.item_key = p.item_key AND lk.plan_date = p.plan_date AND lk.shift = p.shift
        WHERE p.plan_date = :d AND (p.qty_plan > 0 OR a.qty_actual IS NOT NULL)
        ORDER BY i.sort_order, i.item_key"""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"d": plan_date})


# ------------------------------------------------------------------ simpan actual
def _audit(action, d, s, k, old, new, user):
    old, new = old or (None, None, None), new or (None, None, None)
    return {"id": uuid.uuid4().hex, "d": d, "s": int(s), "k": k, "a": action,
            "oq": old[0], "nq": new[0], "or": old[1], "nr": new[1], "on": old[2], "nn": new[2], "u": user, "t": _now()}


_AUDIT_SQL = """INSERT INTO audit (log_id, plan_date, shift, item_key, action, old_actual, new_actual,
                old_reason, new_reason, old_note, new_note, by_user, at)
                VALUES (:id, :d, :s, :k, :a, :oq, :nq, :or, :nr, :on, :nn, :u, :t)"""


def save_actuals(engine, plan_date: str, shift: int, rows: list[dict], user: str, lock: bool = False) -> dict:
    """rows: item_key, qty_actual (int|None), reason, note. Baris kosong semua = hapus actual item itu.
    lock=True: item yang punya actual ikut dikunci. Item yang SUDAH terkunci dilewati (dikembalikan di 'skipped').
    Semua perubahan tercatat di tabel audit."""
    base = {"d": plan_date, "s": int(shift)}
    saved, skipped, logs, ups, rms, lks = 0, [], [], [], [], []
    with engine.begin() as conn:
        old = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
            text("SELECT item_key, qty_actual, reason, note FROM actuals WHERE plan_date=:d AND shift=:s"), base)}
        locked = {r[0] for r in conn.execute(text("SELECT item_key FROM locks WHERE plan_date=:d AND shift=:s"), base)}
        for r in rows:
            k = r["item_key"]
            if k in locked:
                skipped.append(k)
                continue
            qa, rs, nt = r.get("qty_actual"), (r.get("reason") or None), ((r.get("note") or "").strip().upper() or None)
            qa = None if qa is None else int(qa)
            if qa is None and rs is None and nt is None:
                if k in old:
                    rms.append({"k": k, **base})
                    logs.append(_audit("HAPUS", plan_date, shift, k, old[k], None, user))
                    saved += 1
                continue
            new = (qa, rs, nt)
            ups.append({"k": k, **base, "qa": qa, "r": rs, "n": nt, "u": user, "t": _now()})
            if k in old and old[k] != new:
                logs.append(_audit("UBAH", plan_date, shift, k, old[k], new, user))
            if lock and qa is not None:
                lks.append({"k": k, **base, "u": user, "t": _now()})
                logs.append(_audit("KUNCI", plan_date, shift, k, None, new, user))
            saved += 1
        if ups:
            conn.execute(text("""
                INSERT INTO actuals (item_key, plan_date, shift, qty_actual, reason, note, input_by, updated_at)
                VALUES (:k, :d, :s, :qa, :r, :n, :u, :t)
                ON CONFLICT (item_key, plan_date, shift) DO UPDATE SET qty_actual=excluded.qty_actual,
                    reason=excluded.reason, note=excluded.note, input_by=excluded.input_by,
                    updated_at=excluded.updated_at"""), ups)
        if rms:
            conn.execute(text("DELETE FROM actuals WHERE item_key=:k AND plan_date=:d AND shift=:s"), rms)
        if lks:
            conn.execute(text("""
                INSERT INTO locks (item_key, plan_date, shift, locked_by, locked_at)
                VALUES (:k, :d, :s, :u, :t)
                ON CONFLICT (item_key, plan_date, shift) DO UPDATE SET locked_by=excluded.locked_by,
                    locked_at=excluded.locked_at"""), lks)
        if logs:
            conn.execute(text(_AUDIT_SQL), logs)
    return {"saved": saved, "skipped": skipped}


def unlock_item(engine, plan_date: str, shift: int, item_key: str, user: str) -> bool:
    """Buka kunci satu item (khusus PPIC). Tercatat di audit."""
    p = {"k": item_key, "d": plan_date, "s": int(shift)}
    with engine.begin() as conn:
        n = conn.execute(text("DELETE FROM locks WHERE item_key=:k AND plan_date=:d AND shift=:s"), p).rowcount
        if n:
            cur = conn.execute(text("SELECT qty_actual, reason, note FROM actuals WHERE item_key=:k AND plan_date=:d AND shift=:s"), p).fetchone()
            conn.execute(text(_AUDIT_SQL), _audit("BUKA KUNCI", plan_date, shift, item_key, tuple(cur) if cur else None, None, user))
    return bool(n)


def load_audit(engine, plan_date: str, limit: int = 300) -> pd.DataFrame:
    sql = """
        SELECT a.at, a.shift, i.customer, i.part_name, a.action, a.old_actual, a.new_actual,
               a.old_reason, a.new_reason, a.new_note, a.by_user
        FROM audit a LEFT JOIN items i ON i.item_key = a.item_key
        WHERE a.plan_date = :d ORDER BY a.at DESC LIMIT :n"""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"d": plan_date, "n": limit})


# ------------------------------------------------------------------ prioritas
def save_priorities(engine, plan_date: str, shifts: list[int], checked: list[str], in_view: list[str], user: str) -> int:
    """Tandai/lepas prioritas. in_view = semua item yang sedang tampil di layar PPIC (yang tidak
    dicentang di antaranya dilepas), checked = yang dicentang. shifts = shift yang terpengaruh."""
    base = [{"k": k, "d": plan_date, "s": int(s)} for s in shifts for k in in_view]
    ups = [{"k": k, "d": plan_date, "s": int(s), "u": user, "t": _now()} for s in shifts for k in checked]
    with engine.begin() as conn:
        if base:
            conn.execute(text("DELETE FROM priorities WHERE item_key=:k AND plan_date=:d AND shift=:s"), base)
        if ups:
            conn.execute(text("""
                INSERT INTO priorities (item_key, plan_date, shift, marked_by, updated_at)
                VALUES (:k, :d, :s, :u, :t)
                ON CONFLICT (item_key, plan_date, shift) DO UPDATE SET marked_by=excluded.marked_by,
                    updated_at=excluded.updated_at"""), ups)
    return len(checked)
