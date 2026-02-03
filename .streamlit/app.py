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

# --- DANH SÁCH MODEL (ĐÃ CHỈNH SỬA ĐỂ TRÁNH LỖI 404/429) ---
# Ưu tiên dùng bản Lite (Nhẹ) và bản 2.0 mới nhất có trong tài khoản của anh
MODEL_LIST = [
    "gemini-2.0-flash-lite-preview-02-05", # Bản siêu nhẹ mới nhất
    "gemini-2.0-flash-lite-preview-09-2025", # Bản nhẹ dự phòng
    "gemini-2.0-flash", # Bản chuẩn
]

# --- HÀM ĐỌC DRIVE (CÓ PHANH AN TOÀN) ---
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
        total_chars = 0
        CHAR_LIMIT = 600000 # Giới hạn khoảng 150k-200k tokens để không sập quota
        
        for file in files:
            # Nếu đã nạp quá nhiều chữ -> Dừng nạp tiếp để bảo vệ App
            if total_chars > CHAR_LIMIT:
                break
                
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
                    total_chars += len(content)
            except: continue 
            
        return full_text, file_list, total_chars
    except Exception as e: return None, str(e), 0

# --- HÀM XỬ LÝ AI ---
def ask_gemini(full_prompt):
    debug_error = ""
    for model_name in MODEL_LIST:
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt)
                return response.text, None 
            except Exception as e:
                error_str = str(e)
                debug_error += f"\n- {model_name}: {error_str}"
                
                if "429" in error_str or "quota" in error_str.lower():
                    time.sleep(4) # Nghỉ lâu hơn chút
                    continue 
                elif "404" in error_str:
                    break 
                else:
                    break
    return None, debug_error

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 45px; margin-bottom: 10px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI VỀ PCCC VÀ CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('Đang đồng bộ dữ liệu...'):
    knowledge, list_files, total_chars = load_drive_data()

if list_files:
    # Cảnh báo nếu dữ liệu quá lớn (Chỉ admin thấy)
    if total_chars >= 600000:
        st.toast(f"⚠️ Cảnh báo: Dữ liệu quá lớn ({total_chars} ký tự). Hệ thống đã tự động cắt bớt để tránh sập.", icon="⚡")
    else:
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
if prompt := st.chat_input("Nhập nội dung... (Ví dụ: Cơ sở karaoke 5 tầng do ai quản lý?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # Lịch sử chat (Rút gọn còn 4 câu để tiết kiệm Token)
    chat_history_text = ""
    for msg in st.session_state.messages[-4:]: 
        role_name = "Người dùng" if msg["role"] == "user" else "AI"
        chat_history_text += f"{role_name}: {msg['content']}\n"

    # --- PROMPT NGHIỆP VỤ CAO CẤP ---
    final_prompt = f"""
    VAI TRÒ: Chuyên gia Thẩm duyệt PCCC (Đại úy Phạm Tùng Linh).
    
    DỮ LIỆU LUẬT (TRA CỨU):
    {knowledge}
    
    LỊCH SỬ TRÒ CHUYỆN:
    {chat_history_text}
    
    NHIỆM VỤ: Phân tích và xác định thẩm quyền quản lý hoặc giải đáp thắc mắc.
    
    THUẬT TOÁN XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (BẮT BUỘC ÁP DỤNG KHI CÓ CÂU HỎI VỀ PHÂN CẤP QUẢN LÝ):
    
    Bước 1: Kiểm tra dữ liệu đầu vào.
    - Nếu thiếu thông tin (Diện tích, số tầng, khối tích, công năng chi tiết), HÃY HỎI NGƯỢC LẠI người dùng. Đừng đoán mò.
      
    Bước 2: Xác định công năng chính (Logic 70%):
    - Tính % diện tích của từng công năng.
    - Nếu công năng nào > 70% -> Công năng chính.
    - Nếu không -> Nhà hỗn hợp.
    
    Bước 3: Đối chiếu Phụ lục (Nghị định 136/2020 hoặc NĐ 50/2024 tùy dữ liệu):
    - So sánh Số tầng, Diện tích, Khối tích với Phụ lục I (Xã quản lý) và Phụ lục II (Công an quản lý).
    
    Bước 4: Kết luận (Quy tắc ưu tiên):
    - Nếu đạt điều kiện Phụ lục II -> PHÒNG CẢNH SÁT PCCC & CNCH QUẢN LÝ.
    - Nếu chỉ đạt Phụ lục I và KHÔNG đạt Phụ lục II -> UBND CẤP XÃ QUẢN LÝ.
    
    YÊU CẦU TRẢ LỜI:
    - Rõ ràng, mạch lạc, có tính toán.
    - Không chào hỏi lại.
    
    INPUT NGƯỜI DÙNG: {prompt}
    OUTPUT CỦA AI:
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang phân tích hồ sơ...*")
        
        reply, err_log = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            st.error("⚠️ Hệ thống đang quá tải. Vui lòng đợi 10 giây rồi thử lại.")
            with st.expander("Chi tiết lỗi kỹ thuật:"):
                st.code(err_log)
