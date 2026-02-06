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
import re

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
    "gemini-1.5-flash", 
    "gemini-2.0-flash-lite-preview-02-05",
    "gemini-flash-latest"
]

# --- HÀM ĐỌC DRIVE (CHIA NHÓM VĂN BẢN) ---
@st.cache_resource(ttl=3600)
def load_drive_data_categorized():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        # Tạo 3 giỏ dữ liệu
        groups = {
            "xu_phat": "",  # NĐ 106, 189, 144
            "ky_thuat": "", # QCVN 06, QC10, TCVN
            "thu_tuc": "",  # NĐ 136, 50, Luật PCCC
            "khac": ""      # Các file còn lại
        }
        
        file_count = 0
        
        for file in files:
            fname = file['name'].lower() # Chuyển tên file về chữ thường để dễ so sánh
            if "google-apps" in file['mimeType']: continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # Đọc nội dung
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    for p in doc.paragraphs: content += p.text + "\n"
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    for page in reader.pages: content += page.extract_text() + "\n"
                
                if content:
                    formatted_content = f"\n=== VĂN BẢN: {file['name']} ===\n{content}\n"
                    
                    # PHÂN LOẠI VÀO GIỎ (Logic phân loại tự động)
                    if any(x in fname for x in ["106", "189", "144", "xử phạt", "vi phạm"]):
                        groups["xu_phat"] += formatted_content
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "tiêu chuẩn", "quy chuẩn"]):
                        groups["ky_thuat"] += formatted_content
                    elif any(x in fname for x in ["136", "50", "luật pccc", "thẩm duyệt", "nghiệm thu"]):
                        groups["thu_tuc"] += formatted_content
                    else:
                        groups["khac"] += formatted_content
                    
                    file_count += 1
            except: continue 
            
        return groups, file_count
    except Exception as e: return None, str(e)

# --- HÀM CHỌN GIỎ DỮ LIỆU THÔNG MINH ---
def select_context(prompt, groups):
    prompt_lower = prompt.lower()
    
    # 1. Phát hiện hỏi về XỬ PHẠT
    if any(x in prompt_lower for x in ["phạt", "tiền", "lỗi", "vi phạm", "bao nhiêu tiền"]):
        # Khi phạt thì cần cả Luật xử phạt + Luật gốc (để đối chiếu hành vi)
        return groups["xu_phat"] + groups["thu_tuc"]
        
    # 2. Phát hiện hỏi về KỸ THUẬT
    elif any(x in prompt_lower for x in ["mét", "chiều cao", "rộng", "bậc", "khoảng cách", "trang bị", "lối thoát", "cầu thang"]):
        return groups["ky_thuat"]
        
    # 3. Phát hiện hỏi về THỦ TỤC / HỒ SƠ / QUẢN LÝ
    elif any(x in prompt_lower for x in ["hồ sơ", "thủ tục", "quản lý", "thẩm duyệt", "nghiệm thu", "ai quản lý"]):
        return groups["thu_tuc"]
        
    # 4. Trường hợp không rõ -> Gửi TẤT CẢ (An toàn nhất)
    else:
        return groups["xu_phat"] + groups["ky_thuat"] + groups["thu_tuc"] + groups["khac"]

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

# Load dữ liệu (Chỉ chạy 1 lần khi khởi động)
with st.spinner('Đang phân loại và nạp thư viện luật...'):
    data_groups, count = load_drive_data_categorized()

if data_groups:
    if "data_loaded_msg" not in st.session_state:
        st.toast(f"Đã nạp {count} văn bản vào hệ thống phân loại.", icon="✅")
        st.session_state.data_loaded_msg = True
else:
    st.error("Chưa kết nối được dữ liệu Drive."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Hệ thống đã kích hoạt <b>Bộ lọc dữ liệu thông minh</b> để trả lời chính xác nhất.
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
    
    # --- BỘ LỌC THÔNG MINH HOẠT ĐỘNG ---
    # Tự động chọn đúng tài liệu dựa trên câu hỏi
    selected_knowledge = select_context(prompt, data_groups)

    # --- PROMPT ---
    final_prompt = f"""
    VAI TRÒ: Chuyên gia PCCC & CNCH.
    
    DỮ LIỆU LUẬT ĐƯỢC CHỌN LỌC (CONTEXT):
    {selected_knowledge}
    
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 YÊU CẦU:
    1. Chỉ trả lời dựa trên DỮ LIỆU LUẬT ĐƯỢC CHỌN LỌC ở trên.
    2. Trích dẫn rõ ràng: "Theo Điểm..., Khoản..., Điều..., Văn bản...".
    
    QUY TẮC XỬ LÝ:
    - Nếu hỏi KỸ THUẬT: Ưu tiên QC10 (Trang bị) và QCVN 06:2022/Sửa đổi 1:2023 (Kiến trúc). KHÔNG dùng TCVN 3890.
    - Nếu hỏi HỒ SƠ/THỦ TỤC: Tra NĐ 136, NĐ 50. Không tra NĐ xử phạt.
    - Nếu hỏi XỬ PHẠT: Tra NĐ 106, 189. Áp dụng sàng lọc thẩm quyền (Tiền + Bổ sung).
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        # Hiển thị cho anh biết nó đang đọc cái gì (Debug)
        message_placeholder.markdown("⏳ *Đang kích hoạt bộ lọc dữ liệu chuyên ngành...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống bận.")
