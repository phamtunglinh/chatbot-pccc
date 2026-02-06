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

# --- MODEL (Dùng Flash vì nó nhanh và chịu tải tốt nhất) ---
MODEL_NAME = "gemini-1.5-flash"

# --- HÀM ĐỌC DRIVE (PHÂN LOẠI RỘNG RÃI HƠN) ---
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
            "file_names": {"xu_phat": [], "ky_thuat": [], "thu_tuc": [], "khac": []} # Để debug
        }
        
        file_count = 0
        
        for file in files:
            fname = file['name'].lower() # Chuyển tên file về chữ thường
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
                    
                    # --- PHÂN LOẠI (Từ khóa linh hoạt hơn) ---
                    # 1. XỬ PHẠT (106, 189, 144)
                    if any(x in fname for x in ["106", "189", "144", "xử phạt", "vi phạm", "xphc"]):
                        groups["xu_phat"] += formatted_content
                        groups["file_names"]["xu_phat"].append(file['name'])
                    
                    # 2. KỸ THUẬT (06, QC10, TCVN, 3890)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "tiêu chuẩn", "quy chuẩn", "kỹ thuật"]):
                        groups["ky_thuat"] += formatted_content
                        groups["file_names"]["ky_thuat"].append(file['name'])

                    # 3. THỦ TỤC (105, 136, 50, Luật)
                    # Lưu ý: Thêm các từ khóa như "nghị định", "luật" để bắt được nhiều hơn
                    elif any(x in fname for x in ["136", "50", "105", "luật", "thẩm duyệt", "nghiệm thu", "hồ sơ", "quản lý", "nghị định"]):
                        groups["thu_tuc"] += formatted_content
                        groups["file_names"]["thu_tuc"].append(file['name'])
                    
                    # 4. KHÁC
                    else:
                        groups["khac"] += formatted_content
                        groups["file_names"]["khac"].append(file['name'])
                    
                    file_count += 1
            except: continue 
            
        return groups, file_count
    except Exception as e: return None, str(e)

# --- HÀM CHỌN DỮ LIỆU ---
def select_context(prompt, groups):
    prompt_lower = prompt.lower()
    
    # Logic ưu tiên
    if any(x in prompt_lower for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        # Hỏi phạt -> Lấy Xử phạt + Thủ tục (để tham chiếu hành vi)
        return groups["xu_phat"] + groups["thu_tuc"], "Xử phạt + Thủ tục"
        
    elif any(x in prompt_lower for x in ["mét", "chiều cao", "rộng", "khoảng cách", "trang bị", "lối thoát", "bậc"]):
        # Hỏi kỹ thuật -> Lấy Kỹ thuật
        return groups["ky_thuat"], "Kỹ thuật (QC10, QCVN 06...)"
        
    elif any(x in prompt_lower for x in ["hồ sơ", "thủ tục", "quản lý", "thẩm duyệt", "nghiệm thu", "ai quản lý"]):
        # Hỏi hồ sơ -> Lấy Thủ tục (Tuyệt đối không lấy xử phạt để tránh nhầm)
        return groups["thu_tuc"], "Thủ tục (NĐ 136, 50, 105...)"
        
    else:
        # Không rõ -> Lấy tất (trừ kỹ thuật cho nhẹ)
        return groups["thu_tuc"] + groups["xu_phat"], "Tổng hợp"

# --- HÀM GỌI AI VỚI CƠ CHẾ "LÌ ĐÒN" (RETRY) ---
def ask_gemini_resilient(full_prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    # Thử tối đa 3 lần
    for attempt in range(3): 
        try:
            response = model.generate_content(full_prompt)
            return response.text 
        except Exception as e:
            error_msg = str(e)
            # Nếu gặp lỗi 429 (Quá tải) -> Nghỉ và thử lại
            if "429" in error_msg or "quota" in error_msg.lower():
                wait_time = (attempt + 1) * 5 # Lần 1 nghỉ 5s, lần 2 nghỉ 10s...
                time.sleep(wait_time)
                continue 
            # Nếu lỗi khác -> Bỏ qua
            else:
                return f"Lỗi kỹ thuật: {error_msg}"
    return "⚠️ Hệ thống Google đang quá tải (Lỗi 429). Vui lòng đợi khoảng 30 giây rồi hỏi lại."

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

# --- NÚT KIỂM TRA DỮ LIỆU (DEBUG) ---
# Anh bấm vào đây để xem AI đang đọc file nào
with st.expander("🛠️ KIỂM TRA DỮ LIỆU ĐẦU VÀO (Dành cho Admin)"):
    st.write("**Giỏ Thủ tục (Dùng cho câu hỏi Hồ sơ/Quản lý):**")
    st.info(", ".join(data_groups["file_names"]["thu_tuc"]) if data_groups["file_names"]["thu_tuc"] else "⚠️ Rỗng (Cần kiểm tra lại tên file)")
    
    st.write("**Giỏ Xử phạt:**")
    st.warning(", ".join(data_groups["file_names"]["xu_phat"]) if data_groups["file_names"]["xu_phat"] else "⚠️ Rỗng")

    st.write("**Giỏ Kỹ thuật:**")
    st.success(", ".join(data_groups["file_names"]["ky_thuat"]) if data_groups["file_names"]["ky_thuat"] else "⚠️ Rỗng")


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
    
    🛑 CHỈ THỊ TUYỆT ĐỐI (KHÔNG ĐƯỢC VI PHẠM):
    
    1. CHỈ TRẢ LỜI DỰA TRÊN DỮ LIỆU ĐƯỢC CUNG CẤP Ở TRÊN.
       - Nếu không tìm thấy thông tin trong dữ liệu -> Trả lời: "Nội dung này không tìm thấy trong các văn bản hiện có (NĐ 105, 136...)."
       - TUYỆT ĐỐI KHÔNG lấy quy định xử phạt (NĐ 106) để trả lời cho câu hỏi về "Thành phần hồ sơ". Nếu không có văn bản quy định hồ sơ, hãy báo là không có.
    
    2. NGOẠI LỆ DUY NHẤT (VỀ KỸ THUẬT):
       - Được phép dùng kiến thức về **QCVN 06:2022/BXD** và **Sửa đổi 1:2023** để trả lời câu hỏi kỹ thuật (lối thoát nạn, bậc chịu lửa...).
    
    3. CÁC THUẬT TOÁN BẮT BUỘC:
       - **Hỏi Hồ sơ/Thủ tục:** Tìm trong NĐ 105, 136, 50, Luật PCCC.
       - **Hỏi Xử phạt:** Tìm trong NĐ 106, 189. Áp dụng Sàng lọc thẩm quyền (Tiền + Bổ sung).
       - **Hỏi Quản lý:** Áp dụng công năng 70% + Phụ lục.
       
    YÊU CẦU TRÌNH BÀY:
    - Trích dẫn: "Theo Khoản..., Điều..., Văn bản [Tên file]...".
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        # Hiển thị trạng thái để biết đang đọc cái gì
        message_placeholder.markdown(f"⏳ *Đang tra cứu dữ liệu: {source_type}...*")
        
        # Gọi hàm AI "Lì đòn"
        reply = ask_gemini_resilient(final_prompt)
        
        full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
        message_placeholder.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
