import streamlit as st
import requests  # Dùng cái này thay cho google.generativeai để không bị lỗi
import json
import time
import random
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(
    page_title="Hệ thống Trợ lý ảo PCCC & CNCH (Pro)",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #b92b27 0%, #1565C0 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI KEY & DRIVE ---
try:
    if "GEMINI_API_KEYS" in st.secrets:
        keys_string = st.secrets["GEMINI_API_KEYS"]
    else:
        keys_string = st.secrets["GEMINI_API_KEY"]
        
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình Secrets: {str(e)}")
    st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. HÀM GỌI AI TRỰC TIẾP (KHÔNG DÙNG THƯ VIỆN ĐỂ TRÁNH LỖI) ---
def call_gemini_direct(prompt, system_instruction=""):
    api_key = get_random_key()
    # Ưu tiên Flash 2.5 (Mới nhất) -> Flash 2.0 -> Flash 1.5
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    last_error = ""
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
        }
        
        if system_instruction:
             payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        try:
            # Timeout 45s cho câu trả lời dài
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                result = response.json()
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    return "⚠️ Lỗi: AI trả về nội dung rỗng."
            elif response.status_code == 404:
                continue # Thử model tiếp theo
            elif response.status_code == 429:
                time.sleep(2); continue # Quá tải thì thử lại
            else:
                last_error = f"Lỗi Google ({response.status_code}): {response.text}"
                continue
                
        except Exception as e:
            last_error = str(e)
            continue
            
    return f"⚠️ Hệ thống đang bận. Vui lòng thử lại sau. (Lỗi: {last_error})"

# --- 4. ĐỌC DỮ LIỆU DRIVE (SMART CACHING) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_and_process_drive_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"phap_luat": [], "xu_phat": [], "ky_thuat": [], "chua_chay": [], "khac": []}
        total_files = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages[:20] if p.extract_text()])
                
                if content:
                    doc_item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    # Phân loại
                    if any(x in fname for x in ["144", "xu phat", "vi pham"]): data_store["xu_phat"].append(doc_item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn"]): data_store["ky_thuat"].append(doc_item)
                    elif any(x in fname for x in ["chua chay", "cnch"]): data_store["chua_chay"].append(doc_item)
                    elif any(x in fname for x in ["luat", "nghi dinh", "ho so"]): data_store["phap_luat"].append(doc_item)
                    else: data_store["phap_luat"].append(doc_item) # Mặc định cho vào luật
                    total_files += 1
            except: continue
        return data_store, total_files
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🔥</div>
    <p style="font-size: 24px; font-weight: 900; margin: 0;">TRỢ LÝ AI PCCC & CNCH</p>
    <p style="font-size: 14px; opacity: 0.9;">PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động hệ thống siêu tốc...'):
    data_store, file_count = load_and_process_drive_data()

if not data_store: st.error("❌ Lỗi kết nối Drive."); st.stop()

with st.expander(f"✅ TRẠNG THÁI: {file_count} TÀI LIỆU | SẴN SÀNG"):
    st.write("Hệ thống đã nạp xong dữ liệu pháp luật và kỹ thuật.")

# --- CHAT ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # 1. Chọn dữ liệu (Smart Context)
    p = prompt.lower()
    ctx = ""
    src_list = []
    
    if not any(x in p for x in ["chào", "hello", "hi ", "là ai"]):
        if any(x in p for x in ["phạt", "tiền", "lỗi"]): 
            ctx += "\n".join(data_store["xu_phat"] + data_store["phap_luat"]); src_list.append("Xử phạt")
        elif any(x in p for x in ["mét", "cao", "rộng", "bậc", "thang"]):
            ctx += "\n".join(data_store["ky_thuat"]); src_list.append("Kỹ thuật")
        elif any(x in p for x in ["hồ sơ", "thủ tục"]):
            ctx += "\n".join(data_store["phap_luat"]); src_list.append("Thủ tục")
        elif any(x in p for x in ["chữa cháy", "xe"]):
            ctx += "\n".join(data_store["chua_chay"]); src_list.append("Chữa cháy")
        
        if not ctx: # Fallback
             ctx = "\n".join(data_store["phap_luat"])
             src_list = ["Pháp luật chung"]

    src_label = "+".join(src_list) if src_list else "Giao tiếp"
    
    # 2. Tạo Prompt
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Trợ lý nghiệp vụ PCCC & CNCH.
    DỮ LIỆU THAM KHẢO:
    {ctx}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU:
    1. Trả lời chính xác, trích dẫn Điều/Khoản/Văn bản pháp luật.
    2. Nếu là Xử phạt: Nêu mức tiền phạt cụ thể.
    3. Nếu là Kỹ thuật: Nêu thông số kỹ thuật.
    4. Văn phong: Chuyên nghiệp, ngắn gọn.
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu ({src_label})...*")
        
        reply = call_gemini_direct(final_prompt, "Bạn là chuyên gia PCCC.")
        
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
