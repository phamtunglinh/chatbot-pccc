import streamlit as st
import google.generativeai as genai
import time
import random
from docx import Document
from pypdf import PdfReader
import io

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC", page_icon="🚒")

# --- KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys.split(",") if k.strip()]
except: st.error("Lỗi: Chưa cấu hình GEMINI_API_KEYS trong Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- HÀM TỰ ĐỘNG TÌM MODEL SỐNG (FIX LỖI 404) ---
@st.cache_resource
def get_working_model():
    # Thử kết nối để lấy danh sách model
    genai.configure(api_key=API_KEYS[0])
    try:
        models = [m.name for m in genai.list_models()]
        # Ưu tiên Flash -> Pro 1.5 -> Pro 1.0
        if 'models/gemini-1.5-flash' in models: return 'gemini-1.5-flash'
        if 'models/gemini-1.5-pro' in models: return 'gemini-1.5-pro'
        return 'gemini-pro' # Fallback cuối cùng
    except:
        return 'gemini-pro'

ACTIVE_MODEL = get_working_model()

# --- GIAO DIỆN CHAT ĐƠN GIẢN ---
st.title("🚒 Trợ lý PCCC & CNCH")
st.caption(f"Đang chạy trên model: {ACTIVE_MODEL}")

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Nhập nội dung..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Xử lý trả lời
    try:
        # Chọn key ngẫu nhiên
        genai.configure(api_key=get_random_key())
        model = genai.GenerativeModel(ACTIVE_MODEL)
        
        with st.chat_message("assistant"):
            with st.spinner("Đang trả lời..."):
                response = model.generate_content(prompt)
                st.write(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
    except Exception as e:
        err = str(e)
        if "404" in err:
            st.error("Lỗi Model: Hãy cập nhật requirements.txt thành google-generativeai>=0.7.0")
        elif "429" in err:
            st.warning("Hệ thống bận, vui lòng thử lại sau 10s.")
        else:
            st.error(f"Lỗi: {err}")
