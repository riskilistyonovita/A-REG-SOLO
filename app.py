import streamlit as st
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import traceback
import io
import logging
from datetime import date
from html import escape

# ===============================
# KONFIGURASI GOOGLE API
# ===============================
SPREADSHEET_ID = "1Fj2gNDdA65hcfHVj55DKZiLl-BcBKdG_QMWSLA3y9dQ"
SHEET_KATEGORI = "kategori"
SHEET_METADATA = "metadata"
ROOT_FOLDER_ID = "1bB3P_f_ZtdO5BA_u9yLfA-Zy2c0kte1c"  # Shared Drive root

ADMIN_PASSWORD = "sekretaris"
USER_PASSWORD = "regulasirshsl"

# Setup logging
logging.basicConfig(
    filename="app_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

@st.cache_resource
def get_services():
    """Inisialisasi Google Sheets dan Drive API"""
    try:
        creds = service_account.Credentials.from_service_account_file(
            "credentials.json",
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets",
            ],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws_kategori = sh.worksheet(SHEET_KATEGORI)
        ws_metadata = sh.worksheet(SHEET_METADATA)

        drive_service = build("drive", "v3", credentials=creds)

        return {
            "gc": gc,
            "sh": sh,
            "ws_kategori": ws_kategori,
            "ws_metadata": ws_metadata,
            "drive": drive_service,
        }
    except Exception:
        tb = traceback.format_exc()
        st.error("Gagal inisialisasi service:\n{}".format(tb))
        return None


# ===============================
# HELPERS
# ===============================
def get_or_create_folder(drive, parent_id, folder_name):
    """Cari folder, kalau tidak ada buat baru"""
    if not folder_name:
        return parent_id
    try:
        query = "name='{}' and '{}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false".format(
            folder_name, parent_id
        )
        results = drive.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        items = results.get("files", [])
        if items:
            return items[0]["id"]
        # buat folder baru
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = drive.files().create(
            body=file_metadata,
            fields="id",
            supportsAllDrives=True
        ).execute()
        folder_id = folder.get("id")
        logging.info("Buat folder baru: {} (ID: {})".format(folder_name, folder_id))
        return folder_id
    except Exception:
        tb = traceback.format_exc()
        st.error("Gagal membuat/mencari folder:\n{}".format(tb))
        return None


def upload_file_to_drive(drive, file, parent_id):
    """Upload file PDF ke folder"""
    try:
        file_metadata = {"name": file.name, "parents": [parent_id]}
        media = MediaIoBaseUpload(file, mimetype="application/pdf")
        uploaded = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()
        file_id = uploaded.get("id")
        logging.info("Upload file: {} (ID: {})".format(file.name, file_id))
        return file_id
    except Exception:
        tb = traceback.format_exc()
        st.error("Gagal upload file:\n{}".format(tb))
        return None


# ===============================
# LOGIN (Modern UI)
# ===============================
def login():
    st.markdown(
        """
        <style>
        .login-box {
            max-width: 400px;
            margin: 50px auto;
            padding: 2rem;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
        }
        .login-title {
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: .5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown("<div class='login-title'>🔐 Masuk ke Sistem</div>", unsafe_allow_html=True)

    role = st.radio("Pilih Akses:", ["Pengunjung", "Admin"], horizontal=True)
    password = st.text_input("Password:", type="password")

    if st.button("🚀 Login"):
        if role == "Admin" and password == ADMIN_PASSWORD:
            st.session_state["role"] = "admin"
            st.rerun()
        elif role == "Pengunjung" and password == USER_PASSWORD:
            st.session_state["role"] = "user"
            st.rerun()
        else:
            st.error("Password salah!")

    st.markdown("</div>", unsafe_allow_html=True)


# ===============================
# PAGE: Daftar Regulasi (tabel rapi)
# ===============================
def page_daftar(services):
    st.header("📑 Tabel Regulasi")

    try:
        ws_metadata = services["ws_metadata"]
        rows = ws_metadata.get_all_values()
        if not rows or len(rows) <= 1:
            st.info("Belum ada regulasi yang diunggah.")
            return

        header, data = rows[0], rows[1:]

        # Normalisasi baris ke 8 kolom
        normalized = []
        for r in data:
            r = (r + [""] * 8)[:8]
            nama, kategori, bidang, unit, sub, file_id, t_terbit, t_kadaluarsa = r
            normalized.append({
                "Nama Regulasi": nama or "",
                "Kategori": kategori or "",
                "Tanggal Terbit": t_terbit or "",
                "Tanggal Kadaluarsa": t_kadaluarsa or "",
                "file_id": file_id or "",
            })

        # Pencarian
        q = st.text_input("🔍 Cari regulasi", "")
        if q:
            ql = q.lower()
            normalized = [row for row in normalized if ql in row["Nama Regulasi"].lower()]

        # Pengurutan
        c1, c2 = st.columns([3, 1])
        with c1:
            sort_col = st.selectbox(
                "Urutkan berdasarkan",
                ["Nama Regulasi", "Kategori", "Tanggal Terbit", "Tanggal Kadaluarsa"],
                index=0
            )
        with c2:
            sort_dir = st.radio("Arah", ["Naik", "Turun"], index=0, horizontal=True)
        reverse = (sort_dir == "Turun")
        normalized.sort(key=lambda x: (x.get(sort_col) or "").lower(), reverse=reverse)

        # CSS custom
        st.markdown(
            """
            <style>
            table.reg-table {
                table-layout: fixed;
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #eee;
                background: #fff;
                border-radius: 10px;
                overflow: hidden;
            }
            .reg-table th, .reg-table td {
                padding: 10px 12px;
                text-align: left;
                vertical-align: middle;
                word-wrap: break-word;
                border-bottom: 1px solid #f0f0f0;
            }
            .reg-table thead th {
                background: #f9fafb;
                font-weight: 700;
            }
            .reg-table tr:hover td { background: #fafcff; }
            .reg-table th:nth-child(1), .reg-table td:nth-child(1) { width: 40%; }
            .reg-table th:nth-child(2), .reg-table td:nth-child(2) { width: 15%; }
            .reg-table th:nth-child(3), .reg-table td:nth-child(3) { width: 15%; }
            .reg-table th:nth-child(4), .reg-table td:nth-child(4) { width: 15%; }
            .reg-table th:nth-child(5), .reg-table td:nth-child(5) { width: 15%; text-align: center; }
            .doc-link { text-decoration: none; font-size: 20px; }
            </style>
            """,
            unsafe_allow_html=True
        )

        # HTML tabel
        html = [
            '<table class="reg-table">',
            "<thead><tr>",
            "<th>Nama Regulasi</th>",
            "<th>Kategori</th>",
            "<th>Tanggal Terbit</th>",
            "<th>Tanggal Kadaluarsa</th>",
            "<th>Dokumen</th>",
            "</tr></thead><tbody>"
        ]

        for row in normalized:
            doc = (
                f'<a class="doc-link" href="https://drive.google.com/file/d/{row["file_id"]}/preview" '
                f'target="_blank" title="Buka dokumen">📄</a>'
            ) if row["file_id"] else ""
            html.append(
                "<tr>"
                f"<td>{escape(row['Nama Regulasi'])}</td>"
                f"<td>{escape(row['Kategori'])}</td>"
                f"<td>{escape(row['Tanggal Terbit'])}</td>"
                f"<td>{escape(row['Tanggal Kadaluarsa'])}</td>"
                f"<td style='text-align:center'>{doc}</td>"
                "</tr>"
            )

        html.append("</tbody></table>")
        st.markdown("\n".join(html), unsafe_allow_html=True)
        st.caption("Klik ikon 📄 untuk membuka dokumen di tab baru.")

    except Exception:
        st.error("Gagal memuat daftar regulasi. Detail error ditulis ke log.")
        st.write(traceback.format_exc())


# ===============================
# PAGE: Unggah Regulasi
# ===============================
def page_upload(services):
    st.header("📤 Unggah Regulasi")
    ws_kategori = services["ws_kategori"]
    ws_metadata = services["ws_metadata"]
    drive = services["drive"]

    kategori_rows = ws_kategori.get_all_values()[1:]

    kategori_options = sorted(set(row[0] for row in kategori_rows))
    kategori = st.selectbox("Kategori", [""] + kategori_options)

    bidang_options = sorted(set(row[1] for row in kategori_rows if row[0] == kategori and row[1]))
    bidang = st.selectbox("Bidang Pelayanan (opsional)", [""] + bidang_options)

    unit_options = sorted(set(row[2] for row in kategori_rows if row[0] == kategori and row[1] == bidang and row[2]))
    unit = st.selectbox("Unit Pelayanan (opsional)", [""] + unit_options)

    sub_options = sorted(set(row[3] for row in kategori_rows if row[0] == kategori and row[1] == bidang and row[2] == unit and row[3]))
    subkategori = st.selectbox("Subkategori (opsional)", [""] + sub_options)

    nama = st.text_input("Nama Regulasi")
    file = st.file_uploader("Upload file PDF", type=["pdf"])

    tanggal_terbit = st.date_input("Tanggal Terbit", value=date.today())
    tanggal_kadaluarsa = st.date_input("Tanggal Kadaluarsa", value=date.today())

    if st.button("Simpan Regulasi"):
        if not nama or not kategori or not file:
            st.error("Nama, Kategori, dan File wajib diisi")
            return

        kategori_folder = get_or_create_folder(drive, ROOT_FOLDER_ID, kategori)
        bidang_folder = get_or_create_folder(drive, kategori_folder, bidang) if bidang else kategori_folder
        unit_folder = get_or_create_folder(drive, bidang_folder, unit) if unit else bidang_folder
        sub_folder = get_or_create_folder(drive, unit_folder, subkategori) if subkategori else unit_folder

        file_id = upload_file_to_drive(drive, file, sub_folder)
        ws_metadata.append_row([
            nama, kategori, bidang, unit, subkategori, file_id,
            tanggal_terbit.strftime("%Y-%m-%d"),
            tanggal_kadaluarsa.strftime("%Y-%m-%d")
        ])
        st.success("Regulasi berhasil diunggah!")


# ===============================
# PAGE: Tambah Kategori
# ===============================
def page_kategori(services):
    st.header("📂 Tambah/Mengelola Kategori Regulasi")
    ws_kategori = services["ws_kategori"]
    drive = services["drive"]

    kategori_rows = ws_kategori.get_all_values()[1:]

    existing_kategori = sorted(set(row[0] for row in kategori_rows))
    kategori = st.selectbox(
        "Pilih Kategori atau Tambah Baru",
        ["+ Tambah Baru"] + existing_kategori
    )
    if kategori == "+ Tambah Baru":
        nama_baru = st.text_input("Nama kategori baru")
    else:
        nama_baru = kategori

    bidang_options = sorted(set(row[1] for row in kategori_rows if row[0] == nama_baru and row[1]))
    bidang = st.selectbox("Bidang Pelayanan (opsional)", [""] + bidang_options)

    unit_options = sorted(set(row[2] for row in kategori_rows if row[0] == nama_baru and row[1] == bidang and row[2]))
    unit = st.selectbox("Unit Pelayanan (opsional)", [""] + unit_options)

    sub_options = sorted(set(row[3] for row in kategori_rows if row[0] == nama_baru and row[1] == bidang and row[2] == unit and row[3]))
    subkategori = st.selectbox("Subkategori (opsional)", [""] + sub_options)

    if st.button("Simpan Kategori"):
        if not nama_baru:
            st.error("Nama kategori wajib diisi.")
            return

        duplicate = any(
            row[0] == nama_baru and row[1] == bidang and row[2] == unit and row[3] == subkategori
            for row in kategori_rows
        )
        if duplicate:
            st.warning("Kategori/Bidang/Unit/Subkategori ini sudah ada, tidak ditambahkan.")
            return

        kategori_folder = get_or_create_folder(drive, ROOT_FOLDER_ID, nama_baru)
        bidang_folder = get_or_create_folder(drive, kategori_folder, bidang) if bidang else kategori_folder
        unit_folder = get_or_create_folder(drive, bidang_folder, unit) if unit else bidang_folder
        sub_folder = get_or_create_folder(drive, unit_folder, subkategori) if subkategori else unit_folder

        ws_kategori.append_row([nama_baru, bidang, unit, subkategori, kategori_folder])
        st.success(f"Kategori '{nama_baru}' berhasil dibuat atau dipilih!")


# ===============================
# MAIN
# ===============================
def main():
    if "role" not in st.session_state:
        login()
        return

    services = get_services()
    if not services:
        return

    st.sidebar.title("Navigasi")
    menu = st.sidebar.radio(
        "Menu",
        ["Daftar Regulasi", "Unggah Regulasi", "Kategori Regulasi", "Keluar"],
    )

    if menu == "Daftar Regulasi":
        page_daftar(services)
    elif menu == "Unggah Regulasi":
        if st.session_state["role"] == "admin":
            page_upload(services)
        else:
            st.warning("Hanya admin yang dapat mengunggah regulasi.")
    elif menu == "Kategori Regulasi":
        if st.session_state["role"] == "admin":
            page_kategori(services)
        else:
            st.warning("Hanya admin yang dapat membuat kategori.")
    elif menu == "Keluar":
        st.session_state.clear()
        st.rerun()


if __name__ == "__main__":
    main()
