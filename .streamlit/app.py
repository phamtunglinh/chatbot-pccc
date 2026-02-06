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
    .stAlert {padding: 0.5rem;}
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI HỆ THỐNG ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình Secrets: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- HÀM KIỂM TRA MODEL KHẢ DỤNG (CHỮA LỖI 404) ---
@st.cache_resource
def get_available_model():
    # Danh sách ưu tiên
    preferred_models = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-pro"]
    try:
        available_models = [m.name for m in genai.list_models()]
        # Tìm model tốt nhất có trong danh sách khả dụng
        for model in preferred_models:
            if model in available_models:
                return model.replace("models/", "") # Trả về tên sạch (vd: gemini-1.5-flash)
        # Nếu không thấy cái nào quen, lấy cái đầu tiên generateContent được
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                return m.name.replace("models/", "")
    except Exception as e:
        return "gemini-pro" # Fallback an toàn nhất
    return "gemini-pro"

# Xác định model sẽ dùng ngay khi chạy app
ACTIVE_MODEL_NAME = get_available_model()

# --- HÀM ĐỌC DRIVE (GOM KHÔNG BỎ SÓT) ---
@st.cache_resource(ttl=3600)
def load_drive_data_categorized():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        groups = {
            "xu_phat": "",  
            "ky_thuat": "", 
            "thu_tuc": "",  # Nhóm này sẽ chứa cả Thủ tục + Các file chưa phân loại
            "debug_info": {"xu_phat": [], "ky_thuat": [], "thu_tuc": []}
        }
        
        file_count = 0
        
        for file in files:
            fname = file['name'].lower()
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
                    formatted_content = f"\n=== FILE: {file['name']} ===\n{content}\n=== HẾT FILE ===\n"
                    
                    # --- PHÂN LOẠI MỚI (CHẶT CHẼ HƠN) ---
                    # 1. Nhóm Xử phạt (Ưu tiên cao nhất)
                    if any(x in fname for x in ["106", "189", "144", "xử phạt", "vi phạm", "xphc"]):
                        groups["xu_phat"] += formatted_content
                        groups["debug_info"]["xu_phat"].append(file['name'])
                    
                    # 2. Nhóm Kỹ thuật
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "tiêu chuẩn", "quy chuẩn", "kỹ thuật"]):
                        groups["ky_thuat"] += formatted_content
                        groups["debug_info"]["ky_thuat"].append(file['name'])

                    # 3. Nhóm Thủ tục & Còn lại (GOM HẾT VÀO ĐÂY ĐỂ KHÔNG SÓT NĐ 105)
                    else:
                        groups["thu_tuc"] += formatted_content
                        groups["debug_info"]["thu_tuc"].append(file['name'])
                    
                    file_count += 1
            except: continue 
            
        return groups, file_count
    except Exception as e: return None, str(e)

# --- HÀM CHỌN DỮ LIỆU ---
def select_context(prompt, groups):
    prompt_lower = prompt.lower()
    
    if any(x in prompt_lower for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        # Hỏi phạt -> Lấy Xử phạt + Thủ tục (để tham chiếu hành vi)
        return groups["xu_phat"] + groups["thu_tuc"], "Xử phạt + Pháp lý"
        
    elif any(x in prompt_lower for x in ["mét", "chiều cao", "rộng", "khoảng cách", "trang bị", "lối thoát", "bậc"]):
        return groups["ky_thuat"], "Kỹ thuật (QC10, QCVN 06)"
        
    else:
        # Mặc định lấy nhóm Thủ tục (chứa NĐ 105, 136, 50...)
        return groups["thu_tuc"], "Hồ sơ & Thủ tục"

# --- HÀM GỌI AI (ĐƠN GIẢN HÓA) ---
def ask_gemini_safe(full_prompt):
    try:
        model = genai.GenerativeModel(ACTIVE_MODEL_NAME)
        response = model.generate_content(full_prompt)
        return response.text 
    except Exception as e:
        # Nếu lỗi quá tải, đợi chút rồi thử lại 1 lần
        if "429" in str(e):
            time.sleep(5)
            try:
                response = model.generate_content(full_prompt)
                return response.text
            except: pass
        return f"⚠️ Lỗi kết nối AI ({str(e)}). Vui lòng thử lại sau."

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI PCCC & CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

# Load dữ liệu
with st.spinner('Đang nạp dữ liệu từ Drive...'):
    data_groups, count = load_drive_data_categorized()

if not data_groups:
    st.error("Chưa kết nối được Drive."); st.stop()

# --- ADMIN PANEL: KIỂM TRA TRẠNG THÁI ---
with st.expander("🛠️ TRẠNG THÁI HỆ THỐNG (Bấm để xem)"):
    st.write(f"✅ **Model đang dùng:** `{ACTIVE_MODEL_NAME}` (Đã tự động chọn model tốt nhất)")
    st.write(f"📂 **Tổng số file:** {count}")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"Giỏ THỦ TỤC (Chứa NĐ 105...):\n" + str(len(data_groups["debug_info"]["thu_tuc"])) + " file")
        # In tên file để kiểm tra
        for f in data_groups["debug_info"]["thu_tuc"]: st.caption(f"- {f}")
    with c2:
        st.warning(f"Giỏ XỬ PHẠT:\n" + str(len(data_groups["debug_info"]["xu_phat"])) + " file")
    with c3:
        st.success(f"Giỏ KỸ THUẬT:\n" + str(len(data_groups["debug_info"]["ky_thuat"])) + " file")

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown(f"""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Hệ thống đang hoạt động trên nền tảng: <b>{ACTIVE_MODEL_NAME}</b>
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

    chat_history = ""
    for msg in st.session_state.messages[-4:]:
        chat_history += f"{msg['role']}: {msg['content']}\n"
    
    # 1. Chọn dữ liệu
    selected_knowledge, source_type = select_context(prompt, data_groups)

    # 2. Prompt
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    
    DỮ LIỆU SỬ DỤNG (CONTEXT):
    {selected_knowledge}
    
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 CHỈ THỊ TUYỆT ĐỐI:
    1. CHỈ TRẢ LỜI DỰA TRÊN DỮ LIỆU ĐÃ CUNG CẤP.
    2. Nếu không có thông tin -> Trả lời "Không tìm thấy trong dữ liệu hiện có".
    3. NGOẠI LỆ: Được dùng kiến thức QCVN 06:2022 cho câu hỏi kỹ thuật.
    
    CÁC QUY TẮC TRẢ LỜI:
    - **Hỏi Hồ sơ/Thủ tục:** Tìm kỹ trong các file thuộc nhóm Thủ tục (NĐ 105, 136, 50, Luật PCCC...). TUYỆT ĐỐI KHÔNG dùng NĐ 106 (Xử phạt) để trả lời câu hỏi "Hồ sơ gồm những gì".
    - **Hỏi Xử phạt:** Tìm trong NĐ 106, 189. Áp dụng logic Thẩm quyền (Tiền + Bổ sung).
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown(f"⏳ *Đang tra cứu ({source_type})...*")
        
        reply = ask_gemini_safe(final_prompt)
        
        full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
        message_placeholder.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
