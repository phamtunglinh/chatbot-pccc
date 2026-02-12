import streamlit as st
import requests
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
    page_title="Trợ lý PCCC (Quy trình Chuẩn)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
    }
    .stChatInput {border-radius: 20px;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI KEY & DRIVE ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_string = st.secrets["GEMINI_API_KEYS"]
    else: keys_string = st.secrets["GEMINI_API_KEY"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("⚠️ Lỗi cấu hình Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO TƯ DUY (ĐÃ KHÔI PHỤC NGUYÊN VĂN QUY TẮC CỦA ĐẠI ÚY) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC & CNCH.

⚡ DỮ LIỆU ĐƯỢC CHIA THÀNH 5 GIỎ:
1. [PHÁP LÝ]: NĐ 105, Luật... (Tra cứu Hồ sơ, Thủ tục, Phân cấp).
2. [XỬ PHẠT]: NĐ 106, 189... (Tra cứu Lỗi, Tiền phạt, Thẩm quyền).
3. [QUY CHUẨN]: QCVN 10, QCVN 06... (Tra cứu Trang bị, Kỹ thuật).
4. [CHỮA CHÁY]: Chiến thuật, Đội hình...
5. [KHÁC]: Văn bản bổ trợ.

🔴 QUY TRÌNH SUY LUẬN (BẮT BUỘC TUÂN THỦ KHI XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ):
    
    BƯỚC 1: KIỂM TRA DỮ LIỆU
    - Để xác định ai quản lý, bạn CẦN BIẾT: Tổng diện tích sàn, Số tầng, Chiều cao, Khối tích, Công năng chi tiết.
    - Nếu người dùng KHÔNG cung cấp đủ -> HÃY HỎI NGƯỢC LẠI NGƯỜI DÙNG để lấy thông tin. Đừng trả lời chung chung.
    
    BƯỚC 2: XÁC ĐỊNH CÔNG NĂNG CHÍNH (QUY TẮC 70%)
    - Nếu một công năng chiếm > 70% tổng diện tích -> Đó là công năng chính.
    - Nếu Công năng nhà ở > 70% -> Nhà ở kết hợp SXKD.
    - Nếu KHÔNG CÓ công năng nào vượt 70% -> Kết luận là: NHÀ HỖN HỢP.
    
    BƯỚC 3: ĐỐI CHIẾU PHỤ LỤC (Nghị định 105/2025 hoặc văn bản tương đương trong dữ liệu)
    - So sánh số tầng, khối tích, diện tích với Phụ lục I và Phụ lục II.
    
    BƯỚC 4: KẾT LUẬN (QUY TẮC ƯU TIÊN TUYỆT ĐỐI)
    - Nếu cơ sở đạt tiêu chí Phụ lục II -> PHÒNG CẢNH SÁT PCCC & CNCH (PC07) quản lý.
    - Lưu ý: Dù diện tích nhỏ (thuộc Phụ lục I) nhưng Số tầng cao (thuộc Phụ lục II) -> Vẫn là PC07 quản lý.
    - Chỉ khi nào KHÔNG đạt Phụ lục II mà chỉ đạt Phụ lục I -> Mới do UBND CẤP XÃ hoặc CÔNG AN HUYỆN quản lý.

🔴 QUY TRÌNH 2: ĐỐI VỚI CÂU HỎI VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH
    Thực hiện nghiêm ngặt 3 bước:
    
    BƯỚC 1: XÁC ĐỊNH MỨC PHẠT & HÌNH THỨC BỔ SUNG (NĐ 106)
    - Tìm mức phạt Cá nhân & Tổ chức.
    - Tìm Hình thức phạt bổ sung & Khắc phục hậu quả.
    -> Ghi rõ căn cứ từng mục.
    
    BƯỚC 2: SÀNG LỌC THẨM QUYỀN (Theo NĐ 189/2025)
    - So sánh mức phạt trung bình với quyền hạn tiền tối đa của các chức danh.
    - LOẠI BỎ NGAY các chức danh không đủ tiền phạt hoặc không đủ quyền phạt bổ sung.
    
    BƯỚC 3: TRÌNH BÀY (FORM MẪU):
    1. Về hành vi và mức tiền phạt:
       - Hành vi: ...
       - Mức phạt Cá nhân: ... -> Căn cứ: Điểm..., Khoản..., Điều... NĐ...
       - Mức phạt Tổ chức: ...
       
    2. Hình thức phạt bổ sung & KPHQ:
       - Phạt bổ sung: [Có/Không] -> Căn cứ: ...
       - KPHQ: [Có/Không] -> Căn cứ: ...

    3. Phân tích thẩm quyền xử phạt:
       *Chỉ xét các chức danh ĐỦ ĐIỀU KIỆN (Tiền + Bổ sung/KPHQ):*
       - [Chức danh A]: 
         + Thẩm quyền tiền: ... (Căn cứ: Khoản..., Điều... NĐ 189/2025).
         + Thẩm quyền bổ sung: ... (Nếu có).
         => KẾT LUẬN: Đủ thẩm quyền ký.

       - [Chức danh B]: ... (Tương tự)
       
    4. Đề xuất: Trình [Chức danh thấp nhất đủ quyền] quyết định.

🛑 NGUYÊN TẮC VÀNG (BẮT BUỘC):
   1. TUYỆT ĐỐI KHÔNG trả lời chung chung (kiểu "theo quy định pháp luật...").
   2. MỌI con số, nhận định đưa ra ĐỀU PHẢI CÓ TRÍCH DẪN CỤ THỂ.
   3. Nếu không tìm thấy điều khoản cụ thể trong dữ liệu -> Hãy nói thẳng "Trong dữ liệu hiện tại không tìm thấy quy định chi tiết về vấn đề này".
   4. KHÔNG chào hỏi lại.
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    # Cắt context thông minh
    if len(context) > 100000: 
        context = context[:30000] + "\n...[Lược bớt phần giữa]...\n" + context[-70000:]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (ĐƯỢC CHỌN TỪ CÁC GIỎ LIÊN QUAN):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: Áp dụng đúng Quy trình suy luận (Phân cấp 4 bước / Xử phạt 3 bước) đã được hướng dẫn.
    """
    
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for attempt in range(3):
        api_key = get_random_key()
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "system_instruction": {"parts": [{"text": ALGORITHMS_INSTRUCTION}]},
                "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"}]
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code in [404, 429, 500, 503]: continue
            except: continue
    return "⚠️ Hệ thống đang bận."

# --- 5. ĐỌC DỮ LIỆU (PHÂN LOẠI 5 GIỎ + LỌC FILE CŨ) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_final():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        # Lấy tối đa 500 file
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=500, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        buckets = {
            "phap_ly": [], "xu_phat": [], "quy_chuan": [], "chua_chay": [], "khac": []
        }
        
        log_accepted = []
        log_blocked = [] 
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            # 🛑 CHẶN FILE CŨ (136/144/50)
            if "136" in fname or "144" in fname or "50" in fname:
                log_blocked.append(f"🚫 {file['name']}")
                continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # --- ĐỌC DOCX (KÈM BẢNG) ---
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content += "\n".join([p.text for p in doc.paragraphs])
                    # Đọc bảng
                    tables = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                            tables.append(" | ".join(row_text))
                    if tables: content += "\n\n=== BẢNG BIỂU ===\n" + "\n".join(tables)

                # --- ĐỌC PDF ---
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # --- PHÂN LOẠI 5 GIỎ ---
                    if "105" in fname:
                        buckets["phap_ly"].append(item) # NĐ 105 vào pháp lý
                        log_accepted.append(f"🔹 {file['name']} (Quản lý)")
                    elif any(x in fname for x in ["106", "189", "296", "xu phat", "vi pham"]):
                        buckets["xu_phat"].append(item)
                        log_accepted.append(f"⚖️ {file['name']} (Xử phạt)")
                    elif any(x in fname for x in ["qcvn", "tcvn", "10:2025", "06:2022", "3890", "trang bi", "ky thuat"]):
                        buckets["quy_chuan"].append(item)
                        log_accepted.append(f"🛠️ {file['name']} (Kỹ thuật)")
                    elif any(x in fname for x in ["chua chay", "cnch", "chien thuat", "doi hinh"]):
                        buckets["chua_chay"].append(item)
                        log_accepted.append(f"🚒 {file['name']} (Chữa cháy)")
                    elif any(x in fname for x in ["nghi dinh", "luat", "thong tu", "ho so"]):
                        buckets["phap_ly"].append(item)
                        log_accepted.append(f"📂 {file['name']}")
                    else:
                        buckets["khac"].append(item)
                        log_accepted.append(f"📄 {file['name']}")
                        
            except: continue
        return buckets, log_accepted, log_blocked
    except Exception as e: return None, [str(e)], []

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (QUY TRÌNH CHUẨN)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động hệ thống & Nạp quy trình suy luận...'):
    data_buckets, log_ok, log_bad = load_data_final()

if not data_buckets: st.error("❌ Lỗi dữ liệu."); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔍 DỮ LIỆU ĐÃ NẠP")
    
    with st.expander("🚫 FILE BỊ CHẶN (CŨ)", expanded=True):
        if log_bad:
            for log in log_bad: st.error(log)
        else: st.success("Không có file cũ.")
            
    with st.expander("1. 📂 Văn bản Pháp lý (NĐ 105...)", expanded=True):
        st.write(f"SL: {len(data_buckets['phap_ly'])}")
    with st.expander("2. ⚖️ Văn bản Xử phạt (NĐ 106...)", expanded=True):
        st.write(f"SL: {len(data_buckets['xu_phat'])}")
    with st.expander("3. 🛠️ Quy chuẩn Kỹ thuật", expanded=True):
        st.write(f"SL: {len(data_buckets['quy_chuan'])}")
    with st.expander("4. 🚒 Quy trình Chữa cháy"):
        st.write(f"SL: {len(data_buckets['chua_chay'])}")
    with st.expander("5. 📄 Văn bản Khác"):
        st.write(f"SL: {len(data_buckets['khac'])}")

    st.divider()
    for log in log_ok: st.text(log)

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHỌN GIỎ
    p = prompt.lower()
    ctx_list = []
    labels = []
    
    # 1. QUẢN LÝ / HỒ SƠ -> Pháp lý
    if any(x in p for x in ["quản lý", "phân cấp", "hồ sơ", "thủ tục", "karaoke", "nhà hàng"]):
        ctx_list.extend(data_buckets["phap_ly"])
        labels.append("Pháp lý")
        
    # 2. XỬ PHẠT -> Xử phạt + Pháp lý
    if any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi"]):
        ctx_list.extend(data_buckets["xu_phat"])
        ctx_list.extend(data_buckets["phap_ly"])
        labels.append("Xử phạt")

    # 3. KỸ THUẬT -> Quy chuẩn
    if any(x in p for x in ["trang bị", "lắp đặt", "hệ thống", "báo cháy", "chữa cháy", "quy chuẩn"]):
        ctx_list.extend(data_buckets["quy_chuan"])
        labels.append("Kỹ thuật")

    # 4. CHỮA CHÁY
    if any(x in p for x in ["chiến thuật", "đội hình", "xe", "cứu nạn"]):
        ctx_list.extend(data_buckets["chua_chay"])
        labels.append("Chữa cháy")

    # Fallback
    if not ctx_list:
        ctx_list.extend(data_buckets["phap_ly"])
        ctx_list.extend(data_buckets["khac"])
        labels.append("Tổng hợp")

    final_ctx = "\n".join(ctx_list)
    label_str = " + ".join(labels)

    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang áp dụng Quy trình suy luận ({label_str})...*")
        reply = call_gemini_logic(prompt, final_ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
