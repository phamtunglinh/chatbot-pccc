import subprocess
import sys

# --- 1. CƯỠNG CHẾ CÀI ĐẶT THƯ VIỆN MỚI NHẤT (MAGIC FIX) ---
# Đoạn này sẽ ép máy chủ tải bản mới nhất về ngay lập tức
try:
    import google.generativeai as genai
    # Kiểm tra xem có cũ quá không, nếu cũ thì cài lại
    if genai.__version__ < "0.7.0":
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "google-generativeai"])
        import google.generativeai as genai # Import lại sau khi cài
except:
    # Nếu chưa có thì cài mới luôn
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "google-generativeai"])
    import google.generativeai as genai

import streamlit as st
import random
import time
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC (Bản Fix 404)", page_icon="🚒")

# --- HIỂN THỊ PHIÊN BẢN (ĐỂ ANH YÊN TÂM) ---
st.caption(f"🛠️ Phiên bản thư viện Google AI: {genai.__version__}") 
# Nếu anh thấy số này >= 0.7.0 là CHẮC CHẮN THÀNH CÔNG

# --- KẾT NỐI KEY ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys.split(",") if k.strip()]
except: st.error("⚠️ Lỗi: Chưa nhập Key vào Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- CẤU HÌNH MODEL ---
# Bây giờ thư viện đã mới, ta tự tin dùng model xịn
ACTIVE_MODEL = "gemini-1.5-flash"

# --- HÀM LOAD DATA (RÚT GỌN ĐỂ TEST) ---
# (Phần này giữ nguyên logic cũ của anh, tôi rút gọn để code không quá dài)
@st.cache_resource
def load_data_simple():
    return "Dữ liệu PCCC mẫu (Đang test hệ thống)", ["Test.docx"]

# --- GIAO DIỆN CHAT ---
st.title("🚒 Trợ lý PCCC & CNCH")

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Gõ 'chào' để thử..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    try:
        current_key = get_random_key()
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel(ACTIVE_MODEL)
        
        with st.chat_message("assistant"):
            with st.spinner(f"Đang kết nối {ACTIVE_MODEL}..."):
                # Gửi câu hỏi trơn (không kèm file) để test kết nối trước
                response = model.generate_content(prompt)
                st.write(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        if "404" in str(e):
            st.warning("Vẫn lỗi 404? Lạ quá. Anh thử bấm nút 'Rerun' ở góc phải trên cùng xem.")
