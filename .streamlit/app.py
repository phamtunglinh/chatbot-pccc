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
    st.error(f"⚠️ Lỗi cấu hình: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- HÀM TỰ ĐỘNG TÌM MODEL TỐT NHẤT (CHỮA LỖI 404) ---
@st.cache_resource
def get_best_model():
    # Ưu tiên Flash (nhanh, rẻ) -> Pro (thông minh) -> Cũ
    priority_list = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]
    
    try:
        # Lấy danh sách model thực tế Google đang cấp cho tài khoản này
        available = [m.name.replace("models/", "") for m in genai.list_models()]
        
        for model in priority_list:
            if model in available:
                return model # Tìm thấy cái nào ngon nhất thì dùng ngay
                
        # Nếu không thấy cái nào trong list ưu tiên, lấy đại cái đầu tiên hỗ trợ chat
        return "gemini-pro"
    except:
        return "gemini-pro" # Fallback cuối cùng

# Kích hoạt model
ACTIVE_MODEL = get_best_model()

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
            "thu_tuc": "",  # Nhóm này quan trọng nhất
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
                    
                    # --- LOGIC PHÂN LOẠI MỚI (AN TOÀN HƠN) ---
                    # 1. Xử phạt: Chỉ khi tên file có chữ 'phạt' hoặc '106', '189'
                    if any(x in fname for x in ["106", "189", "144", "xử phạt", "vi phạm", "xphc"]):
                        groups["xu_phat"] += formatted_content
                        groups["debug_info"]["xu_phat"].append(file['name'])
                    
                    # 2. Kỹ thuật: Chỉ khi có chữ '06', 'qc10', 'tcvn'
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "tiêu chuẩn", "quy chuẩn", "kỹ thuật"]):
                        groups["ky_thuat"] += formatted_content
                        groups["debug_info"]["ky_thuat"].append(file['name'])

                    # 3. CÒN LẠI GOM HẾT VÀO THỦ TỤC (Chữa lỗi sót file NĐ 105/136)
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
    
    # Logic ưu tiên để tiết kiệm dung lượng (Tránh lỗi 429)
    if any(x in prompt_lower for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        return groups["xu_phat"] + groups["thu_tuc"], "Xử phạt + Pháp lý"
        
    elif any(x in prompt_lower for x in ["mét", "chiều cao", "rộng", "khoảng cách", "trang bị", "lối thoát", "bậc"]):
        return groups["ky_thuat"], "Kỹ thuật (QC10, QCVN 06)"
        
    else:
        # Nếu hỏi hồ sơ, thủ tục hoặc câu hỏi chung -> Lấy nhóm Thủ tục
        return groups["thu_tuc"], "Hồ sơ & Thủ tục"

# --- HÀM GỌI AI AN TOÀN (CHỮA LỖI 429 QUÁ TẢI) ---
def ask_gemini_safe(full_prompt):
    model = genai.GenerativeModel(ACTIVE_MODEL)
    try:
        response = model.generate_content(full_prompt)
        return response.text 
    except Exception as e:
        error_msg = str(e)
        # Nếu bị lỗi Quá tải (429) -> Tự động đợi 5s rồi thử lại
        if "429" in error_msg or "quota" in error_msg.lower():
            time.sleep(5) 
            try:
                response = model.generate_content(full_prompt)
                return response.text
            except: 
                return "⚠️ Hệ thống đang quá tải. Vui lòng đợi 30 giây rồi hỏi lại."
        return f"⚠️ Lỗi kết nối: {error_msg}"

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

# --- BẢNG ĐIỀU KHIỂN (ĐỂ ANH KIỂM TRA) ---
with st.expander("🛠️ TRẠNG THÁI HỆ THỐNG (Bấm để xem)"):
    st.write(f"✅ **Model hoạt động:** `{ACTIVE_MODEL}`")
    st.write(f"📂 **Tổng số file:** {count}")
    
    # Hiển thị rõ file nào nằm ở đâu
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"Giỏ THỦ TỤC & HỒ SƠ:\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["thu_tuc"]]))
    with c2:
        st.warning(f"Giỏ XỬ PHẠT:\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["xu_phat"]]))
    with c3:
        st.success(f"Giỏ KỸ THUẬT:\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["ky_thuat"]]))

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown(f"""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Hệ thống đang chạy trên nền tảng: <b>{ACTIVE_MODEL}</b>
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
    - **Hỏi Hồ sơ/Thủ tục:** Tìm trong các file thuộc giỏ THỦ TỤC (NĐ 105, 136, 50...). TUYỆT ĐỐI KHÔNG dùng NĐ 106 (Xử phạt) để trả lời về thành phần hồ sơ.
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
