import streamlit as st
import google.generativeai as genai
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
st.set_page_config(page_title="PCCC PC07 (Model Selector)", page_icon="🎛️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1.5rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;}
    .stChatInput {border-radius: 20px;}
    .router-box {background-color: #e3f2fd; padding: 10px; border-radius: 5px; border-left: 5px solid #2196f3; margin-bottom: 10px; font-size: 0.9em;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI API (CÓ NHẬP TAY) ---
API_KEYS_LIST = []
if "GEMINI_API_KEYS" in st.secrets: 
    keys_string = st.secrets["GEMINI_API_KEYS"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
elif "GEMINI_API_KEY" in st.secrets:
    API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]

if not API_KEYS_LIST:
    with st.sidebar:
        st.warning("⚠️ Chưa có API Key trong Secrets.")
        manual_key = st.text_input("Nhập API Key:", type="password")
        if manual_key: API_KEYS_LIST = [manual_key]

if not API_KEYS_LIST: st.error("❌ Vui lòng nhập API Key để bắt đầu."); st.stop()

DRIVE_FOLDER_ID = ""; GCP_JSON = {}
try:
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: pass

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO THAM MƯU (ROUTER - LUÔN DÙNG FLASH CHO NHANH) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: PHÂN TÍCH CÂU HỎI để chọn tài liệu CHÍNH XÁC NHẤT.

1. GIỎ PHÁP LÝ & QUẢN LÝ:
   - Tài liệu: [Luật PCCC], [Nghị định 105], [Thông tư 36].
   - Dấu hiệu: Trách nhiệm, hồ sơ, thẩm duyệt, nghiệm thu.
   - QUY TẮC: Hỏi "Trách nhiệm" hoặc "Hồ sơ" -> BẮT BUỘC CHỌN CẢ 3.

2. GIỎ XỬ PHẠT:
   - Tài liệu: [Nghị định 106], [Nghị định 189].
   - QUY TẮC:
     + Hỏi tiền/lỗi -> CHỌN [NĐ 106].
     + Hỏi quyền/ai ký -> CHỌN [NĐ 106] + [NĐ 189].

3. GIỎ LỰC LƯỢNG: [Thông tư 37], [Thông tư 48].

4. GIỎ HUY ĐỘNG: [Công văn huy động].

5. GIỎ KỸ THUẬT: [QCVN 10], [QCVN 06].
   - QUY TẮC: Hỏi trang bị/lắp đặt -> BẮT BUỘC CHỌN [QCVN 10].

OUTPUT: Chỉ trả về danh sách tên file, ngăn cách bằng dấu phẩy.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    try:
        api_key = get_random_key()
        genai.configure(api_key=api_key)
        # Router luôn dùng 1.5 Flash cho nhẹ
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except: return ""

# --- 4. BỘ NÃO CHUYÊN GIA (EXPERT - MODEL DO NGƯỜI DÙNG CHỌN) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🚫 NGUYÊN TẮC CỐT TỬ (GROUNDING):
1. TUYỆT ĐỐI KHÔNG SÁNG TẠO: Chỉ trả lời dựa trên tài liệu được cung cấp.
2. TRÍCH DẪN CHÍNH XÁC: Phải ghi rõ nguồn (Điểm, Khoản, Điều, Văn bản).

⚡ QUY TRÌNH NGHIỆP VỤ (FULL):
1. Dịch lỗi dân gian sang luật.
2. Hỏi Trách nhiệm/Hồ sơ: Tổng hợp Luật -> NĐ 105 -> TT 36.
3. Hỏi Phạt: Tra tiền (NĐ 106) -> Tra quyền (NĐ 189, nếu có) -> Kết luận.
4. Hỏi Quản lý: Quy tắc 70% -> Phụ lục NĐ 105.
5. Hỏi Kỹ thuật: Tra Bảng QCVN 10 -> Liệt kê hệ thống.
"""

def call_gemini_expert(prompt, context, selected_model_name):
    # Dùng đúng Model mà Đại úy đã chọn ở Sidebar
    
    if not context: 
        full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: 
        full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU ĐƯỢC CHỌN LỌC ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"

    try:
        api_key = get_random_key()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(selected_model_name)
        
        # Timeout an toàn
        response = model.generate_content(full_prompt, request_options={'timeout': 100})
        return response.text
    except Exception as e:
        return f"⚠️ Lỗi kết nối với Model **{selected_model_name}**: {str(e)}. Đại úy hãy thử chọn Model khác ở menu bên trái."

# --- 5. NẠP DỮ LIỆU ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_database_final():
    if not GCP_JSON or not DRIVE_FOLDER_ID: return {}, ["⚠️ Chưa cấu hình Drive"]
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        db = {} 
        logs = []
        processed = set()
        
        keywords = ["189", "106", "105", "36", "37", "48", "luat", "huy dong", "qcvn", "10:2025", "06", "10"]
        files = []
        for k in keywords:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and name contains '{k}'", fields="files(id, name)").execute().get('files', []))
            except: pass
        try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name)").execute().get('files', []))
        except: pass

        for f in files:
            if f['id'] in processed: continue
            processed.add(f['id'])
            if "144" in f['name'] and "106" not in f['name']: continue

            try:
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, service.files().get_media(fileId=f['id']))
                done = False
                while not done: _, done = downloader.next_chunk()
                fh.seek(0)
                
                text = ""
                if f['name'].endswith(".docx"):
                    doc = Document(fh)
                    text = "\n".join([p.text for p in doc.paragraphs])
                    for t in doc.tables:
                        for r in t.rows: text += " | ".join([c.text.strip() for c in r.cells]) + "\n"
                elif f['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                
                if text:
                    db[f['name']] = text
                    logs.append(f"✅ {f['name']}")
            except: continue
        return db, logs
    except Exception as e: return None, [str(e)]

# --- 6. GIAO DIỆN ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC (TÙY CHỌN MODEL)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động hệ thống...'):
    database, logs = load_database_final()

if not database: st.error(f"❌ Lỗi dữ liệu: {logs[0]}"); st.stop()

# --- SIDEBAR: CẤU HÌNH & CHỌN MODEL ---
with st.sidebar:
    st.header("⚙️ CẤU HÌNH AI")
    
    # 🌟 MENU CHỌN MODEL Ở ĐÂY 🌟
    selected_model = st.selectbox(
        "Chọn Model xử lý:",
        (
            "gemini-2.0-flash",       # Ưu tiên 1: Mới nhất, Nhanh
            "gemini-1.5-pro",         # Ưu tiên 2: Thông minh nhất
            "gemini-1.5-flash",       # Ưu tiên 3: Ổn định nhất
            "gemini-1.5-flash-8b"     # Ưu tiên 4: Siêu tốc
        ),
        index=0 # Mặc định chọn 2.0
    )
    
    st.info(f"Đang dùng: **{selected_model}**")
    
    st.divider()
    st.header("KHO DỮ LIỆU")
    with st.expander("Chi tiết file"):
        for l in logs: st.text(l)

# Chat
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    with st.chat_message("assistant", avatar="🚒"):
        router_box = st.empty()
        
        # BƯỚC 1: ROUTER
        router_box.markdown("🧠 *Đang phân tích...*")
        all_files = list(database.keys())
        selected_files_str = smart_router(prompt, all_files)
        
        # BƯỚC 2: TRÍCH XUẤT
        relevant_context = ""
        used_files = []
        if selected_files_str:
            for fname in all_files:
                if fname in selected_files_str:
                    relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
                    used_files.append(fname)
        
        # BACKUP LOGIC
        if not relevant_context:
            for fname, content in database.items():
                if "189" in fname and ("ai" in prompt or "thẩm quyền" in prompt or "ký" in prompt): relevant_context += content; used_files.append(fname)
                if "106" in fname and ("phạt" in prompt or "lỗi" in prompt): relevant_context += content; used_files.append(fname)
                if ("trách nhiệm" in prompt or "hồ sơ" in prompt) and any(x in fname for x in ["luat", "105", "36"]): relevant_context += content; used_files.append(fname)
                if ("10" in fname or "qc" in fname) and ("trang bị" in prompt or "lắp" in prompt): relevant_context += content; used_files.append(fname)

        if used_files:
            st.markdown(f'<div class="router-box">📚 <b>AI Tham mưu đã chọn:</b><br>{", ".join(used_files)}</div>', unsafe_allow_html=True)
            router_box.empty()
        else: router_box.empty()
            
        # BƯỚC 3: TRẢ LỜI (DÙNG MODEL ĐƯỢC CHỌN)
        response = call_gemini_expert(prompt, relevant_context, selected_model)
        
        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
