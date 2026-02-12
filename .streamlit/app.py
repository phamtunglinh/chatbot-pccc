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
    page_title="Trợ lý PCCC (Ổn định & Thông minh)",
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

# --- 3. BỘ NÃO TƯ DUY (ĐẦY ĐỦ QUY TRÌNH SUY LUẬN) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC & CNCH.

⚡ DỮ LIỆU ĐƯỢC CHIA THÀNH 5 GIỎ:
1. [PHÁP LÝ]: NĐ 105, Luật... (Tra cứu Hồ sơ, Thủ tục).
2. [XỬ PHẠT]: NĐ 106 (Mức phạt), NĐ 189 (Thẩm quyền).
3. [QUY CHUẨN]: QCVN 10, QCVN 06... (Tra cứu Trang bị).
4. [CHỮA CHÁY]: Chiến thuật...
5. [KHÁC]: Văn bản bổ trợ.

🧠 KỸ NĂNG SUY LUẬN LỖI (MAPPING):
   Người dùng hỏi ngôn ngữ đời thường -> Bạn phải tìm theo ngôn ngữ Luật (trong NĐ 106):
   - "Không có..." -> Tìm: "Không lập", "Không trang bị", "Không lắp đặt".
   - "Hồ sơ" -> Tìm: "Vi phạm quy định về hồ sơ quản lý".
   - "Thiếu..." -> Tìm: "Không đầy đủ".

🔴 QUY TRÌNH 1: XỬ PHẠT VI PHẠM HÀNH CHÍNH (NĐ 106 & 189)
    
    BƯỚC 1: XÁC ĐỊNH MỨC PHẠT (NĐ 106)
    - Tìm hành vi (dùng kỹ năng suy luận).
    - Xác định Mức phạt tiền (Cá nhân & Tổ chức).
    - Xác định Phạt bổ sung / Khắc phục hậu quả.
    
    BƯỚC 2: SÀNG LỌC THẨM QUYỀN (NĐ 189)
    - So sánh mức phạt tối đa với quyền hạn của các chức danh.
    - LOẠI BỎ NGAY chức danh không đủ tiền hoặc không đủ quyền phạt bổ sung.
    
    BƯỚC 3: TRÌNH BÀY (FORM MẪU):
    1. Hành vi: [Tên pháp lý]
    2. Mức phạt: 
       - Cá nhân: ... (Căn cứ NĐ 106).
       - Tổ chức: ...
    3. Biện pháp bổ sung/KPHQ: ...
    4. Phân tích thẩm quyền:
       - [Chức danh A]: Quyền phạt ... -> ĐỦ/KHÔNG.
       - [Chức danh B]: Quyền phạt ... -> ĐỦ/KHÔNG.
    5. Đề xuất: Trình [Chức danh thấp nhất đủ quyền] ra quyết định.

🔵 QUY TRÌNH 2: XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (NĐ 105)
    
    BƯỚC 1: KIỂM TRA DỮ LIỆU ĐẦU VÀO (Diện tích, Tầng, Khối tích, Công năng).
    
    BƯỚC 2: XÁC ĐỊNH CÔNG NĂNG CHÍNH (QUY TẮC 70%)
    - Công năng > 70% -> Chính.
    - Nhà ở > 70% -> Nhà ở kết hợp SXKD.
    - Không có > 70% -> Hỗn hợp.
    
    BƯỚC 3: ĐỐI CHIẾU PHỤ LỤC (NĐ 105).
    
    BƯỚC 4: KẾT LUẬN (ƯU TIÊN TUYỆT ĐỐI)
    - Có tên trong Phụ lục II -> PC07 quản lý.
    - Chỉ thuộc Phụ lục I (không thuộc II) -> Công an Huyện hoặc Xã.

🟢 QUY TRÌNH 3: TRANG BỊ KỸ THUẬT (QCVN 10)
    - Tra cứu Bảng biểu -> Liệt kê hệ thống bắt buộc.

🛑 NGUYÊN TẮC VÀNG: KHÔNG trả lời chung chung. TRÍCH DẪN CỤ THỂ.
"""

# --- 4. HÀM GỌI AI (ĐÃ TỐI ƯU DUNG LƯỢNG AN TOÀN) ---
def call_gemini_logic(prompt, context):
    # GIỚI HẠN AN TOÀN: 500.000 KÝ TỰ (Đủ chứa 106, 189, 105 mà không gây Timeout)
    if len(context) > 500000: 
        context = context[:500000]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (ĐÃ NẠP ƯU TIÊN 106, 189, 105):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: Áp dụng Quy trình Suy luận (Xử phạt/Phân cấp) đã hướng dẫn.
    """
    
    # Ưu tiên model 1.5 Flash (Nhanh và ổn định nhất hiện nay)
    models = ["gemini-1.5-flash", "gemini-2.0-flash"]
    
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
                # Timeout 90s để xử lý dữ liệu lớn
                response = requests.post(url, headers=headers, json=payload, timeout=90)
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code in [404, 429, 500, 503]: continue
            except: continue
    return "⚠️ Hệ thống đang bận (Quá tải hoặc lỗi mạng). Vui lòng thử lại câu hỏi ngắn hơn."

# --- 5. ĐỌC DỮ LIỆU (CƠ CHẾ SĂN TÌM VIP) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_final_stable():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        
        buckets = {
            "phap_ly": [], "xu_phat": [], "quy_chuan": [], "chua_chay": [], "khac": []
        }
        log_ok = []
        log_bad = []
        processed_ids = set() 

        # --- PHA 1: SĂN TÌM CÁC FILE VIP ---
        target_queries = [
            "name contains '189'", # Ưu tiên THẨM QUYỀN
            "name contains '106'", # Ưu tiên MỨC PHẠT
            "name contains '105'", 
            "name contains '10'", 
            "name contains 'xu phat'"
        ]
        
        vip_files = []
        for q in target_queries:
            try:
                res = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and {q}", fields="files(id, name, mimeType)").execute()
                vip_files.extend(res.get('files', []))
            except: continue

        # --- PHA 2: LẤY FILE CÒN LẠI (GIỚI HẠN 200 FILE ĐỂ TRÁNH QUÁ TẢI) ---
        try:
            res_all = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name, mimeType)").execute()
            all_files = res_all.get('files', [])
        except: all_files = []
        
        # Gộp lại (Ưu tiên VIP lên đầu)
        final_file_list = vip_files + all_files
        
        for file in final_file_list:
            if file['id'] in processed_ids: continue 
            processed_ids.add(file['id'])
            
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            # 🛑 CHẶN FILE CŨ
            is_trash = False
            if "144" in fname and "106" not in fname and "189" not in fname: is_trash = True
            if "136" in fname and "105" not in fname: is_trash = True
            if "50" in fname and "105" not in fname: is_trash = True
            if is_trash:
                log_bad.append(f"🚫 {file['name']}")
                continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content += "\n".join([p.text for p in doc.paragraphs])
                    tables = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                            tables.append(" | ".join(row_text))
                    if tables: content += "\n\n=== BẢNG BIỂU ===\n" + "\n".join(tables)

                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    if any(x in fname for x in ["106", "189", "296", "xu phat", "vi pham"]):
                        buckets["xu_phat"].append(item)
                        log_ok.append(f"⚖️ {file['name']}")
                    elif any(x in fname for x in ["qcvn", "tcvn", "10:2025", "trang bi"]):
                        buckets["quy_chuan"].append(item)
                        log_ok.append(f"🛠️ {file['name']}")
                    elif any(x in fname for x in ["105", "nghi dinh", "luat", "thong tu", "ho so"]):
                        buckets["phap_ly"].append(item)
                        log_ok.append(f"🔹 {file['name']}")
                    elif any(x in fname for x in ["chua chay", "cnch"]):
                        buckets["chua_chay"].append(item)
                        log_ok.append(f"🚒 {file['name']}")
                    else:
                        buckets["khac"].append(item)
                        log_ok.append(f"📄 {file['name']}")
                        
            except: continue
        return buckets, log_ok, log_bad
    except Exception as e: return None, [str(e)], []

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (STABLE)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang săn tìm dữ liệu & Nạp quy trình...'):
    data_buckets, log_ok, log_bad = load_data_final_stable()

if not data_buckets: st.error("❌ Lỗi dữ liệu."); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔍 DỮ LIỆU ĐÃ NẠP")
    
    has_189 = any("189" in log for log in log_ok)
    has_106 = any("106" in log for log in log_ok)
    
    if has_189: st.success("✅ Đã có NĐ 189 (Thẩm quyền)")
    else: st.error("❌ CHƯA CÓ NĐ 189!")
    
    if has_106: st.success("✅ Đã có NĐ 106 (Mức phạt)")
    else: st.warning("⚠️ CHƯA CÓ NĐ 106")

    with st.expander("Chi tiết file"):
        for log in log_ok: st.text(log)
    with st.expander("File bị chặn (Cũ)"):
        for log in log_bad: st.error(log)

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
    
    # XỬ PHẠT (Lấy 106 + 189 + 105)
    if any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi", "không có", "hồ sơ", "thiếu"]):
        # ƯU TIÊN 189 (Thẩm quyền) & 106 (Phạt) LÊN ĐẦU
        nd_189 = [item for item in data_buckets["xu_phat"] if "189" in item]
        nd_106 = [item for item in data_buckets["xu_phat"] if "106" in item]
        other_xp = [item for item in data_buckets["xu_phat"] if "189" not in item and "106" not in item]
        
        ctx_list.extend(nd_189)
        ctx_list.extend(nd_106)
        ctx_list.extend(other_xp)
        ctx_list.extend(data_buckets["phap_ly"]) # Lấy 105 để hiểu hồ sơ
        labels.append("Xử phạt (189+106)")

    # QUẢN LÝ
    elif any(x in p for x in ["quản lý", "phân cấp", "thuộc diện", "karaoke"]):
        ctx_list.extend(data_buckets["phap_ly"])
        labels.append("Quản lý (NĐ 105)")

    # KỸ THUẬT
    elif any(x in p for x in ["trang bị", "lắp đặt", "hệ thống"]):
        ctx_list.extend(data_buckets["quy_chuan"])
        labels.append("Kỹ thuật (QCVN 10)")
    
    else:
        ctx_list.extend(data_buckets["phap_ly"])
        ctx_list.extend(data_buckets["khac"])
        labels.append("Tổng hợp")

    final_ctx = "\n".join(ctx_list)

    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang suy luận ({' + '.join(labels)})...*")
        reply = call_gemini_logic(prompt, final_ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
