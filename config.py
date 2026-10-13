"""Pengaturan umum app Planning Assy Packing."""

# Zona waktu untuk menentukan "hari ini" (Streamlit Cloud berjalan di UTC)
TZ_NAME = "Asia/Jakarta"

# Sheet yang dibaca dari Excel planning
DEFAULT_SHEET = "ASSY"

# Baris yang nama part-nya mengandung frasa ini TIDAK ikut (itu planning assy stay)
DEFAULT_EXCLUDE = ["sub assy stay", "stay mirror"]

# Pilihan alasan (dropdown): 4M
REASONS = ["MAN", "METHODE", "MACHINE", "MATERIAL"]

# Alasan yang berarti sisa shift 1 TIDAK perlu dikejar di shift 2 (kosong = semua kekurangan dikejar)
DROP_REASONS = set()
