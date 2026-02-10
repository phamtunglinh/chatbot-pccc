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
    page_title="Hệ thống Trợ lý PCCC (All-in-One)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
    }
    .header-title {font-size: 28px; font-weight: 900; text-transform: uppercase; margin: 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);}
    .header-subtitle {font-size: 14px; opacity: 0.9; margin-top: 5px;}
    .stChatInput {border-radius: 20px;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI HỆ THỐNG ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_string = st.secrets["GEMINI_API_KEYS"]
    else: keys_string = st.secrets["GEMINI_API_KEY"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình: {str(e)}"); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO TƯ DUY (SYSTEM INSTRUCTION) ---
# Kết hợp Logic Xử phạt của anh + Logic Karaoke/Trang bị mới
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế & Nghiệp vụ PCCC.

⚡ NGUYÊN TẮC VÀNG:
1. TUYỆT ĐỐI KHÔNG trả lời chung chung. Mọi thông số phải có trích dẫn (Văn bản, Bảng, Mục).
2. Dữ liệu QCVN 10 và Phụ lục NĐ 105 nằm trong các BẢNG BIỂU (Table). Hãy đọc kỹ.

-----------------------------------------------------
🟢 1. QUY TRÌNH TRẢ LỜI VỀ QUẢN LÝ / PHÂN CẤP (NĐ 105/2025):
   - Bước 1: Tìm cơ sở (Karaoke, Bar...) trong **PHỤ LỤC II** (Danh mục cơ sở nguy hiểm cháy nổ).
   - Bước 2: So sánh quy mô (Số tầng, Khối tích). 
     + Ví dụ: Karaoke >= 3 tầng HOẶC >= 1.000 m3 -> Thuộc Phụ lục II.
   - Bước 3: KẾT LUẬN: Do **Phòng Cảnh sát PCCC (PC07)** quản lý. (Không cần xét diện tích nếu đã đủ tầng).

-----------------------------------------------------
🔵 2. QUY TRÌNH TRẢ LỜI VỀ TRANG BỊ / KỸ THUẬT (QCVN 10:2025):
   - Bước 1: Tìm loại hình cơ sở trong các Bảng của QCVN 10.
   - Bước 2: Liệt kê các hệ thống bắt buộc (Báo cháy, Chữa cháy tự động, Cấp nước...).
   - Bước 3: Trích dẫn chính xác: "Theo Bảng..., Mục..., QCVN 10:2025/BCA".

-----------------------------------------------------
🔴 3. QUY TRÌNH TRẢ LỜI VỀ XỬ PHẠT (NĐ 144, 109, 106...):
   Thực hiện nghiêm ngặt 3 bước:
   
   BƯỚC 1: XÁC ĐỊNH MỨC PHẠT
   - Hành vi: ...
   - Mức phạt Cá nhân: ... -> Căn cứ: Điểm..., Khoản..., Điều...
   - Mức phạt Tổ chức: ... (Gấp 2 lần cá nhân).
   - Phạt bổ sung / Khắc phục hậu quả: ...

   BƯỚC 2: SÀNG LỌC THẨM QUYỀN (Theo NĐ 189 hoặc Luật XLVPHC)
   - So sánh mức phạt tối đa của hành vi với quyền hạn của chức danh.
   - LOẠI BỎ NGAY người không đủ tiền phạt hoặc không đủ quyền phạt bổ sung.

   BƯỚC 3: ĐỀ XUẤT
   - Trình [Chức danh thấp nhất đủ quyền] ra quyết định.
-----------------------------------------------------
"""

# --- 4. HÀM GỌI AI (Dùng Requests để ổn định hơn) ---
def call_gemini_direct(prompt, context):
    # Cắt bớt nếu quá dài nhưng giữ phần đầu (Mục lục) và phần đuôi (Bảng biểu Phụ lục)
    if len(context) > 100000: 
        context = context[:30000] + "\n...[Đoạn giữa]...\n" + context[-70000:]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (BAO GỒM CẢ BẢNG BIỂU):
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
    return "⚠️ Hệ thống đang bận. Vui lòng thử lại sau giây lát."

# --- 5. ĐỌC DỮ LIỆU (NÂNG CẤP: ĐỌC TABLE TRONG DOCX) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=80, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"nd_105": [], "xu_phat": [], "ky_thuat": [], "khac": []}
        file_count = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            # Cấm NĐ 136/50 (Chống nhiễu)
            if "136" in fname or "50" in fname: continue
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # --- XỬ LÝ DOCX (QUÉT SẠCH BẢNG BIỂU) ---
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    paras = [p.text for p in doc.paragraphs if p.text.strip()]
                    content += "\n".join(paras)
                    
                    # ĐỌC BẢNG (QUAN TRỌNG): Lấy dữ liệu Phụ lục & QCVN 10
                    tables_data = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                            tables_data.append(" | ".join(row_cells))
                    if tables_data:
                        content += "\n\n=== DỮ LIỆU BẢNG BIỂU ===\n" + "\n".join(tables_data)

                # --- XỬ LÝ PDF ---
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Đọc toàn bộ (để đảm bảo thấy Phụ lục cuối)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    if "105" in fname: data_store["nd_105"].append(item)
                    elif any(x in fname for x in ["144", "109", "106", "xu phat"]): data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["qc10", "10:2025", "ky thuat", "trang bi"]): data_store["ky_thuat"].append(item)
                    else: data_store["nd_105"].append(item)
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI PCCC & CNCH</p>
    <p class="header-subtitle">PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động hệ thống (Đọc Bảng biểu & Phân loại)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

# KHUNG CHÀO MỪNG
if "messages" not in st.session_state: st.session_state.messages = []
if len(st.session_state.messages) == 0:
    st.markdown("""
    <div style='background-color: #f8f9fa; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #eee;'>
        <p style='margin: 0;'>✅ <b>Hệ thống đã sẵn sàng:</b> Đã nạp {file_count} văn bản.</p>
        <p style='font-size: 13px; color: #666;'>Tích hợp logic: Xử phạt (3 bước) | Phân cấp (NĐ 105) | Trang bị (QCVN 10)</p>
    </div>
    """, unsafe_allow_html=True)

# Hiển thị lịch sử
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"):
        st.markdown(msg["content"])

# XỬ LÝ CÂU HỎI
if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # 1. PHÂN LOẠI CÂU HỎI & CHỌN DỮ LIỆU
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # Nhóm Trang bị (QCVN 10)
    if any(x in p for x in ["trang bị", "lắp đặt", "hệ thống", "báo cháy", "chữa cháy"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Kỹ thuật (QCVN 10)"
    # Nhóm Xử phạt
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nd_105"])
        label = "Xử phạt"
    # Nhóm Quản lý (NĐ 105)
    elif any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp", "karaoke"]):
        ctx = "\n".join(data_store["nd_105"])
        label = "Nghị định 105"
    else:
        ctx = "\n".join(data_store["nd_105"] + data_store["ky_thuat"])

    # 2. GỌI AI
    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⏳ *Đang tra cứu ({label})...*")
        
        reply = call_gemini_direct(prompt, ctx)
        
        # Format lại câu trả lời cho đẹp
        full_reply = reply + "\n\n---\n*Đại úy cần hỗ trợ thêm gì không?*"
        msg_ph.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
