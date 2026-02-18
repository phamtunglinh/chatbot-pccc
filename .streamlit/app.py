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

# --- 1. CẤU HÌNH GIAO DIỆN CHUYÊN NGHIỆP ---
st.set_page_config(
    page_title="HỆ THỐNG TRỢ LÝ ẢO PCCC & CNCH",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Hệ thống hỗ trợ nghiệp vụ PCCC PC07"
    }
)

# --- CSS TÙY CHỈNH (GIAO DIỆN CAO CẤP) ---
st.markdown("""
<style>
    /* 1. TỔNG THỂ */
    [data-testid="stAppViewContainer"] {
        background-color: #f8f9fa; /* Màu nền xám rất nhạt cho dịu mắt */
    }
    
    /* 2. HEADER BANNER */
    .header-container {
        background: linear-gradient(135deg, #b71c1c 0%, #0d47a1 100%); /* Gradient Đỏ - Xanh Cảnh sát */
        padding: 20px;
        border-radius: 0 0 15px 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-top: -60px; /* Kéo lên che phần padding mặc định */
        margin-bottom: 20px;
        color: white;
        text-align: center;
    }
    .header-title {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 700;
        font-size: 28px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 0;
    }
    .header-subtitle {
        font-size: 14px;
        opacity: 0.9;
        font-weight: 300;
        margin-top: 5px;
    }

    /* 3. SIDEBAR (THANH ĐIỀU KHIỂN) */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
    }
    .sidebar-header {
        font-weight: bold;
        color: #b71c1c;
        border-bottom: 2px solid #b71c1c;
        padding-bottom: 5px;
        margin-bottom: 10px;
        margin-top: 20px;
    }
    .status-card {
        background-color: #e3f2fd;
        border-left: 4px solid #1565c0;
        padding: 10px;
        border-radius: 4px;
        font-size: 0.85em;
        color: #0d47a1;
        margin-bottom: 10px;
    }

    /* 4. CHAT INTERFACE */
    .stChatInput textarea {
        border-radius: 25px !important;
        border: 1px solid #cfd8dc;
    }
    
    /* Ẩn các thành phần thừa */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* Ẩn các box kỹ thuật cũ */
    .router-box, .success-box {display: none;}
    
    /* 5. TEXT HIỂN THỊ KẾT QUẢ */
    .result-text {
        font-family: 'Segoe UI', sans-serif;
        line-height: 1.6;
        color: #212121;
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER GIAO DIỆN ---
st.markdown("""
<div class="header-container">
    <div class="header-title">🛡️ TRUNG TÂM CHỈ HUY SỐ PCCC & CNCH</div>
    <div class="header-subtitle">HỆ THỐNG TRỢ LÝ ẢO NGHIỆP VỤ - PC07 PHÚ THỌ</div>
</div>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI API (FAILOVER - TUẦN TỰ) ---
API_KEYS_LIST = []
try:
    if "GEMINI_API_KEYS" in st.secrets: 
        keys_string = st.secrets["GEMINI_API_KEYS"]
        API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    elif "GEMINI_API_KEY" in st.secrets:
        API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]
    
    if not API_KEYS_LIST: st.error("❌ LỖI HỆ THỐNG: Không tìm thấy Khóa bảo mật API!"); st.stop()
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e: st.error(f"⚠️ Lỗi cấu hình hệ thống: {str(e)}"); st.stop()

# --- 3. BỘ NÃO THAM MƯU (ROUTER) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: Chọn tài liệu "TỐI GIẢN NHƯNG ĐÚNG TRỌNG TÂM".

1. GIỎ PHÁP LÝ - QUẢN LÝ (TRÁCH NHIỆM / ĐIỀU KIỆN / HỒ SƠ / KIỂM TRA):
   - Dấu hiệu: "Trách nhiệm người đứng đầu", "Điều kiện an toàn", "Hồ sơ gồm gì", "Thủ tục", "Kiểm tra an toàn", "Thẩm duyệt", "Nghiệm thu".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Luật PCCC và CNCH], [Nghị định 105], [Thông tư 36].

2. GIỎ CÔNG TÁC CHỮA CHÁY (LỰC LƯỢNG):
   - Dấu hiệu: "Việc chữa cháy", "Nhiệm vụ chữa cháy", "Tổ chức chữa cháy", "Đội PCCC cơ sở", "Chiến thuật".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Thông tư 37] (và [Thông tư 48] nếu hỏi trang phục).

3. GIỎ KỸ THUẬT (TRANG BỊ / HỆ THỐNG):
   - Dấu hiệu: "Cần trang bị gì?", "Lắp hệ thống nào?", "Bình chữa cháy", "Báo cháy", "Khoảng cách", "Lối thoát nạn".
   - HÀNH ĐỘNG: CHỈ CHỌN [QCVN 10] (và [QCVN 06] nếu cần).

4. GIỎ HUY ĐỘNG (QUÂN ĐỘI / PHỐI HỢP):
   - Dấu hiệu: "Quân đội", "Chi viện", "Phối hợp", "Đội 3".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN file có tên chứa "CV HD", "QUÂN ĐỘI", "ĐỘI 3".

5. GIỎ XỬ PHẠT (LỖI / TIỀN / THẨM QUYỀN):
   - Dấu hiệu: "Lỗi", "Phạt bao nhiêu", "Xử lý", "Bị sao", "Vi phạm".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 106] (Tiền) VÀ [Nghị định 189] (Thẩm quyền).
   - CẤM CHỌN: Luật, NĐ 105, TT 36 (để tránh nhiễu).

6. GIỎ PHÂN CẤP QUẢN LÝ (AI QUẢN LÝ CƠ SỞ):
   - Dấu hiệu: "Cơ sở này do ai quản lý", "Thuộc danh mục nào", "Xã hay Công an quản lý", "Phụ lục mấy".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 105].

OUTPUT: Chỉ trả về danh sách tên file có trong kho, ngăn cách bằng dấu phẩy.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE HIỆN CÓ: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    for key in API_KEYS_LIST:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text.strip()
        except: continue
    return ""

# --- 4. BỘ NÃO CHUYÊN GIA (EXPERT) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🛑 NGUYÊN TẮC VÀNG:
1. TUYỆT ĐỐI KHÔNG trả lời chung chung.
2. MỌI con số, nhận định ĐỀU PHẢI CÓ TRÍCH DẪN: "...(Căn cứ: Điểm..., Khoản..., Điều..., Văn bản...)".
3. Nếu thiếu dữ liệu -> HỎI NGƯỢC LẠI NGƯỜI DÙNG.

🔴 RULE 1: SUY LUẬN XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (QUAN TRỌNG - THEO NĐ 105/2025):
   BẮT BUỘC TUÂN THỦ 4 BƯỚC SAU:
   
   - BƯỚC 1: KIỂM TRA DỮ LIỆU ĐẦU VÀO
     + Cần biết: Tổng diện tích sàn, Số tầng, Chiều cao, Khối tích, Công năng chi tiết.
     + Nếu người dùng KHÔNG cung cấp đủ -> HÃY HỎI NGƯỢC LẠI NGƯỜI DÙNG để lấy thông tin. Đừng trả lời chung chung.

   - BƯỚC 2: XÁC ĐỊNH CÔNG NĂNG CHÍNH (QUY TẮC 70%)
     + Nếu một công năng chiếm > 70% tổng diện tích -> Đó là công năng chính.
     + Nếu Công năng nhà ở > 70% -> Nhà ở kết hợp SXKD.
     + Nếu KHÔNG CÓ công năng nào vượt 70% -> Kết luận là: NHÀ HỖN HỢP.

   - BƯỚC 3: ĐỐI CHIẾU PHỤ LỤC (Nghị định 105/2025/NĐ-CP)
     + So sánh số tầng, khối tích, diện tích với Phụ lục I (Diện quản lý) và Phụ lục II (Nguy hiểm cháy nổ).

   - BƯỚC 4: KẾT LUẬN (QUY TẮC ƯU TIÊN TUYỆT ĐỐI)
     + Nếu cơ sở đạt tiêu chí Phụ lục II -> PHÒNG CẢNH SÁT PCCC & CNCH (PC07) quản lý.
     + Lưu ý đặc biệt: Dù diện tích nhỏ (thuộc Phụ lục I) nhưng Số tầng cao (thuộc Phụ lục II) -> Vẫn là PC07 quản lý.
     + Chỉ khi nào KHÔNG đạt tiêu chí Phụ lục II mà chỉ đạt tiêu chí Phụ lục I -> Mới do UBND CẤP XÃ quản lý.

🔴 RULE 2: XỬ PHẠT (NĐ 106 + 189) - CƠ CHẾ "LỌC ẨN":
   BẮT BUỘC TRÌNH BÀY THEO FORM:
   1. Hành vi & Mức phạt tiền:
      - Cá nhân: X đồng (Căn cứ NĐ 106).
      - Tổ chức: 2 * X đồng.
   2. Bổ sung & KPHQ: [Có/Không] -> Chi tiết.
   3. Xét thẩm quyền (QUAN TRỌNG: CHỈ XÉT THEO MỨC CÁ NHÂN X):
      *Chỉ xét: Chiến sĩ CA, Đội trưởng, Trưởng CA Xã, Trưởng Phòng PC07, Giám đốc CA Tỉnh, Chủ tịch Tỉnh.*
      *Nguyên tắc LỌC ẨN: Chỉ hiển thị những người ĐỦ THẨM QUYỀN TIỀN (>= X).*
      - Xét [Chức danh A (Đủ tiền)]: 
        + Thẩm quyền tiền: ...
        + Thẩm quyền Bổ sung/KPHQ: ...
        => Kết luận: Đủ thẩm quyền ký hay không.
   4. Đề xuất: Trình người thấp nhất đủ điều kiện.

🟢 RULE 3: CÔNG TÁC CHỮA CHÁY (TT 37):
   - Trả lời về nhiệm vụ, quyền hạn, chỉ huy chữa cháy.

🔴 RULE 4: TRÁCH NHIỆM / HỒ SƠ (Luật + 105 + 36):
   - Trả lời chi tiết theo quy định pháp luật.

🔵 RULE 5: KỸ THUẬT (QCVN 10):
   - Chỉ căn cứ QCVN 10. Trả lời thông số.

🟣 RULE 6: HUY ĐỘNG QUÂN ĐỘI:
   - Căn cứ: CV HD CÔNG TÁC CC&CNCH PHỐI HỢP QUÂN ĐỘI.
"""

def call_gemini_expert_exhaustive(prompt, context):
    TARGET_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"]
    if not context: full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"
    
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
    return f"⚠️ Hệ thống quá tải. Vui lòng thử lại sau giây lát. (Error: {last_error})"

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
        
        # Bổ sung keywords cho Nghị định 105
        keywords = ["189", "106", "105", "50", "36", "37", "48", "luat", "huy dong", "quan doi", "du thao", "phoi hop", "cv hd", "doi 3", "qcvn", "10:2025", "06", "10"]
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

# --- 6. KHỞI ĐỘNG HỆ THỐNG ---
with st.spinner('🔄 Đang kết nối Cơ sở dữ liệu Nghiệp vụ...'):
    database, logs = load_database_final()

if not database: st.error(f"❌ Lỗi dữ liệu: {logs[0]}"); st.stop()

# --- 7. SIDEBAR (DASHBOARD) ---
with st.sidebar:
    st.markdown('<div class="sidebar-header">⚙️ BẢNG ĐIỀU KHIỂN</div>', unsafe_allow_html=True)
    
    # Trạng thái hệ thống
    st.markdown(f"""
    <div class="status-card">
        <b>Trạng thái:</b> 🟢 Sẵn sàng<br>
        <b>Model:</b> Auto-Switch (2.5)<br>
        <b>Failover:</b> Active (Key 1 -> n)<br>
        <b>Văn bản số hóa:</b> {len(database)} tài liệu
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-header">📂 KHO DỮ LIỆU SỐ</div>', unsafe_allow_html=True)
    with st.expander("Tra cứu danh mục", expanded=True):
        st.markdown(f"<div style='font-size: 0.85em; color: #424242;'>", unsafe_allow_html=True)
        for l in logs: st.markdown(f"{l}")
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.caption("© 2025 Phòng Cảnh sát PCCC & CNCH - Công an tỉnh Phú Thọ")

# --- 8. KHUNG CHAT CHÍNH ---
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👮‍♂️" if m["role"] == "user" else "🔥"): 
        st.markdown(f'<div class="result-text">{m["content"]}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("Nhập nội dung cần tra cứu hoặc hỏi đáp..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👮‍♂️").write(prompt)
    
    with st.chat_message("assistant", avatar="🔥"):
        with st.spinner("🧠 Đang phân tích câu hỏi và tra cứu văn bản pháp luật..."):
            
            # 1. Router
            all_files = list(database.keys())
            selected_files_str = smart_router(prompt, all_files)
            
            # 2. Context Logic
            relevant_context = ""
            if selected_files_str:
                for fname in all_files:
                    if fname in selected_files_str: relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
            
            # 3. Backup Logic
            if not relevant_context:
                for fname, content in database.items():
                    is_penalty = ("phạt" in prompt or "lỗi" in prompt or "xử lý" in prompt)
                    is_military = ("quân đội" in prompt or "chi viện" in prompt or "phối hợp" in prompt)
                    is_tech = ("trang bị" in prompt or "lắp" in prompt or "hệ thống" in prompt)
                    is_manage = ("trách nhiệm" in prompt or "hồ sơ" in prompt or "điều kiện" in prompt or "kiểm tra" in prompt)
                    is_force = ("lực lượng" in prompt or "chữa cháy" in prompt or "nhiệm vụ" in prompt)
                    is_classification = ("quản lý" in prompt or "cơ quan" in prompt or "ủy ban" in prompt or "xã" in prompt or "công an" in prompt)

                    if is_military and any(x in fname.lower() for x in ["quan doi", "du thao", "phoi hop", "cv hd", "doi 3"]):
                         relevant_context += content
                    elif is_penalty and any(x in fname for x in ["106", "189"]):
                         relevant_context += content
                    elif is_tech and any(x in fname for x in ["10", "qc", "06"]) and not is_penalty: 
                        relevant_context += content
                    elif is_manage and any(x in fname for x in ["luat", "105", "36"]):
                        relevant_context += content
                    elif is_force and "37" in fname:
                        relevant_context += content
                    elif is_classification and "105" in fname:
                        relevant_context += content

            # 4. Expert
            response_text = call_gemini_expert_exhaustive(prompt, relevant_context)
        
        st.markdown(f'<div class="result-text">{response_text}</div>', unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
