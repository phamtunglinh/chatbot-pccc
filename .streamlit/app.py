import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io
import json
import time

# --- CẤU HÌNH TRANG (Tab trình duyệt) ---
st.set_page_config(
    page_title="PCCC & CNCH Phú Thọ",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed" # Ẩn thanh bên cho rộng
)

# --- CSS TÙY CHỈNH (LÀM ĐẸP GIAO DIỆN) ---
st.markdown("""
<style>
    /* Ẩn menu mặc định của Streamlit cho giống App thật */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Tùy chỉnh thanh cuộn */
    ::-webkit-scrollbar {width: 8px;}
    ::-webkit-scrollbar-thumb {background: #ccc; border-radius: 4px;}
    
    /* Style cho khung chat */
    .stChatInput {border-radius: 20px;}
    
    /* Header Banner chuyên nghiệp */
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem;
        border-radius: 0 0 15px 15px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-top: -60px; /* Kéo lên che header cũ */
        margin-bottom: 20px;
    }
    .header-title {
        font-size: 24px;
        font-weight: bold;
        text-transform: uppercase;
        margin: 0;
        letter-spacing: 1px;
    }
    .header-subtitle {
        font-size: 14px;
        opacity: 0.9;
        margin-top: 5px;
        font-weight: 300;
    }
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI BẢO MẬT ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình hệ thống: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DANH SÁCH MODEL ---
MODEL_LIST = [
    "gemini-flash-latest",      
    "gemini-2.0-flash-lite-preview-09-2025", 
    "gemini-pro",               
]

# --- HÀM ĐỌC DRIVE (CHẠY NGẦM) ---
@st.cache_resource(ttl=3600)
def load_drive_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        full_text = ""
        file_list = []
        
        for file in files:
            fname = file['name']
            if "google-apps" in file['mimeType']: continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                
                content = ""
                if fname.endswith(".docx"):
                    doc = Document(fh)
                    for p in doc.paragraphs: content += p.text + "\n"
                elif fname.endswith(".pdf"):
                    reader = PdfReader(fh)
                    for page in reader.pages: content += page.extract_text() + "\n"
                
                if content:
                    full_text += f"\n--- TÀI LIỆU: {fname} ---\n{content}\n"
                    file_list.append(fname)
            except:
                continue 
                
        return full_text, file_list
    except Exception as e:
        return None, str(e)

# --- HÀM XỬ LÝ AI ---
def ask_gemini(prompt):
    for model_name in MODEL_LIST:
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text 
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    time.sleep(2) 
                    continue 
                elif "404" in error_str:
                    break 
                else:
                    break
    return None

# --- GIAO DIỆN CHÍNH ---

# 1. HEADER BANNER (Phần đầu trang xịn xò)
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 10px;">🛡️</div>
    <p class="header-title">HỆ THỐNG TRỢ LÝ ẢO PCCC & CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

# Load dữ liệu ngầm
with st.spinner('Đang đồng bộ dữ liệu...'):
    knowledge, list_files = load_drive_data()

if list_files:
    st.toast(f"Đã kết nối cơ sở dữ liệu ({len(list_files)} văn bản).", icon="✅")
else:
    st.error("Không thể kết nối dữ liệu. Vui lòng kiểm tra lại.")
    st.stop()

# 2. KHUNG CHÀO MỪNG (Chỉ hiện khi chưa có tin nhắn nào)
if "messages" not in st.session_state:
    st.session_state.messages = []

if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; border: 1px solid #e9ecef; text-align: center; margin-bottom: 30px;'>
        <h3 style='color: #B71C1C; margin: 0 0 10px 0;'>XIN CHÀO!</h3>
        <p style='font-size: 16px; color: #444; line-height: 1.6;'>
            Tôi là Trợ lý AI được phát triển bởi <b>Đại úy Phạm Tùng Linh (Phòng PC07)</b>.<br>
            Tôi sẵn sàng giải đáp mọi thắc mắc về quy chuẩn, tiêu chuẩn PCCC.
        </p>
        <p style='color: #666; font-style: italic; font-size: 14px;'>👇 Mời bạn đặt câu hỏi bên dưới 👇</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    # Tùy chỉnh icon: Người dùng là mặt cười, AI là xe cứu hỏa
    avatar = "👤" if msg["role"] == "user" else "🚒"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Xử lý câu hỏi
if prompt := st.chat_input("Nhập nội dung cần tra cứu..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # PROMPT ĐÃ CHỈNH SỬA (Cấm xưng danh lại)
    final_prompt = f"""
    Bạn là Trợ lý AI PCCC chuyên nghiệp.
    
    DỮ LIỆU LUẬT (CƠ SỞ TRẢ LỜI DUY NHẤT):
    {knowledge}
    
    NGUYÊN TẮC TRẢ LỜI: 
    1. Trả lời TRỰC TIẾP vào câu hỏi. KHÔNG giới thiệu lại bản thân (Ví dụ: Đừng nói "Tôi là trợ lý...").
    2. Ngắn gọn, súc tích, dễ hiểu.
    3. BẮT BUỘC trích dẫn điều luật/tên văn bản làm căn cứ.
    4. Giọng văn lịch sự, nghiêm túc.
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang tra cứu...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống bận. Vui lòng thử lại.")
