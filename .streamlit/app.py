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
    page_title="Trợ lý PCCC (AI Suy Luận)",
    page_icon="🧠",
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

# --- 3. BỘ NÃO TƯ DUY (BỔ SUNG KHẢ NĂNG SUY LUẬN LỖI) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC & CNCH.

⚡ DỮ LIỆU ĐƯỢC CHIA THÀNH 5 GIỎ:
1. [PHÁP LÝ]: NĐ 105, Luật... (Tra cứu Hồ sơ, Thủ tục).
2. [XỬ PHẠT]: NĐ 106, 189... (Tra cứu Lỗi, Tiền phạt).
3. [QUY CHUẨN]: QCVN 10, QCVN 06... (Tra cứu Trang bị).
4. [CHỮA CHÁY]: Chiến thuật...
5. [KHÁC]: Văn bản bổ trợ.

🧠 KỸ NĂNG SUY LUẬN LỖI (QUAN TRỌNG KHI TRA CỨU XỬ PHẠT):
   Người dùng thường hỏi bằng ngôn ngữ đời thường. Bạn phải "DỊCH" sang ngôn ngữ Luật trong NĐ 106:
   - "Không có..." -> Tìm từ khóa: "Không lập", "Không trang bị", "Không lắp đặt", "Không lưu trữ".
   - "Hồ sơ" -> Tìm điều khoản: "Vi phạm quy định về hồ sơ quản lý".
   - "Thiếu..." -> Tìm từ khóa: "Không đầy đủ", "Không đảm bảo số lượng".
   - "Hỏng..." -> Tìm từ khóa: "Không hoạt động", "Hư hỏng", "Không bảo dưỡng".

🔴 QUY TRÌNH 1: XỬ PHẠT VI PHẠM HÀNH CHÍNH (3 BƯỚC)
    
    BƯỚC 1: TRA CỨU HÀNH VI (Trong Giỏ XỬ PHẠT - NĐ 106)
    - Dùng kỹ năng suy luận ở trên để tìm hành vi tương ứng.
    - Xác định Mức phạt tiền (Cá nhân & Tổ chức).
    
    BƯỚC 2: SÀNG LỌC THẨM QUYỀN (Trong Giỏ XỬ PHẠT - NĐ 189)
    - So sánh mức phạt tối đa của hành vi với thẩm quyền của các chức danh (Xã -> Huyện -> PC07 -> Giám đốc/Chủ tịch).
    - LOẠI BỎ người không đủ quyền.
    
    BƯỚC 3: TRÌNH BÀY
    - Hành vi: [Tên chính xác trong NĐ 106]
    - Phạt tiền: ... (Căn cứ: Điểm..., Khoản..., Điều..., NĐ 106).
    - Biện pháp khắc phục (nếu có): ...
    - Thẩm quyền: [Chức danh thấp nhất đủ quyền ký].

🔵 QUY TRÌNH 2: PHÂN CẤP QUẢN LÝ (4 BƯỚC - NĐ 105)
    B1: Kiểm tra thông tin (Diện tích, Tầng, Khối tích). Nếu thiếu -> Hỏi lại.
    B2: Xác định công năng chính (Quy tắc 70%).
    B3: Đối chiếu Phụ lục I và II của NĐ 105.
    B4: KẾT LUẬN:
      - Có trong Phụ lục II -> PC07 quản lý.
      - Có trong Phụ lục I (nhưng ko có trong II) -> Công an Huyện hoặc Xã.

🟢 QUY TRÌNH 3: TRANG BỊ KỸ THUẬT (QCVN 10)
    - Tra cứu Bảng biểu trong QCVN 10.
    - Liệt kê hệ thống bắt buộc.

YÊU CẦU: Trả lời ngắn gọn, nghiệp vụ, trích dẫn rõ ràng.
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    if len(context) > 100000: 
        context = context[:30000] + "\n...[Lược bớt]...\n" + context[-70000:]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (ĐÃ LỌC SẠCH FILE CŨ):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: 
    1. Nếu hỏi lỗi/phạt -> Dùng Kỹ năng suy luận để tìm trong NĐ 106.
    2. Nếu hỏi quản lý -> Dùng NĐ 105.
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

# --- 5. ĐỌC DỮ LIỆU (5 GIỎ + LỌC 136/144) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart_v2():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=500, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        buckets = {
            "phap_ly": [], "xu_phat": [], "quy_chuan": [], "chua_chay": [], "khac": []
        }
        
        log_ok = []
        log_bad = [] 
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            # 🛑 CHẶN FILE CŨ
            if "136" in fname or "144" in fname or "50" in fname:
                log_bad.append(f"🚫 {file['name']}")
                continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # DOCX + TABLE
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content += "\n".join([p.text for p in doc.paragraphs])
                    tables = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                            tables.append(" | ".join(row_text))
                    if tables: content += "\n\n=== BẢNG BIỂU ===\n" + "\n".join(tables)

                # PDF
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    if "105" in fname:
                        buckets["phap_ly"].append(item)
                        log_ok.append(f"🔹 {file['name']} (Quản lý)")
                    elif any(x in fname for x in ["106", "189", "296", "xu phat", "vi pham"]):
                        buckets["xu_phat"].append(item)
                        log_ok.append(f"⚖️ {file['name']} (Xử phạt)")
                    elif any(x in fname for x in ["qcvn", "tcvn", "10:2025", "06:2022", "trang bi", "ky thuat"]):
                        buckets["quy_chuan"].append(item)
                        log_ok.append(f"🛠️ {file['name']} (Kỹ thuật)")
                    elif any(x in fname for x in ["chua chay", "cnch"]):
                        buckets["chua_chay"].append(item)
                        log_ok.append(f"🚒 {file['name']}")
                    elif any(x in fname for x in ["nghi dinh", "luat", "thong tu", "ho so"]):
                        buckets["phap_ly"].append(item)
                        log_ok.append(f"📂 {file['name']}")
                    else:
                        buckets["khac"].append(item)
                        log_ok.append(f"📄 {file['name']}")
                        
            except: continue
        return buckets, log_ok, log_bad
    except Exception as e: return None, [str(e)], []

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🧠</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (AI SUY LUẬN)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang kích hoạt bộ não suy luận...'):
    data_buckets, log_ok, log_bad = load_data_smart_v2()

if not data_buckets: st.error("❌ Lỗi dữ liệu."); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔍 DỮ LIỆU")
    with st.expander("🚫 FILE BỊ CHẶN (CŨ)", expanded=True):
        if log_bad: 
            for log in log_bad: st.error(log)
        else: st.success("Sạch sẽ.")
            
    with st.expander("1. 📂 Văn bản Pháp lý"): st.write(f"SL: {len(data_buckets['phap_ly'])}")
    with st.expander("2. ⚖️ Văn bản Xử phạt"): st.write(f"SL: {len(data_buckets['xu_phat'])}")
    with st.expander("3. 🛠️ Quy chuẩn Kỹ thuật"): st.write(f"SL: {len(data_buckets['quy_chuan'])}")
    with st.expander("4. 🚒 Quy trình Chữa cháy"): st.write(f"SL: {len(data_buckets['chua_chay'])}")
    with st.expander("5. 📄 Văn bản Khác"): st.write(f"SL: {len(data_buckets['khac'])}")
    
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
    
    # 1. XỬ PHẠT (Ưu tiên số 1 khi có từ 'phạt', 'hồ sơ' + 'không có')
    if any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi", "không có hồ sơ"]):
        ctx_list.extend(data_buckets["xu_phat"]) # Lấy NĐ 106
        ctx_list.extend(data_buckets["phap_ly"]) # Lấy NĐ 105 để hiểu hồ sơ là gì
        labels.append("Xử phạt (NĐ 106)")
        
    # 2. QUẢN LÝ
    elif any(x in p for x in ["quản lý", "phân cấp", "thuộc diện"]):
        ctx_list.extend(data_buckets["phap_ly"])
        labels.append("NĐ 105")
        
    # 3. KỸ THUẬT
    elif any(x in p for x in ["trang bị", "lắp đặt", "hệ thống"]):
        ctx_list.extend(data_buckets["quy_chuan"])
        labels.append("QCVN 10")

    # 4. CHỮA CHÁY
    elif any(x in p for x in ["chiến thuật", "đội hình"]):
        ctx_list.extend(data_buckets["chua_chay"])
        labels.append("Chữa cháy")
        
    else:
        ctx_list.extend(data_buckets["phap_ly"])
        ctx_list.extend(data_buckets["khac"])
        labels.append("Tổng hợp")

    final_ctx = "\n".join(ctx_list)
    label_str = " + ".join(labels)

    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang suy luận từ {label_str}...*")
        reply = call_gemini_logic(prompt, final_ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
