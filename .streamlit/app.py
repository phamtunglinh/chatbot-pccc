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
        CHAR_LIMIT = 200000 
        
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
                    # Đánh dấu rõ tên file để AI biết nội dung này từ đâu ra
                    full_text += f"\n--- BẮT ĐẦU VĂN BẢN: {fname} ---\n{content}\n--- KẾT THÚC VĂN BẢN: {fname} ---\n"
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
with st.spinner('Đang đọc và phân tích các văn bản trong Drive...'):
    knowledge, list_files = load_drive_data()

if list_files:
    if "data_loaded_msg" not in st.session_state:
        st.toast(f"Đã đọc {len(list_files)} văn bản từ Drive.", icon="✅")
        st.session_state.data_loaded_msg = True
else:
    st.error("Chưa kết nối được dữ liệu hoặc thư mục Drive trống."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Tôi chỉ trả lời dựa trên chính xác các văn bản anh đã cung cấp trong Drive.
        </p>
        <p style='font-size: 13px; color: #666; font-style: italic;'>👇 Hãy nhập câu hỏi bên dưới 👇</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🚒"
    with st.chat_message(msg["role"], avatar=avatar): st.markdown(msg["content"])

# XỬ LÝ CÂU HỎI
if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # Lịch sử chat
    chat_history = ""
    for msg in st.session_state.messages[-4:]:
        chat_history += f"{msg['role']}: {msg['content']}\n"

    # --- PROMPT "KHÓA MIỆNG" - CHỈ ĐƯỢC DÙNG DỮ LIỆU DRIVE ---
    final_prompt = f"""
    VAI TRÒ: Bạn là một "MÁY ĐỌC VĂN BẢN THÔNG MINH".
    
    DỮ LIỆU ĐẦU VÀO DUY NHẤT (CONTEXT):
    {knowledge}
    
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 CHỈ THỊ TUYỆT ĐỐI (KHÔNG ĐƯỢC VI PHẠM):
    1. Nhiệm vụ duy nhất của bạn là: Đọc nội dung trong phần "DỮ LIỆU ĐẦU VÀO DUY NHẤT" ở trên để trả lời câu hỏi.
    2. TUYỆT ĐỐI KHÔNG sử dụng kiến thức bên ngoài (kiến thức đã được huấn luyện trước đó) nếu thông tin đó không xuất hiện trong Dữ liệu đầu vào.
    3. Nếu câu trả lời không có trong Dữ liệu đầu vào -> Hãy trả lời thẳng: "Nội dung này không tìm thấy trong các văn bản đã được nạp trên hệ thống."
    4. Khi trả lời, phải trích dẫn rõ: "Thông tin này nằm ở văn bản nào? Điều mấy? Khoản mấy?" (Dựa trên tên file tôi đã đánh dấu).

    -----------------------------------------------------
    HƯỚNG DẪN XỬ LÝ CỤ THỂ:
    
    - Nếu hỏi về "HỒ SƠ, THỦ TỤC": Hãy tìm các file có tên liên quan đến Nghị định 136, Nghị định 50 hoặc Luật PCCC trong dữ liệu. Đọc kỹ các điều khoản về hồ sơ để trả lời. Không được bịa ra hồ sơ nếu văn bản không ghi.
    
    - Nếu hỏi về "KỸ THUẬT": Hãy tìm trong các file QCVN 06, QC10, TCVN... (nếu có trong dữ liệu). Nếu trong dữ liệu chỉ có QCVN 06 thì chỉ trả lời theo QCVN 06.
    
    - Nếu hỏi về "XỬ PHẠT": Hãy tìm trong các file Nghị định xử phạt (106, 189...). Nếu không có file xử phạt trong dữ liệu -> Báo không tìm thấy.
    
    - Về logic phân tích (Thẩm quyền, công năng 70%...): Bạn được phép dùng khả năng tư duy logic để phân tích Dữ liệu đầu vào, NHƯNG dữ liệu gốc (số liệu, quy định) phải lấy từ văn bản.

    -----------------------------------------------------
    CÂU HỎI CỦA NGƯỜI DÙNG: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang đọc tài liệu trong Drive...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống bận. Vui lòng thử lại.")
