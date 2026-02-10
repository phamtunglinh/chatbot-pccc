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
    page_title="Hệ thống Trợ lý PCCC (Master)",
    page_icon="🔥",
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
    .css-1aumxhk {text-align: left;}
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

# --- 3. BỘ NÃO TỔNG HỢP (MASTER INSTRUCTION) ---
# Kết hợp cả 3 luồng tư duy: Quản lý (105) + Kỹ thuật (QC10) + Xử phạt (106/189)
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC & CNCH.

⚡ NGUYÊN TẮC CỐT LÕI:
1. Dữ liệu quan trọng (Phụ lục, Quy chuẩn) nằm trong các BẢNG BIỂU (Table). Hãy đọc kỹ.
2. KHÔNG DÙNG văn bản cũ (NĐ 136, NĐ 50, TCVN 3890).

⚡ QUY TRÌNH XỬ LÝ THEO TỪNG LOẠI CÂU HỎI:

🔵 1. HỎI VỀ "QUẢN LÝ / PHÂN CẤP" (Karaoke, Bar, Khách sạn...):
   - Căn cứ: **Nghị định 105/2025/NĐ-CP** (Tra cứu Phụ lục I, II).
   - Logic: 
     + Tìm cơ sở trong **Phụ lục II** (Cơ sở nguy hiểm cháy nổ).
     + Ví dụ: Karaoke >= 3 tầng (hoặc >= 1.000 m3) -> Thuộc Phụ lục II -> **Phòng PC07 quản lý**.
     + Nếu không thuộc Phụ lục II -> Công an Huyện hoặc UBND Xã.

🟢 2. HỎI VỀ "TRANG BỊ / KỸ THUẬT" (Lắp hệ thống gì?):
   - Căn cứ: **QCVN 10:2025/BCA**.
   - Cách trả lời: Tra cứu Bảng quy định trong QCVN 10. Liệt kê các hệ thống bắt buộc (Báo cháy, Chữa cháy tự động, Cấp nước...).
   - Tuyệt đối không dùng Thông tư 36 (trang bị cho người) để trả lời cho công trình.

🔴 3. HỎI VỀ "XỬ PHẠT" (Phạt bao nhiêu? Ai ký?):
   - Căn cứ Mức phạt: **Nghị định 106**.
   - Căn cứ Thẩm quyền: **Nghị định 189**.
   - Quy trình:
     + B1: Xác định mức phạt tiền (Cá nhân & Tổ chức).
     + B2: So sánh với thẩm quyền (Chiến sĩ -> Đội trưởng -> Trưởng phòng -> Giám đốc -> Chủ tịch).
     + B3: Kết luận người có thẩm quyền thấp nhất đủ điều kiện ký quyết định.

YÊU CẦU: Trả lời ngắn gọn, trích dẫn rõ ràng (Văn bản, Bảng, Khoản, Điều).
"""

# --- 4. HÀM GỌI AI (Dùng Requests ổn định) ---
def call_gemini_master(prompt, context):
    # Cắt context thông minh: Giữ đầu (Mục lục) và Đuôi (Phụ lục/Bảng biểu)
    if len(context) > 100000: 
        context = context[:30000] + "\n...[Lược bớt phần giữa]...\n" + context[-70000:]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (BAO GỒM CẢ BẢNG BIỂU & PHỤ LỤC):
    {context}
    
    CÂU HỎI: "{prompt}"
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
    return "⚠️ Hệ thống đang bận. Vui lòng thử lại."

# --- 5. ĐỌC DỮ LIỆU (QUÉT SẠCH BẢNG BIỂU & PHÂN LOẠI) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_master():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        # 4 NGĂN TỦ DỮ LIỆU RIÊNG BIỆT
        data_store = {
            "nd_105": [],    # Quản lý, Hồ sơ (NĐ 105)
            "nd_106_189": [],# Xử phạt, Thẩm quyền (NĐ 106, 189)
            "qcvn_10": [],   # Kỹ thuật, Trang bị (QCVN 10)
            "khac": []       # Các văn bản khác
        }
        
        log_files = [] # Để hiển thị trạng thái
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            # 🛑 CHẶN FILE CŨ (136, 50)
            if "136" in fname or "50" in fname: continue
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # --- XỬ LÝ DOCX (QUÉT BẢNG BIỂU - QUAN TRỌNG) ---
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    # 1. Đọc văn bản thường
                    content += "\n".join([p.text for p in doc.paragraphs])
                    # 2. Đọc Bảng biểu (Phụ lục & QCVN)
                    tables = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                            tables.append(" | ".join(row_text))
                    if tables:
                        content += "\n\n=== DỮ LIỆU BẢNG (TABLE) ===\n" + "\n".join(tables)

                # --- XỬ LÝ PDF (ĐỌC TOÀN BỘ) ---
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # --- PHÂN LOẠI THÔNG MINH ---
                    if "105" in fname:
                        data_store["nd_105"].append(item)
                        log_files.append(f"🔹 {file['name']} (Quản lý)")
                    elif any(x in fname for x in ["106", "189", "144", "xu phat"]):
                        data_store["nd_106_189"].append(item)
                        log_files.append(f"⚖️ {file['name']} (Xử phạt)")
                    elif any(x in fname for x in ["qc10", "10:2025", "trang bi", "ky thuat"]):
                        data_store["qcvn_10"].append(item)
                        log_files.append(f"🛠️ {file['name']} (Kỹ thuật)")
                    else:
                        data_store["khac"].append(item)
                        
            except: continue
        return data_store, log_files
    except Exception as e: return None, [str(e)]

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🔥</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (MASTER)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động hệ thống tổng hợp (Đọc Bảng + Phân loại)...'):
    data_store, logs = load_data_master()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

# SIDEBAR: HIỂN THỊ TRẠNG THÁI FILE
with st.sidebar:
    st.header("📂 DỮ LIỆU ĐÃ NẠP")
    if logs:
        for log in logs: st.text(log)
    else: st.warning("Chưa có file nào hợp lệ.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHIẾN THUẬT CHỌN DỮ LIỆU (SM
