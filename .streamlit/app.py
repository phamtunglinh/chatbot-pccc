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

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="PCCC & CNCH Phú Thọ",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS TÙY CHỈNH ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    ::-webkit-scrollbar {width: 8px;}
    ::-webkit-scrollbar-thumb {background: #ccc; border-radius: 4px;}
    .stChatInput {border-radius: 20px;}
    
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 2rem 1rem;
        border-radius: 0 0 15px 15px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        margin-top: -60px;
        margin-bottom: 25px;
    }
    .header-title {
        font-size: 32px; font-weight: 900; text-transform: uppercase;
        margin: 0; letter-spacing: 1.5px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .header-subtitle {
        font-size: 15px; opacity: 0.95; margin-top: 8px; font-weight: 400; letter-spacing: 0.5px;
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
MODEL_LIST = ["gemini-flash-latest", "gemini-2.0-flash-lite-preview-09-2025", "gemini-pro"]

# --- HÀM ĐỌC DRIVE ---
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
            except: continue 
        return full_text, file_list
    except Exception as e: return None, str(e)

# --- HÀM XỬ LÝ AI ---
def ask_gemini(full_prompt):
    for model_name in MODEL_LIST:
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                # Tăng max_tokens để AI có thể suy luận dài hơn
                response = model.generate_content(full_prompt)
                return response.text 
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    time.sleep(2); continue 
                elif "404" in error_str: break 
                else: break
    return None

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 45px; margin-bottom: 10px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI VỀ PCCC VÀ CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('Đang đồng bộ dữ liệu...'):
    knowledge, list_files = load_drive_data()

if list_files:
    st.toast("Đã kết nối cơ sở dữ liệu.", icon="✅")
else:
    st.error("Không thể kết nối dữ liệu."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 25px; border-radius: 15px; border: 1px solid #e9ecef; text-align: center; margin-bottom: 30px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);'>
        <h3 style='color: #B71C1C; margin: 0 0 15px 0; font-size: 22px;'>XIN CHÀO!</h3>
        <p style='font-size: 16px; color: #333; line-height: 1.6;'>
            Tôi là Trợ lý AI được phát triển bởi <b>Đại úy Phạm Tùng Linh (Phòng PC07)</b>.<br>
            Tôi có khả năng <b>phân tích hồ sơ, tính toán thông số kỹ thuật</b> dựa trên quy chuẩn.
        </p>
        <hr style="width: 50px; margin: 15px auto; border-top: 2px solid #B71C1C;">
        <p style='color: #666; font-style: italic; font-size: 14px;'>👇 Mời bạn đặt câu hỏi bên dưới 👇</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🚒"
    with st.chat_message(msg["role"], avatar=avatar): st.markdown(msg["content"])

# XỬ LÝ CÂU HỎI
if prompt := st.chat_input("Nhập nội dung... (Ví dụ: Tính bể nước cho nhà Karaoke 5 tầng)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # --- TẠO CHUỖI LỊCH SỬ CHAT (ĐỂ AI NHỚ ĐƯỢC CÂU TRƯỚC) ---
    # Đây là chìa khóa để AI biết hỏi lại và nhớ thông tin cũ
    chat_history_text = ""
    for msg in st.session_state.messages[-6:]: # Chỉ nhớ 6 câu gần nhất để tiết kiệm bộ nhớ
        role_name = "Người dùng" if msg["role"] == "user" else "AI"
        chat_history_text += f"{role_name}: {msg['content']}\n"

    # --- NÂNG CẤP PROMPT THÀNH CHUYÊN GIA PHÂN TÍCH ---
    final_prompt = f"""
    VAI TRÒ: Bạn là Chuyên gia Thẩm duyệt & Nghiệm thu PCCC (Đại úy Phạm Tùng Linh).
    
    DỮ LIỆU LUẬT (TRA CỨU):
    {knowledge}
    
    LỊCH SỬ TRÒ CHUYỆN (ĐỂ SUY LUẬN):
    {chat_history_text}
    
    NHIỆM VỤ VÀ TƯ DUY (QUAN TRỌNG):
    1. **PHÂN TÍCH:** Khi nhận câu hỏi, hãy đối chiếu với Dữ liệu luật xem đã đủ thông tin để kết luận chưa.
    2. **HỎI LẠI:** Nếu thiếu thông tin quan trọng (ví dụ: diện tích, chiều cao, công năng, số tầng...), ĐỪNG trả lời chung chung. Hãy hỏi ngược lại người dùng để lấy thông số.
    3. **TÍNH TOÁN:** Nếu có số liệu, hãy thực hiện tính toán cụ thể (ví dụ: tính m3 nước, tính lối thoát nạn) rồi so sánh với Quy chuẩn.
    4. **TRẢ LỜI:** Ngắn gọn, trích dẫn điều luật. Không chào hỏi lại.
    
    OUTPUT CỦA AI (Chỉ đưa ra câu trả lời):
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang phân tích & suy luận...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống bận. Vui lòng thử lại.")
