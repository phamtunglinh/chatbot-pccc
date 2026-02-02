import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io
import json

# --- CẤU HÌNH ---
st.set_page_config(page_title="PCCC Tra cứu (Drive)", page_icon="🚒", layout="wide")

# --- KẾT NỐI BẢO MẬT ---
try:
    # Lấy thông tin từ Secrets
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    # Chuyển chuỗi JSON thành Dictionary
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except:
    st.error("⚠️ Chưa cấu hình Secrets (API Key, Drive ID, GCP JSON)!")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- HÀM 1: KẾT NỐI DRIVE & TẢI FILE ---
@st.cache_resource(ttl=3600) # Lưu bộ nhớ đệm 1 tiếng để đỡ tốn quota
def load_data_from_drive():
    try:
        # Xác thực với Google Drive
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        
        # Lấy danh sách file trong thư mục
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        all_text = ""
        file_names = []
        
        # Tải từng file về bộ nhớ (RAM)
        for file in files:
            file_id = file['id']
            file_name = file['name']
            mime_type = file['mimeType']
            
            # Chỉ xử lý file Docx và PDF
            if 'google-apps' in mime_type: continue # Bỏ qua file Google Doc online
            
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            fh.seek(0) # Đưa con trỏ về đầu file
            
            # Đọc nội dung
            content = ""
            if file_name.endswith(".docx"):
                doc = Document(fh)
                for para in doc.paragraphs: content += para.text + "\n"
            elif file_name.endswith(".pdf"):
                reader = PdfReader(fh)
                for page in reader.pages: content += page.extract_text() + "\n"
            
            if content:
                all_text += f"\n--- NGUỒN: {file_name} ---\n{content}\n"
                file_names.append(file_name)
                
        return all_text, file_names
    except Exception as e:
        return None, str(e)

# --- GIAO DIỆN ---
st.markdown("<h1 style='text-align: center; color: #CE1126;'>🚒 TRA CỨU PCCC (DATA DRIVE)</h1>", unsafe_allow_html=True)

# Load dữ liệu (Tự động chạy ngầm)
with st.spinner('Đang đồng bộ dữ liệu từ Google Drive...'):
    knowledge_base, file_list = load_data_from_drive()

if file_list is None:
    st.error(f"Lỗi kết nối Drive: {knowledge_base}") # knowledge_base lúc này chứa thông báo lỗi
    st.stop()

# Hiển thị trạng thái dữ liệu (Ẩn trong Expander cho gọn)
with st.expander(f"📚 Dữ liệu đang online: {len(file_list)} văn bản"):
    for f in file_list: st.write(f"- {f}")

# Chatbot
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Chào Đại úy! Tôi đã học xong các văn bản trên Drive. Xin mời hỏi."}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Prompt
    final_prompt = f"""
    Bạn là Trợ lý PCCC.
    DỮ LIỆU TỪ GOOGLE DRIVE CỦA ADMIN:
    {knowledge_base}
    
    YÊU CẦU: Trả lời dựa trên dữ liệu trên. Trích dẫn nguồn file cụ thể.
    CÂU HỎI: {prompt}
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(final_prompt)
        bot_reply = response.text
    except Exception as e:
        bot_reply = "Lỗi kết nối AI."

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    st.chat_message("assistant").write(bot_reply)
