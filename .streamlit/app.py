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
if prompt := st.chat_input("Nhập câu hỏi... (VD: Mức phạt lỗi không mua bảo hiểm cháy nổ bắt buộc?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)

    # Lịch sử chat
    chat_history = ""
    for msg in st.session_state.messages[-4:]:
        chat_history += f"{msg['role']}: {msg['content']}\n"

    # --- PROMPT NGHIỆP VỤ CAO CẤP (LOGIC SÀNG LỌC & ĐẦY ĐỦ TRƯỜNG) ---
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    DỮ LIỆU LUẬT (NĐ 106/2025, NĐ 189/2025...): {knowledge}
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 NHIỆM VỤ: XÁC ĐỊNH THẨM QUYỀN XỬ PHẠT VI PHẠM HÀNH CHÍNH
    
    BƯỚC 1: TÍNH TOÁN KHUNG PHẠT
    - Xác định mức phạt tiền đối với CÁ NHÂN và TỔ CHỨC (nhân đôi).
    - Tính MỨC PHẠT TRUNG BÌNH (để xác định thẩm quyền).
    
    BƯỚC 2: KIỂM TRA PHẠT BỔ SUNG & KHẮC PHỤC HẬU QUẢ (KPHQ)
    - Kiểm tra kỹ xem hành vi có Hình thức phạt bổ sung hoặc Biện pháp KPHQ nào không?
    
    BƯỚC 3: SÀNG LỌC VÀ XÁC ĐỊNH THẨM QUYỀN (QUAN TRỌNG)
    - Nguyên tắc SÀNG LỌC: So sánh Mức phạt tiền trung bình của hành vi với Thẩm quyền phạt tiền tối đa của các chức danh:
      + Chiến sĩ: 500k
      + Đội trưởng: 1.500.000đ (Check lại luật mới)
      + Trưởng CA cấp xã: 2.500.000đ
      + Chủ tịch xã: 5.000.000đ
      + Trưởng phòng PC07 / Trưởng CA huyện: 25.000.000đ (hoặc theo luật mới)
      + Giám đốc CA tỉnh / Chủ tịch huyện: 50.000.000đ (hoặc theo luật mới)
      + Chủ tịch Tỉnh / Cục trưởng: > 50.000.000đ
    
    - THỰC HIỆN LỌC:
      1. LOẠI BỎ NGAY lập tức các chức danh có thẩm quyền tiền < Mức phạt trung bình của hành vi. (Không được đưa vào danh sách trả lời để tránh dài dòng).
      2. CHỈ GIỮ LẠI các chức danh có thẩm quyền tiền >= Mức phạt.
      3. Với danh sách đã lọc được, tiếp tục kiểm tra quyền hạn về Phạt bổ sung/KPHQ. Nếu ai không đủ quyền phạt bổ sung -> Ghi chú rõ.

    BƯỚC 4: TRÌNH BÀY CÂU TRẢ LỜI (BẮT BUỘC ĐÚNG FORM SAU):
    --------------------------------------------------
    1. Mức tiền phạt:
       - Cá nhân: Từ ... đến ... đồng (Trung bình: ...).
       - Tổ chức: Từ ... đến ... đồng (Trung bình: ...).
       - Căn cứ: Điểm ..., Khoản ..., Điều ... Nghị định ...
       
    2. Hình thức phạt bổ sung: [Nếu có ghi cụ thể. Nếu không có BẮT BUỘC ghi: "Không"]
    
    3. Biện pháp khắc phục hậu quả: [Nếu có ghi cụ thể. Nếu không có BẮT BUỘC ghi: "Không"]

    4. Phân tích thẩm quyền xử phạt:
       *Chỉ xét các chức danh có thẩm quyền phạt tiền từ mức [...] trở lên:*
       
       - [Chức danh A]: 
         + Thẩm quyền phạt tiền tối đa: ... (Đủ/Không đủ).
         + Thẩm quyền phạt bổ sung/KPHQ: ... (Có/Không).
         => KẾT LUẬN: [Được phép ký / Không được phép ký].

       - [Chức danh B]: ... (Tương tự)
       
    5. Đề xuất:
       - Đề xuất trình [Chức danh thấp nhất nhưng đủ toàn bộ thẩm quyền] ra quyết định.
    --------------------------------------------------
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang tra cứu và sàng lọc thẩm quyền...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống đang bận. Vui lòng thử lại sau 10 giây.")
