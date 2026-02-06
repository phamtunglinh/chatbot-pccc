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
def load_drive_data_categorized():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        groups = {"all": ""}
        file_count = 0
        
        for file in files:
            if "google-apps" in file['mimeType']: continue 
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    for p in doc.paragraphs: content += p.text + "\n"
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    for page in reader.pages: content += page.extract_text() + "\n"
                
                if content:
                    formatted_content = f"\n=== BẮT ĐẦU VĂN BẢN: {file['name']} ===\n{content}\n=== KẾT THÚC VĂN BẢN: {file['name']} ===\n"
                    groups["all"] += formatted_content
                    file_count += 1
            except: continue 
            
        return groups["all"], file_count
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
with st.spinner('Đang nạp dữ liệu Drive và cài đặt thuật toán xử lý...'):
    knowledge, count = load_drive_data_categorized()

if knowledge:
    if "data_loaded_msg" not in st.session_state:
        st.toast(f"Đã nạp {count} văn bản. Đã kích hoạt Logic nghiệp vụ.", icon="✅")
        st.session_state.data_loaded_msg = True
else:
    st.error("Chưa tìm thấy tài liệu nào trong Drive."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Tôi tuân thủ: <b>Chỉ dùng dữ liệu Drive + Áp dụng đúng thuật toán phân tích.</b>
        </p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử
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

    # --- PROMPT HOÀN HẢO: DỮ LIỆU DRIVE + LOGIC NGHIỆP VỤ ---
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    
    DỮ LIỆU ĐƯỢC PHÉP SỬ DỤNG (CONTEXT):
    {knowledge}
    
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 NGUYÊN TẮC CỐT LÕI (KHÔNG ĐƯỢC VI PHẠM):
    1. CHỈ sử dụng thông tin có trong phần "DỮ LIỆU ĐƯỢC PHÉP SỬ DỤNG".
    2. KHÔNG sử dụng kiến thức bên ngoài về các Nghị định (136, 50, 106...) nếu chúng không có trong dữ liệu.
    3. NGOẠI LỆ DUY NHẤT: Được phép dùng kiến thức về **QCVN 06:2022/BXD** và **Sửa đổi 1:2023** để trả lời câu hỏi kỹ thuật (nếu trong dữ liệu bị thiếu).
    
    -----------------------------------------------------
    ⚡ CÁC THUẬT TOÁN TƯ DUY BẮT BUỘC PHẢI ÁP DỤNG:
    
    🔵 1. THUẬT TOÁN XÁC ĐỊNH LOẠI HÌNH & THẨM QUYỀN QUẢN LÝ (Khi hỏi: Ai quản lý? Cơ sở này thuộc diện nào?):
       - Bước 1: Tính toán công năng chính (Nếu 1 công năng > 70% diện tích -> Công năng chính. Nếu không -> Hỗn hợp).
       - Bước 2: Tìm kiếm Phụ lục phân cấp (Phụ lục I, II, III...) TRONG DỮ LIỆU ĐÃ NẠP.
       - Bước 3: Đối chiếu thông số (Tầng, Khối tích) với Phụ lục tìm được.
       - Bước 4: Kết luận (Ưu tiên Phụ lục II - PC07 quản lý).
    
    🔴 2. THUẬT TOÁN SÀNG LỌC THẨM QUYỀN XỬ PHẠT (Khi hỏi: Lỗi này phạt bao nhiêu? Ai ký?):
       - Bước 1: Tìm hành vi trong Dữ liệu (NĐ 106 hoặc văn bản tương đương có trong Drive).
       - Bước 2: Xác định Mức phạt tiền (Cá nhân/Tổ chức) + Hình thức phạt bổ sung (Tước, Tịch thu...) + KPHQ.
       - Bước 3: SÀNG LỌC NGƯỜI CÓ THẨM QUYỀN (Dựa trên NĐ 189 hoặc Luật XLVPHC có trong dữ liệu):
         + Loại bỏ ngay người có Thẩm quyền phạt tiền < Mức phạt của hành vi.
         + Loại bỏ người không có quyền áp dụng hình thức phạt bổ sung (nếu hành vi có phạt bổ sung).
       - Bước 4: Trả lời theo Form: Mức tiền -> Phạt bổ sung -> Danh sách người đủ điều kiện -> Đề xuất.
    
    🟢 3. KHI HỎI VỀ HỒ SƠ / THỦ TỤC:
       - Ưu tiên tìm kiếm trong **Nghị định 105/2025/NĐ-CP** (Điều 4, Điều 13...) có trong dữ liệu.
       - Nếu không có NĐ 105 mới tìm các văn bản khác trong dữ liệu.
       - Tuyệt đối không lấy danh mục hồ sơ từ văn bản xử phạt.
    
    -----------------------------------------------------
    YÊU CẦU TRÌNH BÀY:
    - Trích dẫn rõ: "Theo Khoản..., Điều..., Văn bản [Tên file]...".
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang rà soát dữ liệu và áp dụng thuật toán...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống bận.")
