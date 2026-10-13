"""Pengaturan umum app Planning Assy Packing."""

# Zona waktu untuk menentukan "hari ini" (Streamlit Cloud berjalan di UTC)
TZ_NAME = "Asia/Jakarta"

# Sheet yang dibaca dari Excel planning
DEFAULT_SHEET = "ASSY"

# Baris yang nama part-nya mengandung frasa ini TIDAK ikut (itu planning assy stay)
DEFAULT_EXCLUDE = ["sub assy stay", "stay mirror"]

# Pilihan alasan (dropdown). Bebas diubah/ditambah.
REASONS = [
    "Material / part kurang",
    "WIP belum ada (proses sebelumnya)",
    "Mesin / jig bermasalah",
    "Manpower kurang",
    "Prioritas diganti (item lain didahulukan)",
    "Part tidak terpakai / di-drop",
    "Lainnya (isi keterangan)",
]

# Alasan yang berarti sisa shift 1 TIDAK perlu dikejar di shift 2
DROP_REASONS = {"Part tidak terpakai / di-drop"}
