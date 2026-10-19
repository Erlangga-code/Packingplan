"""Gaya tampilan (CSS) dan potongan HTML kecil untuk app Planning Assy Packing.

Gaya visual: papan andon pabrik (lampu hijau/kuning/merah) + pita hazard kuning-hitam.
Semua warna status dipakai konsisten: hijau = sesuai, kuning = belum diisi, merah = kurang.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Semi+Condensed:wght@500;600;700&display=swap');
:root{--ink:#1C2B39;--line:#D5DBE3;--mute:#5F6F7F;--ok:#1E9E6A;--ok-bg:#E3F5EC;--wait:#C98200;--wait-bg:#FFF1CC;--bad:#D64040;--bad-bg:#FDE7E7;--steel:#2B5C9E}
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button{font-family:'Barlow',system-ui,sans-serif !important}
.block-container{padding-top:4.4rem !important;max-width:1080px !important;margin:0 auto}
@media (max-width:640px){.block-container{padding:4rem .6rem 3rem !important}}
.hdr{background:var(--ink);color:#fff;padding:14px 18px 12px;border-radius:10px 10px 0 0;display:flex;justify-content:space-between;align-items:flex-end;gap:6px 16px;flex-wrap:wrap}
.hdr-t{font:700 28px/1.05 'Barlow Semi Condensed',sans-serif}
.hdr-s{font:500 15px 'Barlow',sans-serif;color:#B9C6D3}
.hazard{height:9px;border-radius:0 0 10px 10px;background:repeating-linear-gradient(-45deg,#FFC400 0 10px,#1C2B39 10px 20px);margin-bottom:14px}
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:2px 0 8px}
.lamp{background:#fff;border:1px solid var(--line);border-radius:10px;padding:9px 12px;display:flex;align-items:center;gap:10px}
.dot{display:inline-block;width:13px;height:13px;border-radius:50%;flex:none}
.dot.ok{background:var(--ok);box-shadow:0 0 0 4px var(--ok-bg)}
.dot.wait{background:#F0A800;box-shadow:0 0 0 4px var(--wait-bg)}
.dot.bad{background:var(--bad);box-shadow:0 0 0 4px var(--bad-bg)}
.lamp-n{font:700 30px/1 'Barlow Semi Condensed',sans-serif;color:var(--ink)}
.lamp-l{font:500 13px 'Barlow',sans-serif;color:var(--mute)}
.prog{display:flex;height:10px;border-radius:6px;overflow:hidden;background:#DCE2E9;margin:0 0 12px}
.prog span{display:block;height:100%}
.prog .ok{background:var(--ok)}.prog .bad{background:var(--bad)}
.it{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.it-part{font:600 17px/1.2 'Barlow',sans-serif;color:var(--ink);word-break:break-word}
.it-meta{margin-top:5px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.chip{font:500 12px 'Barlow',sans-serif;padding:2px 9px;border-radius:999px;background:#E8EDF3;color:#3C4B5A}
.chip.warn{background:var(--wait-bg);color:#6E4A00}
.st{font:600 13px 'Barlow',sans-serif;display:inline-flex;align-items:center;gap:7px;color:var(--ink)}
.plan{text-align:right;flex:none}
.plan-n{font:700 32px/1 'Barlow Semi Condensed',sans-serif;color:var(--ink)}
.plan-u{display:block;font:500 12px 'Barlow',sans-serif;color:var(--mute)}
.strip{display:grid;grid-template-columns:1fr 1fr 1fr 1.25fr;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:4px 0 14px}
@media (max-width:760px){.strip{grid-template-columns:1fr 1fr}}
.cell{padding:14px 16px;border-right:1px solid var(--line)}
.cell:last-child{border-right:0}
.cell-l{font:500 13px 'Barlow',sans-serif;color:var(--mute)}
.cell-n{font:700 38px/1.05 'Barlow Semi Condensed',sans-serif;color:var(--ink);margin-top:2px}
.cell-s{font:500 13px 'Barlow',sans-serif;color:var(--mute);margin-top:2px}
.cell.hero{background:var(--ink);border-right:0}
.cell.hero .cell-l,.cell.hero .cell-s{color:#B9C6D3}
.cell.hero .cell-n{color:#FFC400;font-size:44px}
.mini{height:6px;border-radius:4px;background:#DCE2E9;margin-top:8px;overflow:hidden}
.mini span{display:block;height:100%;background:var(--ok)}
.sec{font:700 20px 'Barlow Semi Condensed',sans-serif;color:var(--ink);margin:16px 0 6px}
.row{display:flex;gap:14px;justify-content:space-between;align-items:center;background:#fff;border:1px solid var(--line);border-left:6px solid var(--bad);border-radius:8px;padding:10px 14px;margin-bottom:8px}
.row.add{border-left-color:#8A1F1F}
.row-l{min-width:0}
.row-p{font:600 16px/1.2 'Barlow',sans-serif;color:var(--ink);word-break:break-word}
.row-c{font:500 13px 'Barlow',sans-serif;color:var(--mute);margin-top:2px}
.row-n{font:500 13px 'Barlow',sans-serif;color:#3C4B5A;margin-top:5px}
.row-r{text-align:right;flex:none}
.row-big{font:700 28px/1 'Barlow Semi Condensed',sans-serif;color:var(--bad)}
.row-s2{font:500 13px 'Barlow',sans-serif;color:var(--mute);margin-top:4px}
.m4{display:grid;grid-template-columns:96px 1fr 120px;gap:10px;align-items:center;margin:6px 0;font:500 14px 'Barlow',sans-serif;color:var(--ink)}
.m4 .track{height:14px;background:#DCE2E9;border-radius:7px;overflow:hidden}
.m4 .track span{display:block;height:100%;background:var(--bad)}
.m4 .v{text-align:right;color:var(--mute)}
.pbadge{font:700 12px 'Barlow',sans-serif;padding:2px 10px;border-radius:999px;background:#6A2FB5;color:#fff}
.pcall{background:#6A2FB5;color:#fff;border-radius:10px;padding:11px 16px;margin:6px 0 10px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.pcall-t{font:700 18px/1.15 'Barlow Semi Condensed',sans-serif}
.pcall-s{font:500 14px 'Barlow',sans-serif;color:#E6D9F8;margin-top:2px}
.pcall-n{font:700 30px/1 'Barlow Semi Condensed',sans-serif;color:#FFD84D;text-align:right}
.pcall-n small{display:block;font:500 12px 'Barlow',sans-serif;color:#E6D9F8}
[class*="st-key-prio_"]{border-left:8px solid #6A2FB5 !important;border-color:#CDB6EE #CDB6EE #CDB6EE #6A2FB5 !important;background:#F5EFFD !important}
.row.prio{border-left-color:#6A2FB5;background:#F5EFFD}
.row.ok{border-left-color:var(--ok)}
.okl{font:500 14px 'Barlow',sans-serif;padding:4px 0;color:#3C4B5A;border-bottom:1px solid #EEF1F5;display:flex;justify-content:space-between;gap:10px}
.okl b{font-weight:600;color:var(--ink)}
.sum{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 10px}
.sum span{font:600 14px 'Barlow',sans-serif;padding:4px 12px;border-radius:999px;background:#E8EDF3;color:var(--ink)}
.sum .g{background:var(--ok-bg);color:#0F6B47}.sum .r{background:var(--bad-bg);color:#9A2323}.sum .y{background:var(--wait-bg);color:#6E4A00}
.lk{margin-top:8px;font:500 14px 'Barlow',sans-serif;color:#3C4B5A;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.lkb{font:600 12px 'Barlow',sans-serif;padding:2px 9px;border-radius:999px;background:#DDE3EA;color:#3C4B5A}
.empty{background:#fff;border:1px dashed var(--line);border-radius:10px;padding:16px;color:var(--mute);font:500 15px 'Barlow',sans-serif}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return html.escape(str(x))


def idn(n) -> str:
    """Angka format Indonesia: 12500 -> 12.500"""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "-"
    return f"{int(round(n)):,}".replace(",", ".")


def header(title: str, sub: str = ""):
    st.markdown(f'<div class="hdr"><div class="hdr-t">{esc(title)}</div><div class="hdr-s">{esc(sub)}</div></div>'
                '<div class="hazard"></div>', unsafe_allow_html=True)


def board(ok: int, bad: int, wait: int):
    total = max(ok + bad + wait, 1)
    st.markdown(
        '<div class="board">'
        f'<div class="lamp"><i class="dot ok"></i><div><div class="lamp-n">{ok}</div><div class="lamp-l">Sesuai plan</div></div></div>'
        f'<div class="lamp"><i class="dot bad"></i><div><div class="lamp-n">{bad}</div><div class="lamp-l">Kurang</div></div></div>'
        f'<div class="lamp"><i class="dot wait"></i><div><div class="lamp-n">{wait}</div><div class="lamp-l">Belum diisi</div></div></div>'
        '</div>'
        f'<div class="prog"><span class="ok" style="width:{ok / total * 100:.1f}%"></span>'
        f'<span class="bad" style="width:{bad / total * 100:.1f}%"></span></div>', unsafe_allow_html=True)


def item_head(part, remarks, plan, status_html, prio=False):
    chips = ('<span class="pbadge">PRIORITAS</span>' if prio else "") + \
            (f'<span class="chip warn">{esc(remarks)}</span>' if remarks else "")
    return ('<div class="it"><div>'
            f'<div class="it-part">{esc(part)}</div>'
            f'<div class="it-meta">{status_html}{chips}</div></div>'
            f'<div class="plan"><span class="plan-n">{idn(plan)}</span><span class="plan-u">plan</span></div></div>')


def status_html(plan, actual) -> str:
    if actual is None or pd.isna(actual):
        return '<span class="st"><i class="dot wait"></i>Belum diisi</span>'
    if actual < plan:
        return f'<span class="st"><i class="dot bad"></i>Kurang {idn(plan - actual)}</span>'
    if actual > plan:
        return f'<span class="st"><i class="dot ok"></i>Lebih {idn(actual - plan)}</span>'
    return '<span class="st"><i class="dot ok"></i>Sesuai</span>'


def strip(plan1, act1, belum, n_s1, kurang, dikejar, plan2, target2):
    pct = 0 if plan1 == 0 else min(100, act1 / plan1 * 100)
    st.markdown(
        '<div class="strip">'
        f'<div class="cell"><div class="cell-l">Actual shift 1</div><div class="cell-n">{idn(act1)}</div>'
        f'<div class="cell-s">dari plan {idn(plan1)}</div><div class="mini"><span style="width:{pct:.1f}%"></span></div></div>'
        f'<div class="cell"><div class="cell-l">Belum diisi leader</div><div class="cell-n">{belum}</div>'
        f'<div class="cell-s">dari {n_s1} item shift 1</div></div>'
        f'<div class="cell"><div class="cell-l">Item kurang</div><div class="cell-n">{kurang}</div>'
        f'<div class="cell-s">{idn(dikejar)} pcs harus dikejar</div></div>'
        f'<div class="cell hero"><div class="cell-l">Target shift 2</div><div class="cell-n">{idn(target2)}</div>'
        f'<div class="cell-s">plan {idn(plan2)} + sisa {idn(dikejar)}</div></div>'
        '</div>', unsafe_allow_html=True)


def shortfall_row(r) -> str:
    chip = f'<span class="chip">{esc(r["alasan_s1"])}</span>' if r["alasan_s1"] else ""
    note = f'<div class="row-n">{esc(r["ket_s1"])}</div>' if r["ket_s1"] else ""
    new = '<span class="chip warn">belum ada plan S2</span>' if r["plan_s2"] == 0 else ""
    pb = '<span class="pbadge">PRIORITAS</span>' if r.get("prioritas") else ""
    return (f'<div class="row{" add" if r["plan_s2"] == 0 else ""}{" prio" if r.get("prioritas") else ""}"><div class="row-l">'
            f'<div class="row-p">{esc(r["part_name"])}</div>'
            f'<div class="row-c">{esc(r["customer"]) or "(tanpa customer)"}</div>'
            f'<div class="it-meta" style="margin-top:6px">{pb}{chip}{new}</div>{note}</div>'
            f'<div class="row-r"><div class="row-big">-{idn(r["dikejar_s2"])}</div>'
            f'<div class="row-s2">S2: {idn(r["plan_s2"])} &rarr; {idn(r["target_s2"])}</div></div></div>')


def m4_bars(df: pd.DataFrame, order: list[str]) -> str:
    """df: baris item kurang. Batang per penyebab (4M), panjang = pcs kurang."""
    g = df.groupby(df["alasan_s1"].fillna("Tanpa alasan")).agg(pcs=("dikejar_s2", "sum"), n=("part_name", "count"))
    keys = [k for k in order if k in g.index] + [k for k in g.index if k not in order]
    mx = max(g["pcs"].max(), 1) if len(g) else 1
    rows = "".join(f'<div class="m4"><div>{esc(k)}</div><div class="track"><span style="width:{g.loc[k, "pcs"] / mx * 100:.1f}%"></span></div>'
                   f'<div class="v">{idn(g.loc[k, "pcs"])} pcs ({g.loc[k, "n"]} item)</div></div>' for k in keys)
    return rows


def prio_callout(total: int, done: int, title: str = "Item PRIORITAS: tidak boleh di-skip", sub: str = ""):
    sub_html = f'<div class="pcall-s">{esc(sub)}</div>' if sub else ""
    st.markdown(f'<div class="pcall"><div><div class="pcall-t">{esc(title)}</div>{sub_html}</div>'
                f'<div class="pcall-n">{done}/{total}<small>sudah diisi</small></div></div>', unsafe_allow_html=True)


def preview_summary(n_ok: int, n_kurang: int, n_lebih: int) -> str:
    parts = [f'<span>{n_ok + n_kurang + n_lebih} item akan dikunci</span>', f'<span class="g">{n_ok} sesuai</span>']
    if n_kurang:
        parts.append(f'<span class="r">{n_kurang} kurang</span>')
    if n_lebih:
        parts.append(f'<span class="y">{n_lebih} lebih</span>')
    return '<div class="sum">' + "".join(parts) + '</div>'


def preview_detail(it: dict) -> str:
    """Baris detail untuk item yang kurang / lebih dari plan."""
    diff = it["qa"] - it["plan"]
    cls = "" if diff < 0 else " ok"
    chip = f'<span class="chip">{esc(it["reason"])}</span>' if it.get("reason") else ""
    note = f'<div class="row-n">{esc(it["note"])}</div>' if it.get("note") else ""
    prio = '<span class="pbadge">PRIORITAS</span>' if it.get("prio") else ""
    big = f'-{idn(-diff)}' if diff < 0 else f'+{idn(diff)}'
    color = "var(--bad)" if diff < 0 else "#B07A00"
    return (f'<div class="row{cls}"><div class="row-l"><div class="row-p">{esc(it["part"])}</div>'
            f'<div class="it-meta" style="margin-top:6px">{prio}{chip}</div>{note}</div>'
            f'<div class="row-r"><div class="row-big" style="color:{color}">{big}</div>'
            f'<div class="row-s2">Actual {idn(it["qa"])} dari plan {idn(it["plan"])}</div></div></div>')


def preview_ok_line(it: dict) -> str:
    return f'<div class="okl"><span>{esc(it["part"])}</span><b>{idn(it["qa"])}</b></div>'


def locked_info(actual, reason, note) -> str:
    chips = "".join([f'<span class="lkb">{esc(reason)}</span>' if reason else "",
                     f'<span>{esc(note)}</span>' if note else ""])
    return f'<div class="lk"><span class="lkb">🔒 Terkunci</span><span>Actual <b>{idn(actual)}</b></span>{chips}</div>'
