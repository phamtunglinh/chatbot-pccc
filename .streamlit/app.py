import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io
import json

# --- CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Hệ thống PCCC (Drive)", page_icon="🚒", layout="wide")

# --- KẾT NỐI BẢO MẬT ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình Secrets: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- HÀM ĐỌC GOOGLE DRIVE ---
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
            fid = file['id']
            if "google-apps" in file['mimeType']: continue 
            
            request = service.files().get_media(fileId=fid)
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
                
        return full_text, file_list
    except Exception as e:
        return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("<h1 style='text-align: center; color: #CE1126;'>🔥 TRỢ LÝ PCCC (DATA DRIVE)</h1>", unsafe_allow_html=True)

with st.spinner('Đang kết nối Google Drive...'):
    knowledge, list_files = load_drive_data()

if list_files is None:
    st.error(f"Lỗi kết nối Drive: {knowledge}")
    st.stop()

with st.expander(f"📚 Đã nạp thành công {len(list_files)} văn bản từ Drive"):
    for f in list_files: st.write(f"📄 {f}")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Chào Đại úy! Hệ thống đã sẵn sàng."}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi tra cứu..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    final_prompt = f"""
    Bạn là Chuyên gia PCCC.
    DỮ LIỆU TỪ DRIVE:
    {knowledge}
    
    YÊU CẦU: Trả lời câu hỏi dựa trên dữ liệu trên. Trích dẫn nguồn.
    CÂU HỎI: {prompt}
    """
    
    try:
        # THAY ĐỔI QUAN TRỌNG: Dùng tên model mới nhất "gemini-1.5-flash-latest"
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(final_prompt)
        reply = response.text
    except Exception as e:
        # Nếu vẫn lỗi thì thử model cũ hơn "gemini-pro" cho chắc ăn
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(final_prompt)
            reply = response.text
        except Exception as e2:
             reply = f"⚠️ LỖI KẾT NỐI AI: {str(e)}"

    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.chat_message("assistant").write(reply)
