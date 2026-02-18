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

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(
    page_title="TRỢ LÝ PCCC CHUYÊN DỤNG",
    page_icon="🛡️",
    layout="centered", 
    initial_sidebar_state="collapsed", 
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Hệ thống hỗ trợ nghiệp vụ PCCC PC07 - Phát triển bởi Đại úy Phạm Tùng Linh"
    }
)

# --- 2. CSS "CLEAN & BEAUTIFUL" ---
st.markdown("""
<style>
    /* Ẩn hoàn toàn Sidebar và Menu mặc định */
    [data-testid="stSidebar"] {display: none;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}

    /* Nền tổng thể sạch sẽ */
    .stApp {
        background-color: #ffffff;
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    }

    /* Header Banner Chuyên nghiệp */
    .main-header {
        background: linear-gradient(90deg, #ce181e 0%, #003b8e 100%); /* Đỏ PCCC sang Xanh CA */
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    .main-header h1 {
        font-size: 1.4rem; /* Giảm size chút để vừa tên đơn vị dài */
        font-weight: 700;
        margin: 0;
        letter-spacing: 1px;
        text-transform: uppercase;
        line-height: 1.4;
    }
    .main-header p {
        font-size: 0.95rem;
        opacity: 0.95;
        margin-top: 8px;
        font-weight: 400;
        border-top: 1px solid rgba(255,255,255,0.3);
        padding-top: 8px;
        display: inline-block;
    }

    /* Footer Bản Quyền */
    .custom-footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #f8f9fa;
        color: #555;
        text-align: center;
        padding: 10px;
        font-size: 0.8rem;
        border-top: 1px solid #e0e0e0;
        z-index: 999;
    }
    
    /* Đẩy nội dung lên để không bị footer che */
    .block-container {
        padding-bottom: 60px;
    }

    /* Tinh chỉnh Chat Input */
    .stChatInput textarea {
        border-radius: 30px !important;
        padding: 12px 20px !important;
        border: 1px solid #dfe1e5 !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .stChatInput textarea:focus {
        border-color: #ce181e !important;
        box-shadow: 0 2px 8px rgba(206, 24, 30, 0.2);
    }

    /* Chat Message Styling */
    [data-testid="stChatMessage"] {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 10px;
        background-color: transparent;
    }
    
    /* User Message Background */
    [data-testid="stChatMessage"][data-testid="user"] {
        background-color: #f1f3f4;
    }

    /* Content Typography */
    .response-content {
        line-height: 1.6;
        color: #1a1a1a;
        font-size: 1rem;
    }
    .response-content strong {
        color: #ce181e; 
    }
</style>
""", unsafe_allow_html=True)

# --- 3. HEADER GIAO DIỆN (ĐÃ CẬP NHẬT) ---
st.markdown("""
<div class="main-header">
    <h1>🛡️ PHÒNG CẢNH SÁT PCCC VÀ CNCH - CÔNG AN TỈNH PHÚ THỌ</h1>
    <p>TRỢ LÝ NGHIỆP VỤ PCCC & CNCH được phát triển bởi Đại úy Phạm Tùng Linh</p>
</div>
""", unsafe_allow_html=True)

# --- 4. FOOTER BẢN QUYỀN ---
st.markdown("""
<div class="custom-footer">
    © 2025 Bản quyền thuộc về Đại úy Phạm Tùng Linh - PC07 Công an tỉnh Phú Thọ
</div>
""", unsafe_allow_html=True)

# --- 5. KẾT NỐI API (FAILOVER) ---
API_KEYS_LIST = []
try:
    if "GEMINI_API_KEYS" in st.secrets: 
        keys_string = st.secrets["GEMINI_API_KEYS"]
        API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    elif "GEMINI_API_KEY" in st.secrets:
        API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]
    
    if not API_KEYS_LIST: st.error("❌ Lỗi: Thiếu API Key hệ thống."); st.stop()
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e: st.error(f"⚠️ Lỗi cấu hình: {str(e)}"); st.stop()

# --- 6. BỘ NÃO THAM MƯU (ROUTER) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: Chọn tài liệu chính xác.

1. GIỎ PHÂN CẤP QUẢN LÝ (AI QUẢN LÝ CƠ SỞ):
   - Dấu hiệu: "Cơ sở này do ai quản lý", "Thuộc danh mục nào", "Xã hay Công an quản lý", "Phụ lục mấy".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 136], [Nghị định 50].

2. GIỎ PHÁP LÝ (HỒ SƠ/THỦ TỤC):
   - Dấu hiệu: "Hồ sơ", "Thủ tục", "Điều kiện", "Kiểm tra", "Thẩm duyệt".
   - HÀNH ĐỘNG: Chọn [Luật PCCC], [Nghị định 105], [Thông tư 36], [Nghị định 136], [Nghị định 50].

3. GIỎ XỬ PHẠT:
   - Dấu hiệu: "Lỗi", "Phạt", "Xử lý vi phạm".
   - HÀNH ĐỘNG: [Nghị định 106], [Nghị định 189].

4. GIỎ KỸ THUẬT:
   - Dấu hiệu: "Trang bị", "Lắp đặt", "Hệ thống", "Khoảng cách".
   - HÀNH ĐỘNG: [QCVN 10], [QCVN 06].

5. GIỎ QUÂN ĐỘI:
   - Dấu hiệu: "Quân đội", "Chi viện".
   - HÀNH ĐỘNG: File chứa "CV HD", "QUÂN ĐỘI", "ĐỘI 3".

6. GIỎ CHỮA CHÁY: [Thông tư 37].

OUTPUT: Chỉ trả về danh sách tên file có trong kho.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    for key in API_KEYS_LIST:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text.strip()
        except: continue
    return ""

# --- 7. BỘ NÃO CHUYÊN GIA (EXPERT - STRICT CITATION) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: AI chuyên gia về PCCC và CNCH Công an tỉnh PC07 Phú Thọ.

🛑 NGUYÊN TẮC CỐT TỬ:
1. Trả lời ngắn gọn, đúng trọng tâm, văn phong hành chính chuyên nghiệp.
2. Tuyệt đối không sáng tạo ngoài văn bản.

🔴 RULE 1: XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (QUAN TRỌNG):
   - Khi trả lời câu hỏi "Cơ sở này do ai quản lý?", BẮT BUỘC tuân thủ:
   1. CĂN CỨ PHÁP LÝ DUY NHẤT: Nghị định 136/2020/NĐ-CP và Nghị định 50/2024/NĐ-CP (Sửa đổi NĐ 136).
   2. TUYỆT ĐỐI KHÔNG trích dẫn: Công văn, Hướng dẫn nội bộ, Quy tắc suy luận (Rule), hay "Dự thảo".
   3. QUY TRÌNH SUY LUẬN (Chạy ngầm trong não, không viết quy trình ra):
      - B1: Xác định công năng chính (Quy tắc 70%).
      - B2: Đối chiếu Phụ lục I (Diện quản lý), Phụ lục II (Nguy hiểm cháy nổ), Phụ lục III (Công an), Phụ lục IV (Xã) của NĐ 50/2024.
      - B3: Kết luận.
   4. MẪU TRẢ LỜI:
      "Căn cứ Phụ lục... ban hành kèm theo Nghị định số 50/2024/NĐ-CP:
       - Cơ sở [Tên cơ sở] có [Đặc điểm: Diện tích/Tầng/Khối tích] thuộc Mục..., Phụ lục...
       -> KẾT LUẬN: Cơ sở thuộc diện quản lý của [Cơ quan Công an / UBND cấp xã]."

🔴 RULE 2: XỬ PHẠT VI PHẠM (NĐ 106 + 189):
   - Áp dụng cơ chế "LỌC ẨN":
     + Chỉ hiển thị những chức danh có thẩm quyền phạt tiền >= Mức phạt cá nhân của hành vi.
     + Ẩn hoàn toàn các chức danh không đủ tiền.
   - Sau đó xét tiếp quyền phạt bổ sung/KPHQ.
   - Đề xuất người thấp nhất đủ quyền.

🟢 RULE 3: CÁC LĨNH VỰC KHÁC:
   - Kỹ thuật: Căn cứ QCVN 10, QCVN 06.
   - Chữa cháy: Căn cứ Thông tư 37.
   - Quân đội: Căn cứ CV Hướng dẫn phối hợp (Riêng phần này được phép trích dẫn CV vì là văn bản đặc thù).
"""

def call_gemini_expert_exhaustive(prompt, context):
    TARGET_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"]
    if not context: full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU HỖ TRỢ ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"
    
    last_error = ""
    for model_name in TARGET_MODELS:
        for index, key in enumerate(API_KEYS_LIST):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(full_prompt, request_options={'timeout': 60})
                return response.text
            except Exception as e:
                last_error = str(e)
                continue 
    return f"⚠️ Hệ thống đang bận. Vui lòng thử lại. (Error: {last_error})"

# --- 8. NẠP DỮ LIỆU ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_database_final():
    if not GCP_JSON or not DRIVE_FOLDER_ID: return {}, []
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        db = {} 
        logs = []
        processed = set()
        
        # Keywords bao gồm Nghị định 50, 136, 105...
        keywords = ["189", "106", "105", "50", "136", "36", "37", "48", "luat", "huy dong", "quan doi", "du thao", "phoi hop", "cv hd", "doi 3", "qcvn", "10:2025", "06", "10"]
        files = []
        for k in keywords:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and name contains '{k}'", fields="files(id, name)").execute().get('files', []))
            except: pass
        
        # Fallback lấy thêm file nếu ít
        if len(files) < 5:
             try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=50, fields="files(id, name)").execute().get('files', []))
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
    except Exception as e: return None, []

# --- 9. KHỞI ĐỘNG ---
with st.spinner('🔄 Đang khởi tạo hệ thống nghiệp vụ...'):
    database, logs = load_database_final()

if not database: st.error("❌ Không thể kết nối Kho dữ liệu. Vui lòng kiểm tra lại cấu hình."); st.stop()

# --- 10. CHAT LOGIC ---
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👮‍♂️" if m["role"] == "user" else "🔥"): 
        st.markdown(f'<div class="response-content">{m["content"]}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("Nhập nội dung cần tra cứu..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👮‍♂️").write(prompt)
    
    with st.chat_message("assistant", avatar="🔥"):
        with st.spinner("🧠 Đang phân tích và tra cứu văn bản pháp luật..."):
            
            # Router
            all_files = list(database.keys())
            selected_files_str = smart_router(prompt, all_files)
            
            # Retrieve
            relevant_context = ""
            if selected_files_str:
                for fname in all_files:
                    if fname in selected_files_str: relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
            
            # Backup Retrieve
            if not relevant_context:
                for fname, content in database.items():
                    is_penalty = ("phạt" in prompt or "lỗi" in prompt)
                    is_military = ("quân đội" in prompt or "chi viện" in prompt)
                    is_tech = ("trang bị" in prompt or "lắp" in prompt or "hệ thống" in prompt)
                    is_manage = ("trách nhiệm" in prompt or "hồ sơ" in prompt or "quản lý" in prompt)
                    is_force = ("lực lượng" in prompt or "chữa cháy" in prompt)

                    if is_military and any(x in fname.lower() for x in ["quan doi", "du thao", "phoi hop", "cv hd", "doi 3"]):
                         relevant_context += content
                    elif is_penalty and any(x in fname for x in ["106", "189"]):
                         relevant_context += content
                    elif is_tech and any(x in fname for x in ["10", "qc", "06"]) and not is_penalty: 
                        relevant_context += content
                    elif is_manage and any(x in fname for x in ["luat", "105", "36", "136", "50"]):
                        relevant_context += content
                    elif is_force and "37" in fname:
                        relevant_context += content

            # Generate
            response_text = call_gemini_expert_exhaustive(prompt, relevant_context)
        
        st.markdown(f'<div class="response-content">{response_text}</div>', unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
