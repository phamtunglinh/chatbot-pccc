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

# --- CSS GIAO DIỆN ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatInput {border-radius: 20px;}
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
    }
    .header-title {font-size: 28px; font-weight: 900; text-transform: uppercase; margin: 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);}
    .header-subtitle {font-size: 14px; opacity: 0.9; margin-top: 5px;}
    .stAlert {padding: 0.5rem;}
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI HỆ THỐNG ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DANH SÁCH MODEL ---
MODEL_LIST = [
    "gemini-2.0-flash-lite-preview-02-05", 
    "gemini-1.5-flash", 
    "gemini-flash-latest"
]

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
        total_chars = 0
        CHAR_LIMIT = 300000 # Tăng giới hạn lên một chút để đọc đủ luật xử phạt
        
        for file in files:
            if total_chars > CHAR_LIMIT: break 
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
        return full_text, file_list
    except Exception as e: return None, str(e)

# --- HÀM XỬ LÝ AI ---
def ask_gemini(full_prompt):
    for model_name in MODEL_LIST:
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt)
                return response.text 
            except Exception as e:
                time.sleep(2)
                continue
    return None

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI PCCC & CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

# Load dữ liệu (Chạy ngầm)
with st.spinner('Đang kết nối dữ liệu luật...'):
    knowledge, list_files = load_drive_data()

if list_files:
    if "data_loaded_msg" not in st.session_state:
        st.toast("Hệ thống đã sẵn sàng.", icon="✅")
        st.session_state.data_loaded_msg = True
else:
    st.error("Lỗi kết nối dữ liệu."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh (Phòng PC07)</b>.<br>
            Tôi chuyên giải đáp về thẩm quyền quản lý và tư vấn xử lý vi phạm hành chính.
        </p>
        <p style='font-size: 13px; color: #666; font-style: italic;'>👇 Hãy nhập câu hỏi bên dưới 👇</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🚒"
    with st.chat_message(msg["role"], avatar=avatar): st.markdown(msg["content"])

# XỬ LÝ CÂU HỎI
if prompt := st.chat_input("Nhập câu hỏi... (VD: Lỗi hàn cắt không che chắn phạt bao nhiêu? Ai ký?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # Lịch sử chat
    chat_history = ""
    for msg in st.session_state.messages[-4:]:
        chat_history += f"{msg['role']}: {msg['content']}\n"

    # --- PROMPT TỔNG HỢP (QUẢN LÝ + XỬ PHẠT) ---
    final_prompt = f"""
    VAI TRÒ: Bạn là Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    DỮ LIỆU LUẬT (TRA CỨU CHÍNH XÁC): {knowledge}
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 NHIỆM VỤ: Phân tích câu hỏi và áp dụng đúng 1 trong 2 quy trình suy luận sau:
    
    ------------------------------------------------------------------
    🔵 QUY TRÌNH 1: NẾU HỎI VỀ "AI QUẢN LÝ CƠ SỞ NÀY?" (PHÂN CẤP)
    1. Kiểm tra dữ liệu: Đã đủ Diện tích, Tầng, Khối tích chưa? Nếu thiếu phải hỏi lại.
    2. Xác định công năng chính (Quy tắc 70%):
       - Nếu 1 công năng > 70% diện tích -> Công năng chính.
       - Nếu không -> Nhà hỗn hợp.
    3. Đối chiếu Phụ lục (NĐ 136 hoặc NĐ 50):
       - Ưu tiên Phụ lục II (PC07 quản lý).
       - Chỉ khi không lọt vào Phụ lục II mới xét Phụ lục I (UBND Xã).
    4. Kết luận: Đơn vị quản lý.
    
    ------------------------------------------------------------------
    🔴 QUY TRÌNH 2: NẾU HỎI VỀ "XỬ PHẠT VI PHẠM" (TIỀN PHẠT & THẨM QUYỀN KÝ)
    
    1. BƯỚC 1: XÁC ĐỊNH KHUNG PHẠT (Theo NĐ 106/2025 hoặc văn bản trong dữ liệu)
       - Tìm mức phạt Cá nhân -> Suy ra Tổ chức (x2).
       - Tính Mức phạt trung bình của hành vi.
       - Kiểm tra kỹ: Có phạt Bổ sung (Tước giấy phép, tịch thu...) hay Khắc phục hậu quả không?
       - Trích dẫn căn cứ pháp lý: Điểm, Khoản, Điều...

    2. BƯỚC 2: SÀNG LỌC NGƯỜI CÓ THẨM QUYỀN (Theo NĐ 189/2025)
       - Nguyên tắc: Chỉ liệt kê những người ĐỦ ĐIỀU KIỆN (Thẩm quyền tiền >= Mức phạt TB hành vi VÀ Có quyền phạt bổ sung).
       - Tự động LOẠI BỎ những người không đủ thẩm quyền tiền (Ví dụ: Phạt 10tr thì không được liệt kê Chiến sĩ, Chủ tịch xã...).
       
    3. BƯỚC 3: TRẢ LỜI THEO MẪU SAU (BẮT BUỘC):
       * Về mức phạt:
         - Cá nhân: ... (Căn cứ ...)
         - Tổ chức: ...
       * Hình thức phạt bổ sung & KPHQ:
         - Bổ sung: [Ghi rõ hoặc ghi "Không"] (Căn cứ ...)
         - KPHQ: [Ghi rõ hoặc ghi "Không"] (Căn cứ ...)
       * Phân tích thẩm quyền giải quyết:
         (Chỉ liệt kê các chức danh đã qua sàng lọc ở Bước 2)
         - [Chức danh A]: Đủ thẩm quyền (Tiền tối đa ..., Quyền bổ sung ...). => ĐƯỢC KÝ.
         - [Chức danh B]: ...
       * Đề xuất: Trình [Chức danh thấp nhất đủ quyền] ra quyết định.
    
    ------------------------------------------------------------------
    YÊU CẦU CHUNG:
    - Trả lời ngắn gọn, đúng trọng tâm.
    - Luôn trích dẫn văn bản pháp luật cụ thể.
    
    CÂU HỎI CỦA NGƯỜI DÂN: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang tra cứu luật và phân tích thẩm quyền...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống đang bận. Vui lòng thử lại sau 10 giây.")
