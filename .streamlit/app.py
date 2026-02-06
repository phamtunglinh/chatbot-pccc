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
        CHAR_LIMIT = 150000 
        
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

# Load dữ liệu
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
            Tôi chuyên giải đáp về thẩm quyền quản lý, xử phạt, thẩm duyệt PCCC.
        </p>
        <p style='font-size: 13px; color: #666; font-style: italic;'>👇 Hãy nhập câu hỏi bên dưới 👇</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🚒"
    with st.chat_message(msg["role"], avatar=avatar): st.markdown(msg["content"])

# XỬ LÝ CÂU HỎI
if prompt := st.chat_input("Nhập câu hỏi... (VD: Lỗi hàn cắt kim loại không che chắn phạt bao nhiêu?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # Lịch sử chat
    chat_history = ""
    for msg in st.session_state.messages[-4:]:
        chat_history += f"{msg['role']}: {msg['content']}\n"

    # --- PROMPT NGHIỆP VỤ CAO CẤP (ĐÃ CẬP NHẬT LOGIC MỚI) ---
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    DỮ LIỆU LUẬT (Nghị định 106/2025, 189/2025, v.v...): {knowledge}
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 QUY TRÌNH SUY LUẬN NGHIỆP VỤ (BẮT BUỘC TUÂN THỦ):

    # PHẦN 1: NẾU HỎI VỀ THẨM QUYỀN QUẢN LÝ (Cơ sở thuộc Phụ lục mấy, ai quản lý?)
    - Áp dụng logic: Xác định công năng chính (Quy tắc 70%) -> Đối chiếu Phụ lục -> Kết luận (Ưu tiên Phụ lục II).

    # PHẦN 2: NẾU HỎI VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH
    Bạn hãy thực hiện đúng trình tự suy luận sau:
    
    BƯỚC 1: XÁC ĐỊNH MỨC PHẠT (Theo NĐ 106/2025/NĐ-CP)
    - Tìm mức phạt tiền đối với CÁ NHÂN.
    - Suy ra mức phạt đối với TỔ CHỨC (= 2 lần mức cá nhân).
    - Lưu ý: Mức phạt tiền tối đa lĩnh vực PCCC là 50.000.000 đồng.
    
    BƯỚC 2: KIỂM TRA HÌNH THỨC PHẠT BỔ SUNG & KHẮC PHỤC HẬU QUẢ
    - Kiểm tra kỹ xem hành vi đó có bị: Tước giấy phép/chứng chỉ? Đình chỉ hoạt động? Tịch thu tang vật? Trục xuất không?
    - Kiểm tra kỹ xem có Biện pháp khắc phục hậu quả không?
    
    BƯỚC 3: XÁC ĐỊNH THẨM QUYỀN RA QUYẾT ĐỊNH (Theo NĐ 189/2025/NĐ-CP)
    - Nguyên tắc "HỘI TỤ ĐỦ": Người ra quyết định phải là người CÓ ĐỦ QUYỀN HẠN ở cả 3 yếu tố:
      1. Đủ thẩm quyền phạt số tiền (đến mức tối đa của khung phạt).
      2. Đủ thẩm quyền phạt bổ sung (nếu có).
      3. Đủ thẩm quyền áp dụng biện pháp khắc phục hậu quả (nếu có).
    
    ⚠️ VÍ DỤ TƯ DUY:
    - Lỗi A phạt 5 triệu (Đội trưởng phạt được).
    - Nhưng Lỗi A có phạt bổ sung "Tịch thu tang vật". Mà Đội trưởng không được tịch thu -> Phải đẩy lên Trưởng phòng.
    => KẾT LUẬN: Trưởng phòng ra quyết định.

    BƯỚC 4: TRÌNH BÀY CÂU TRẢ LỜI (ĐÚNG FORM MẪU SAU):
    --------------------------------------------------
    1. Mức tiền phạt:
       - Cá nhân: Từ ... đến ... đồng.
       - Tổ chức: Từ ... đến ... đồng.
       - Căn cứ: Điểm ..., Khoản ..., Điều ... Nghị định 106/2025/NĐ-CP.
    2. Hình thức phạt bổ sung: [Ghi cụ thể hoặc ghi "Không"]
    3. Biện pháp khắc phục hậu quả: [Ghi cụ thể hoặc ghi "Không"]
    4. Phân tích và Kết luận thẩm quyền:
       - Phân tích: [Ví dụ: Vì mức phạt là X, tuy nhiên có hình thức phạt bổ sung Y nên Đội trưởng không đủ thẩm quyền...]
       - Kết luận: Người có thẩm quyền ra quyết định là [Tên chức danh].
    --------------------------------------------------
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang tra cứu và lập biên bản ảo...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống đang bận. Vui lòng thử lại sau 10 giây.")
