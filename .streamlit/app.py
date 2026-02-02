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

# --- DANH SÁCH MODEL DỰ PHÒNG (QUAN TRỌNG) ---
# Hệ thống sẽ thử lần lượt các model này
MODEL_LIST = [
    "gemini-2.0-flash-lite-preview-09-2025", # Ưu tiên 1: Bản Lite mới nhất (Thường free)
    "gemini-2.0-flash-lite",                  # Ưu tiên 2: Bản Lite thường
    "gemini-pro-latest",                      # Ưu tiên 3: Bản Pro ổn định
    "gemini-2.0-flash-exp",                   # Ưu tiên 4: Bản thử nghiệm
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
                continue # Bỏ qua file lỗi
                
        return full_text, file_list
    except Exception as e:
        return None, str(e)

# --- HÀM GỌI AI THÔNG MINH (TỰ ĐỔI MODEL) ---
def ask_gemini(prompt):
    last_error = ""
    # Vòng lặp thử từng model trong danh sách
    for model_name in MODEL_LIST:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, model_name # Trả về câu trả lời + tên model đã dùng
        except Exception as e:
            last_error = str(e)
            time.sleep(1) # Nghỉ 1 giây rồi thử cái tiếp theo
            continue
    
    # Nếu thử hết mà vẫn lỗi
    return None, last_error

# --- GIAO DIỆN CHÍNH ---
st.markdown("<h1 style='text-align: center; color: #CE1126;'>🔥 TRỢ LÝ PCCC (AI)</h1>", unsafe_allow_html=True)

with st.spinner('Đang kết nối Google Drive...'):
    knowledge, list_files = load_drive_data()

if list_files is None:
    st.error(f"Lỗi kết nối Drive: {knowledge}")
    st.stop()

with st.expander(f"📚 Đã nạp {len(list_files)} văn bản (Drive)"):
    for f in list_files: st.write(f"📄 {f}")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Chào Đại úy! Xin mời nhập câu hỏi."}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    final_prompt = f"""
    Bạn là Đại úy Phạm Tùng, Chuyên gia PCCC.
    DỮ LIỆU TỪ DRIVE:
    {knowledge}
    
    YÊU CẦU: 
    1. Trả lời dựa trên dữ liệu trên. 
    2. Trích dẫn nguồn file cụ thể.
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Typing...")
        
        # Gọi hàm thông minh
        reply, used_model = ask_gemini(final_prompt)
        
        if reply:
            # Thành công
            full_reply = reply + f"\n\n*(Trả lời bởi model: `{used_model}`)*"
            message_placeholder.markdown(full_reply)
            st.session_state.messages.append({"role": "assistant", "content": full_reply})
        else:
            # Thất bại toàn tập
            error_msg = f"⚠️ HỆ THỐNG QUÁ TẢI (Lỗi 429). Vui lòng đợi 1 phút rồi thử lại.\nChi tiết: {used_model}" # used_model lúc này chứa lỗi
            message_placeholder.error(error_msg)
