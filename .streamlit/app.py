import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io
import json

# --- CẤU HÌNH ---
st.set_page_config(page_title="PCCC Debug", page_icon="🛠️", layout="wide")

# --- LẤY SECRETS ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi Secrets: {e}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- GIAO DIỆN BẮT BỆNH ---
st.title("🛠️ CÔNG CỤ CHẨN ĐOÁN LỖI PCCC")

# 1. KIỂM TRA PHIÊN BẢN THƯ VIỆN
st.subheader("1. Kiểm tra phiên bản thư viện")
st.code(f"Phiên bản google-generativeai đang chạy: {genai.__version__}")
# Nếu phiên bản nhỏ hơn 0.7.0 thì chắc chắn lỗi do đây -> Cần ép cập nhật

# 2. KIỂM TRA DANH SÁCH MODEL (QUAN TRỌNG NHẤT)
st.subheader("2. Danh sách Model mà Key của anh nhìn thấy")
try:
    models = list(genai.list_models())
    found_flash = False
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("📋 **Danh sách trả về từ Google:**")
        for m in models:
            st.write(f"- `{m.name}`")
            if "flash" in m.name:
                found_flash = True
    
    with col2:
        st.info("💡 **Kết luận:**")
        if found_flash:
            st.success("✅ Có thấy Flash! Hãy copy chính xác cái tên bên trái vào code.")
        else:
            st.error("❌ Không thấy Flash đâu cả! Có thể do thư viện cũ hoặc Key chưa kích hoạt Generative Language API.")

except Exception as e:
    st.error(f"Không thể lấy danh sách Model. Lỗi: {e}")

# 3. THỬ NGHIỆM TẢI DRIVE
st.subheader("3. Kiểm tra kết nối Drive")
try:
    creds = service_account.Credentials.from_service_account_info(GCP_JSON)
    service = build('drive', 'v3', credentials=creds)
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)").execute()
    files = results.get('files', [])
    st.success(f"✅ Kết nối Drive tốt! Đã thấy {len(files)} file.")
except Exception as e:
    st.error(f"❌ Lỗi kết nối Drive: {e}")
