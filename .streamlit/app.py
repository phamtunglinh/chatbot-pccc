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
st.set_page_config(page_title="PCCC PC07 (Smart Router 2.5)", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1.5rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;}
    .stChatInput {border-radius: 20px;}
    .router-box {background-color: #e3f2fd; padding: 10px; border-radius: 5px; border-left: 5px solid #2196f3; margin-bottom: 10px; font-size: 0.9em;}
    .success-box {background-color: #e8f5e9; padding: 5px; border-radius: 5px; font-size: 0.8em; color: #2e7d32; margin-top: 5px;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI API (ĐA KEY - QUAY VÒNG) ---
API_KEYS_LIST = []
if "GEMINI_API_KEYS" in st.secrets: 
    keys_string = st.secrets["GEMINI_API_KEYS"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
elif "GEMINI_API_KEY" in st.secrets:
    API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]

if not API_KEYS_LIST:
    with st.sidebar:
        st.warning("⚠️ Chưa có API Key.")
        manual_key = st.text_input("Nhập API Key (phân cách dấu phẩy):", type="password")
        if manual_key: 
            API_KEYS_LIST = [k.strip() for k in manual_key.split(",") if k.strip()]

if not API_KEYS_LIST: st.error("❌ Vui lòng nhập API Key."); st.stop()

# --- 3. CẤU HÌNH DRIVE ---
DRIVE_FOLDER_ID = ""; GCP_JSON = {}
try:
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: pass

# --- 4. BỘ NÃO THAM MƯU (ROUTER - CÓ QUY TẮC LOẠI TRỪ) ---
# Đây là phần sửa quan trọng nhất để AI không chọn thừa tài liệu
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: Chọn tài liệu "TỐI GIẢN NHƯNG ĐỦ DÙNG".

QUY TẮC 1 (QUAN TRỌNG NHẤT): HỎI VỀ XỬ PHẠT (Lỗi, Phạt tiền, Xử lý vi phạm, Không có...)
- BẮT BUỘC CHỌN: [Nghị định 106] (để tra tiền) VÀ [Nghị định 189] (để tra thẩm quyền).
- CẤM CHỌN: Luật PCCC, Nghị định 105, Thông tư 36. (Vì các văn bản này chỉ quy định cách làm, không quy định mức tiền phạt -> Đưa vào sẽ gây nhiễu).

QUY TẮC 2: HỎI VỀ THỦ TỤC/HỒ SƠ (Trách nhiệm, Thẩm duyệt, Nghiệm thu, Hồ sơ quản lý gồm gì)
- Chỉ khi câu hỏi KHÔNG nhắc đến "Lỗi" hay "Phạt".
- HÀNH ĐỘNG: Chọn [Luật PCCC], [Nghị định 105], [Thông tư 36].

QUY TẮC 3: HỎI VỀ KỸ THUẬT (Trang bị, Lắp đặt, Hệ thống, Khoảng cách)
- BẮT BUỘC CHỌN: [QCVN 10], [QCVN 06].

QUY TẮC 4: HỎI VỀ LỰC LƯỢNG: [Thông tư 37], [Thông tư 48].

OUTPUT: Chỉ trả về danh sách tên file có trong kho, ngăn cách bằng dấu phẩy.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE HIỆN CÓ: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    
    # Router dùng 1 key ngẫu nhiên và model nhẹ (1.5 Flash) để phản hồi nhanh
    try:
        api_key = random.choice(API_KEYS_LIST)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except: return ""

# --- 5. BỘ NÃO CHUYÊN GIA (EXPERT - MODEL 2.5/2.0 FLASH) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🚫 NGUYÊN TẮC CỐT TỬ (GROUNDING):
1. KHÔNG SÁNG TẠO: Chỉ trả lời dựa trên tài liệu được cung cấp.
2. TRÍCH DẪN: Ghi rõ Điểm, Khoản, Điều, Văn bản.

⚡ QUY TRÌNH XỬ LÝ:

1. NẾU HỎI VỀ XỬ PHẠT (NĐ 106 + 189):
   - Bước A: Tra cứu NĐ 106 để tìm hành vi -> Xác định mức phạt tiền (Cá nhân/Tổ chức).
   - Bước B: Tra cứu NĐ 189 để xem thẩm quyền phạt tối đa của từng chức danh (Xã, Huyện, Phòng, Giám đốc).
   - Bước C: So sánh và Kết luận -> Ai là người thấp nhất có quyền ký quyết định phạt?

2. NẾU HỎI VỀ QUẢN LÝ (NĐ 105):
   - Kiểm tra số liệu (Diện tích, khối tích) -> Áp dụng quy tắc 70% công năng -> Đối chiếu Phụ lục I, II -> Kết luận ai quản lý.

3. NẾU HỎI VỀ KỸ THUẬT (QCVN 10):
   - Tra Bảng quy định -> Liệt kê hệ thống bắt buộc.

4. NẾU HỎI VỀ HỒ SƠ/TRÁCH NHIỆM:
   - Tổng hợp từ Luật -> NĐ 105 -> TT 36.
"""

def call_gemini_expert_exhaustive(prompt, context):
    # DANH SÁCH MODEL MỤC TIÊU (Ưu tiên 2.5 Flash như yêu cầu)
    TARGET_MODELS = [
        "gemini-2.5-flash",       # Ưu tiên 1: Bản mới nhất (Nếu API hỗ trợ)
        "gemini-2.0-flash",       # Ưu tiên 2: Bản 2.0 chuẩn
        "gemini-2.0-flash-exp",   # Ưu tiên 3: Bản thử nghiệm
        "gemini-1.5-pro",         # Ưu tiên 4: Thông minh
        "gemini-1.5-flash"        # Ưu tiên 5: Chống cháy
    ]
    
    if not context: 
        full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: 
        full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"

    last_error = ""
    status_placeholder = st.empty()
    
    # VÒNG LẶP KÉP: DUYỆT TỪNG MODEL -> DUYỆT TỪNG KEY
    # Chiến thuật: Thử Model xịn nhất với tất cả Key. Nếu không được mới hạ cấp Model.
    for model_name in TARGET_MODELS:
        for index, key in enumerate(API_KEYS_LIST):
            try:
                # status_placeholder.text(f"🔄 Đang thử {model_name} (Key {index + 1})...")
                
                genai.configure(api_key=key)
                model = genai.GenerativeModel(model_name)
                
                # Timeout 60s
                response = model.generate_content(full_prompt, request_options={'timeout': 60})
                
                status_placeholder.empty()
                return response.text, model_name, index + 1
                
            except Exception as e:
                last_error = str(e)
                continue # Thử key tiếp theo
    
    status_placeholder.empty()
    return f"⚠️ Hệ thống quá tải (Đã thử hết Key & Model). Lỗi cuối: {last_error}", "None", 0

# --- 6. NẠP DỮ LIỆU ---
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

# --- 7. GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC (GEMINI 2.5 FLASH)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động...'):
    database, logs = load_database_final()

if not database: st.error(f"❌ Lỗi dữ liệu: {logs[0]}"); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ CẤU HÌNH")
    st.success(f"🔑 Đã nạp: **{len(API_KEYS_LIST)} API Key**")
    st.info("💡 Hệ thống ưu tiên Model **2.5 Flash**.")
    
    st.divider()
    st.header("KHO DỮ LIỆU")
    with st.expander("Chi tiết file"):
        for l in logs: st.text(l)

# Chat
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): 
        st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    with st.chat_message("assistant", avatar="🚒"):
        router_box = st.empty()
        
        # BƯỚC 1: ROUTER
        router_box.markdown("🧠 *Đang phân tích...*")
        all_files = list(database.keys())
        selected_files_str = smart_router(prompt, all_files)
        
        # BƯỚC 2: TRÍCH XUẤT (CÓ KIỂM SOÁT)
        relevant_context = ""
        used_files = []
        if selected_files_str:
            for fname in all_files:
                if fname in selected_files_str:
                    relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
                    used_files.append(fname)
        
        # BACKUP LOGIC (NẾU ROUTER THẤT BẠI HOẶC TRẢ VỀ RỖNG)
        if not relevant_context:
            for fname, content in database.items():
                is_penalty_q = ("phạt" in prompt or "lỗi" in prompt or "xử lý" in prompt)
                
                # Logic Xử phạt: Chỉ lấy 106, 189
                if is_penalty_q and any(x in fname for x in ["106", "189"]):
                     relevant_context += content; used_files.append(fname)
                
                # Logic Kỹ thuật
                elif ("10" in fname or "qc" in fname) and ("trang bị" in prompt or "lắp" in prompt): 
                    relevant_context += content; used_files.append(fname)
                
                # Logic Pháp lý (Chỉ lấy khi KHÔNG hỏi phạt)
                elif not is_penalty_q and any(x in fname for x in ["luat", "105", "36"]):
                    relevant_context += content; used_files.append(fname)

        if used_files:
            st.markdown(f'<div class="router-box">📚 <b>AI Tham mưu đã chọn:</b><br>{", ".join(used_files)}</div>', unsafe_allow_html=True)
            router_box.empty()
        else: router_box.empty()
            
        # BƯỚC 3: TRẢ LỜI
        response_text, used_model, used_key_idx = call_gemini_expert_exhaustive(prompt, relevant_context)
        
        st.markdown(response_text)
        
        if used_model != "None":
            st.markdown(f"""
            <div class="success-box">
            ✅ Kết nối thành công!<br>
            - Model: <b>{used_model}</b><br>
            - API Key: <b>Số {used_key_idx}</b>
            </div>
            """, unsafe_allow_html=True)
        
        st.session_state.messages.append({"role": "assistant", "content": response_text})
