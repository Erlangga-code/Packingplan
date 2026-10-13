# Planning Assy Packing

PPIC upload Excel planning (sheet ASSY) -> leader isi actual per shift dari HP -> PPIC lihat rekap
"sisa shift 1 -> target shift 2".

## File
| File | Fungsi |
|---|---|
| `app.py` | Tampilan Streamlit (Input Actual, Rekap Shift, Upload Plan) |
| `assy_parser.py` | Baca sheet ASSY jadi tabel rapi + validasi total |
| `db.py` | Database (SQLite lokal / PostgreSQL online) |
| `recap.py` | Logika rekap & export Excel |
| `config.py` | Daftar alasan (dropdown), frasa baris yang dilewati (stay), zona waktu |

## Jalan lokal
```
pip install -r requirements.txt
streamlit run app.py
```
Tanpa Secrets, app jalan tanpa login dan memakai SQLite (`planning.db`).

## Deploy (Streamlit Community Cloud)
1. Push folder ini ke GitHub (**repo private** karena isinya data produksi). `secrets.toml` dan `*.db` sudah di `.gitignore`.
2. Buat database PostgreSQL gratis (mis. Supabase), salin connection string-nya.
3. Di Streamlit Cloud: New app -> pilih repo -> `app.py`. Lalu **Settings -> Secrets**, isi seperti `.streamlit/secrets.toml.example`:
   `PPIC_PASSWORD`, `LEADER_PIN`, `DATABASE_URL`.
4. Bagikan link app + PIN leader ke leader.

SQLite di Streamlit Cloud bersifat sementara (hilang saat restart), jadi `DATABASE_URL` wajib diisi di produksi.

## Cara pakai
- **PPIC -> Upload Plan**: pilih file, cek tabel validasi (harus OK), klik Simpan. Upload ulang untuk revisi: plan diperbarui, actual leader tidak hilang.
- **Leader -> Input Actual**: pilih tanggal & shift, centang "sesuai plan" untuk yang aman, isi Actual + Alasan untuk yang kurang, Simpan.
- **PPIC -> Rekap Shift**: Target S2 = Plan S2 + sisa S1 yang masih harus dikejar.

## Aturan baca Excel
- Baris dengan nama part berisi frasa di `config.DEFAULT_EXCLUDE` ("sub assy stay", "stay mirror") dilewati. Bisa diubah di halaman Upload.
- Tanggal diambil dari angka tanggal di header + urutan kolom (bukan dari kode lot, karena kode lot ada yang salah ketik).
- Part dengan customer dan nama sama dibedakan lewat urutan baris; kolom Remarks ditampilkan di samping.
- Default hanya kolom yang tidak di-hide yang dibaca.
