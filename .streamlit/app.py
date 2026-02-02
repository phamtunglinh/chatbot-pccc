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

# --- CẤU HÌNH ---
st.set_page_config(page_title="Hệ thống PCCC & CNCH", page_icon="🚒", layout="wide")

# --- KẾT NỐI BẢO MẬT ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DANH SÁCH MODEL (Đã tối ưu) ---
MODEL_LIST = [
    "gemini-flash-latest",      # Ưu tiên 1
    "gemini-2.0-flash-lite-preview-09-2025", # Ưu tiên 2
    "gemini-pro",               # Ưu tiên 3
]

# --- HÀM ĐỌC DRIVE (CHẠY NGẦM) ---
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
        
        for file in files:
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
            except:
                continue 
                
        return full_text, file_list
    except Exception as e:
        return None, str(e)

# --- HÀM XỬ LÝ AI ---
def ask_gemini(prompt):
    for model_name in MODEL_LIST:
        for attempt in range(2): 
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text 
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    time.sleep(2) 
                    continue 
                elif "404" in error_str:
                    break 
                else:
                    break
    return None

# --- GIAO DIỆN CHÍNH ---
st.markdown("<h2 style='text-align: center; color: #CE1126;'>🔥 TRỢ LÝ AI PCCC & CNCH</h2>", unsafe_allow_html=True)

# Load dữ liệu (ẨN DANH SÁCH - Chỉ hiện thông báo nhỏ khi đang tải)
with st.spinner('Đang kết nối cơ sở dữ liệu văn bản...'):
    knowledge, list_files = load_drive_data()

if list_files is None:
    st.error("⚠️ Lỗi kết nối dữ liệu. Vui lòng liên hệ Admin.")
    st.stop()
else:
    # Thông báo nhỏ góc dưới xác nhận đã load xong (tùy chọn)
    st.toast(f"Đã cập nhật {len(list_files)} văn bản luật mới nhất.", icon="✅")

# LỜI CHÀO MỚI (CHUYÊN NGHIỆP)
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "Tôi là trợ lý AI về công tác PCCC và CNCH do Đại úy Phạm Tùng Linh - Phòng PC07 Công an tỉnh Phú Thọ phát triển.\n\nBạn hãy đặt câu hỏi để tôi có thể giải đáp các thắc mắc nhé."
    }]

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Xử lý câu hỏi
if prompt := st.chat_input("Nhập câu hỏi tại đây..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    final_prompt = f"""
    Bạn là Đại úy Phạm Tùng Linh, Trợ lý AI về PCCC & CNCH.
    
    DỮ LIỆU LUẬT (TUYỆT ĐỐI TUÂN THỦ):
    {knowledge}
    
    YÊU CẦU TRẢ LỜI: 
    1. Trả lời chính xác, ngắn gọn dựa trên dữ liệu trên.
    2. Trích dẫn điều luật/tên văn bản cụ thể.
    3. Giọng văn trang trọng, lịch sự, đúng tác phong công an nhân dân.
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *Đang tra cứu văn bản...*")
        
        reply = ask_gemini(final_prompt)
        
        if reply:
            # Thêm câu hỏi thăm vào cuối
            full_reply = reply + "\n\n---\n*Bạn cần hỏi gì thêm không?*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            message_placeholder.error("⚠️ Hệ thống đang bận. Vui lòng thử lại sau 30 giây.")

# Nút xóa lịch sử thủ công (Nếu muốn xóa ngay mà không cần tắt tab)
if st.sidebar.button("🧹 Xóa cuộc trò chuyện"):
    st.session_state.messages = []
    st.rerun()
