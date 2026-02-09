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

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC & CNCH", page_icon="🛡️", layout="wide")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1rem; color: white; text-align: center; border-radius: 0 0 10px 10px; margin-top: -50px;}</style>""", unsafe_allow_html=True)

# --- KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys.split(",") if k.strip()]
    FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("Lỗi cấu hình Secrets"); st.stop()

def get_random_key(): return random.choice(API_KEYS)

@st.cache_resource
def get_model_name():
    # Ưu tiên Flash (Token lớn)
    return "gemini-1.5-flash"

ACTIVE_MODEL = get_model_name()

# --- ĐỌC DỮ LIỆU ---
@st.cache_resource(ttl=3600)
def load_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        files = service.files().list(q=f"'{FOLDER_ID}' in parents and trashed=false", pageSize=50, fields="files(id, name)").execute().get('files', [])
        
        groups = {"phap_luat": "", "xu_phat": "", "quy_chuan": "", "chua_chay": "", "khac": ""}
        debug_list = []

        for file in files:
            try:
                content = ""
                # Chỉ đọc file < 5MB để tránh quá tải
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False; 
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                elif file['name'].endswith(".pdf"): # PDF thường nặng, chỉ lấy 50 trang đầu
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages[:50] if p.extract_text()])

                if content:
                    text = f"\n=== {file['name']} ===\n{content}\n"
                    name = file['name'].lower()
                    
                    if any(x in name for x in ["phat", "106", "189", "vi pham"]): groups["xu_phat"] += text
                    elif any(x in name for x in ["luat", "nghi dinh", "thong tu", "136", "50", "105"]): groups["phap_luat"] += text
                    elif any(x in name for x in ["quy chuan", "tieu chuan", "06", "qc10"]): groups["quy_chuan"] += text
                    elif any(x in name for x in ["chua chay", "cnch", "phuong an"]): groups["chua_chay"] += text
                    else: groups["khac"] += text
                    
                    debug_list.append(file['name'])
            except: continue
        return groups, debug_list
    except: return None, []

# --- CHỌN DỮ LIỆU (TIẾT KIỆM) ---
def get_context(prompt, groups):
    p = prompt.lower()
    
    # 1. NẾU CHÀO HỎI -> KHÔNG GỬI GÌ CẢ (Để tiết kiệm)
    if any(x in p for x in ["chào", "hello", "hi ", "xin chào", "là ai"]):
        return "", "Xã giao"

    # 2. Logic chọn lọc
    content = ""
    source = []
    
    if any(x in p for x in ["phạt", "tiền", "lỗi"]): 
        content += groups["xu_phat"] + groups["phap_luat"]
        source.append("Xử phạt")
    
    elif any(x in p for x in ["mét", "cao", "rộng", "bậc", "thang", "cửa", "lối", "khoảng cách"]):
        content += groups["quy_chuan"]
        source.append("Kỹ thuật")
        
    elif any(x in p for x in ["hồ sơ", "thủ tục", "nghiệm thu", "thẩm duyệt"]):
        content += groups["phap_luat"]
        source.append("Thủ tục")
        
    elif any(x in p for x in ["chữa cháy", "xe", "bơm"]):
        content += groups["chua_chay"]
        source.append("Chữa cháy")

    # 3. FALLBACK: Nếu không khớp từ khóa nào -> Chỉ gửi Pháp luật (Bỏ Quy chuẩn vì quá nặng)
    if not content:
        content = groups["phap_luat"]
        source = ["Cơ bản (Luật)"]
        
    return content, "+".join(source)

# --- GỌI AI ---
def ask_ai(prompt):
    # Thử đổi key liên tục nếu lỗi
    for _ in range(3):
        try:
            genai.configure(api_key=get_random_key())
            model = genai.GenerativeModel(ACTIVE_MODEL)
            return model.generate_content(prompt).text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower(): time.sleep(1); continue
            return f"Lỗi: {str(e)}"
    return "⚠️ Hệ thống đang bận. Vui lòng thử lại sau 10s."

# --- UI ---
st.markdown('<div class="header-banner"><h3>TRỢ LÝ AI PCCC</h3></div>', unsafe_allow_html=True)
with st.spinner("Đang khởi động..."):
    groups, file_list = load_data()

if not groups: st.error("Lỗi Drive"); st.stop()

if "msgs" not in st.session_state: st.session_state.msgs = []
for m in st.session_state.msgs: st.chat_message(m["role"]).write(m["content"])

if q := st.chat_input("Hỏi gì đó..."):
    st.session_state.msgs.append({"role": "user", "content": q})
    st.chat_message("user").write(q)
    
    ctx, src = get_context(q, groups)
    
    # Nếu là xã giao thì prompt ngắn
    if src == "Xã giao":
        final_prompt = f"Bạn là Trợ lý PCCC. Người dùng hỏi: {q}. Hãy trả lời thân thiện ngắn gọn."
    else:
        final_prompt = f"Vai trò: Chuyên gia PCCC.\nDữ liệu:\n{ctx}\n\nCâu hỏi: {q}\nTrả lời dựa trên dữ liệu:"

    with st.chat_message("assistant"):
        if src != "Xã giao": st.caption(f"Đang tra cứu: {src}")
        ans = ask_ai(final_prompt)
        st.write(ans)
        st.session_state.msgs.append({"role": "assistant", "content": ans})
