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
import random

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

# --- DANH SÁCH MODEL (CƠ CHẾ DỰ PHÒNG) ---
# Nếu cái đầu lỗi, nó tự nhảy sang cái sau
MODEL_LIST = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.0-pro"
]

# --- HÀM ĐỌC DRIVE (MỞ RỘNG TỪ KHÓA) ---
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
            "thu_tuc": "",  
            "khac": "",
            "debug_info": {"xu_phat": [], "ky_thuat": [], "thu_tuc": [], "khac": []} # Để anh kiểm tra
        }
        
        file_count = 0
        
        for file in files:
            fname = file['name'].lower() # Chuyển tên file về chữ thường để so sánh
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
                    # Đóng dấu văn bản
                    formatted_content = f"\n=== BẮT ĐẦU TÀI LIỆU: {file['name']} ===\n{content}\n=== KẾT THÚC TÀI LIỆU: {file['name']} ===\n"
                    
                    # --- PHÂN LOẠI (Logic bắt dính) ---
                    # 1. XỬ PHẠT: Có chữ 106, 189, 144, xử phạt...
                    if any(x in fname for x in ["106", "189", "144", "xử phạt", "vi phạm", "xphc"]):
                        groups["xu_phat"] += formatted_content
                        groups["debug_info"]["xu_phat"].append(file['name'])
                    
                    # 2. KỸ THUẬT: Có chữ 06, qc10, tcvn, tiêu chuẩn...
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "tiêu chuẩn", "quy chuẩn", "kỹ thuật"]):
                        groups["ky_thuat"] += formatted_content
                        groups["debug_info"]["ky_thuat"].append(file['name'])

                    # 3. THỦ TỤC/HỒ SƠ: Có chữ 136, 50, 105, luật, hồ sơ, quản lý, nghị định...
                    elif any(x in fname for x in ["136", "50", "105", "luật", "thẩm duyệt", "nghiệm thu", "hồ sơ", "quản lý", "nghị định", "nd"]):
                        groups["thu_tuc"] += formatted_content
                        groups["debug_info"]["thu_tuc"].append(file['name'])
                    
                    # 4. KHÁC
                    else:
                        groups["khac"] += formatted_content
                        groups["debug_info"]["khac"].append(file['name'])
                    
                    file_count += 1
            except: continue 
            
        return groups, file_count
    except Exception as e: return None, str(e)

# --- HÀM CHỌN DỮ LIỆU ---
def select_context(prompt, groups):
    prompt_lower = prompt.lower()
    
    # Logic ưu tiên
    if any(x in prompt_lower for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        return groups["xu_phat"] + groups["thu_tuc"], "Xử phạt + Thủ tục"
        
    elif any(x in prompt_lower for x in ["mét", "chiều cao", "rộng", "khoảng cách", "trang bị", "lối thoát", "bậc"]):
        return groups["ky_thuat"], "Kỹ thuật"
        
    elif any(x in prompt_lower for x in ["hồ sơ", "thủ tục", "quản lý", "thẩm duyệt", "nghiệm thu", "ai quản lý"]):
        # Lấy Thủ tục (Tuyệt đối KHÔNG lấy xử phạt)
        return groups["thu_tuc"], "Thủ tục (NĐ 136, 50, 105...)"
        
    else:
        return groups["thu_tuc"] + groups["xu_phat"], "Tổng hợp"

# --- HÀM GỌI AI ĐA MODEL (CHỐNG LỖI 404 & 429) ---
def ask_gemini_resilient(full_prompt):
    debug_log = ""
    # Thử lần lượt từng Model trong danh sách
    for model_name in MODEL_LIST:
        # Với mỗi model, thử 2 lần nếu mạng lag
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt)
                return response.text 
            except Exception as e:
                error_msg = str(e)
                debug_log += f"\n- {model_name} (Lần {attempt+1}): {error_msg}"
                
                # Nếu lỗi 429 (Quá tải) -> Nghỉ 5s rồi thử lại
                if "429" in error_msg or "quota" in error_msg.lower():
                    time.sleep(5)
                    continue 
                # Nếu lỗi 404 (Không tìm thấy model) -> Bỏ qua model này, thử cái tiếp theo
                elif "404" in error_msg:
                    break 
                else:
                    time.sleep(2)
                    continue
    return f"⚠️ Hệ thống đang bận hoặc lỗi kết nối. Vui lòng thử lại sau ít phút.\n(Chi tiết kỹ thuật: {debug_log})"

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

if data_groups:
    if "data_loaded_msg" not in st.session_state:
        st.toast(f"Đã nạp {count} văn bản.", icon="✅")
        st.session_state.data_loaded_msg = True
else:
    st.error("Chưa kết nối được Drive."); st.stop()

# --- CÔNG CỤ KIỂM TRA (QUAN TRỌNG ĐỂ SỬA LỖI) ---
with st.expander("🛠️ ADMIN: KIỂM TRA DỮ LIỆU ĐÃ NẠP"):
    st.write("Dưới đây là danh sách file AI đã đọc được. Anh hãy kiểm tra xem NĐ 105 nằm ở đâu.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📂 Giỏ THỦ TỤC (Dùng cho câu hỏi Hồ sơ/Quản lý):\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["thu_tuc"]]))
        st.warning(f"📂 Giỏ XỬ PHẠT:\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["xu_phat"]]))
    with col2:
        st.success(f"📂 Giỏ KỸ THUẬT:\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["ky_thuat"]]))
        st.error(f"📂 Giỏ KHÁC (Chưa phân loại):\n" + "\n".join([f"- {f}" for f in data_groups["debug_info"]["khac"]]))

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; border: 1px solid #eee;'>
        <h3 style='color: #B71C1C; margin: 0;'>XIN CHÀO!</h3>
        <p style='font-size: 15px; color: #333; margin-top: 10px;'>
            Tôi là Trợ lý AI của <b>Đại úy Phạm Tùng Linh</b>.<br>
            Tôi hoạt động độc lập dựa trên dữ liệu văn bản nội bộ.
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

    # 2. Prompt chỉ đạo
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    
    DỮ LIỆU ĐƯỢC PHÉP SỬ DỤNG (CONTEXT):
    {selected_knowledge}
    
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 CHỈ THỊ TUYỆT ĐỐI:
    1. CHỈ TRẢ LỜI DỰA TRÊN DỮ LIỆU ĐÃ CUNG CẤP.
    2. Nếu dữ liệu không có -> Trả lời "Không tìm thấy".
    3. NGOẠI LỆ: Được dùng kiến thức về QCVN 06:2022 để trả lời câu hỏi kỹ thuật.
    
    CÁC QUY TẮC NGHIỆP VỤ:
    - Hỏi **Hồ sơ/Thủ tục**: Tìm trong NĐ 105, 136, 50, Luật PCCC. (Tuyệt đối không lấy từ luật xử phạt).
    - Hỏi **Xử phạt**: Tìm trong NĐ 106, 189. Áp dụng Logic sàng lọc thẩm quyền (Tiền + Bổ sung).
    - Hỏi **Quản lý**: Áp dụng công năng 70% + Phụ lục.
       
    YÊU CẦU TRÌNH BÀY:
    - Trích dẫn: "Theo Khoản..., Điều..., Văn bản [Tên file]...".
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown(f"⏳ *Đang tra cứu dữ liệu...*")
        
        reply = ask_gemini_resilient(final_prompt)
        
        full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
        message_placeholder.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
