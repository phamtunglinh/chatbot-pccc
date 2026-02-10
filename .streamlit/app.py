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
st.set_page_config(page_title="Trợ lý PCCC (QCVN 10)", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
    .header-banner {background: linear-gradient(90deg, #b92b27 0%, #1565C0 100%); padding: 1.5rem; border-radius: 0 0 15px 15px; color: white; text-align: center; margin-top: -60px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);} 
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

# --- 3. BỘ NÃO NGHIỆP VỤ (ĐÃ CHỈNH LẠI TƯ DUY TRANG BỊ) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.

⚡ QUY TẮC NGHIỆP VỤ (BẮT BUỘC):

1. KHI HỎI VỀ "TRANG BỊ PHƯƠNG TIỆN / HỆ THỐNG PCCC" CHO CƠ SỞ:
   - ✅ BẮT BUỘC tra cứu: **QCVN 10:2025/BCA** (Quy chuẩn kỹ thuật quốc gia về trang bị phương tiện PCCC).
   - ⛔ KHÔNG ĐƯỢC DÙNG: Thông tư 36/2025/TT-BCA (Đây là trang bị cho Đội PCCC/Con người, không phải cho công trình).
   - ⛔ KHÔNG ĐƯỢC DÙNG: TCVN 3890 (Đã bị thay thế bởi QCVN 10, trừ khi dữ liệu QCVN 10 không có).

2. KHI HỎI VỀ "QUẢN LÝ / PHÂN CẤP":
   - Tra cứu Phụ lục II - Nghị định 105/2025/NĐ-CP.

3. VÍ DỤ TRẢ LỜI ĐÚNG VỀ TRANG BỊ (KARAOKE 3 TẦNG):
   - Phải nêu rõ: Cần hệ thống báo cháy tự động? Hệ thống chữa cháy tự động (Spinkler)? Bình chữa cháy? Đèn chỉ dẫn thoát nạn?...
   - Trích dẫn: "Theo Mục..., Bảng..., QCVN 10:2025/BCA...".
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    # Cắt bớt nếu quá dài nhưng giữ phần đầu (Mục lục) và phần bảng biểu (Nơi chứa quy định trang bị)
    if len(context) > 100000: 
        context = context[:20000] + "\n...[Đoạn giữa]...\n" + context[-80000:]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO TỪ DRIVE (ƯU TIÊN QCVN 10 CHO CÂU HỎI TRANG BỊ):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: 
    - Nếu hỏi trang bị: Tìm trong QCVN 10.
    - Nếu hỏi quản lý: Tìm trong NĐ 105.
    - Đọc kỹ các Bảng (Table).
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
    return "⚠️ Hệ thống bận."

# --- 5. ĐỌC DỮ LIỆU (PHÂN LOẠI KỸ HƠN) ---
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
            
            # Cấm NĐ 136/50
            if "136" in fname or "50" in fname: continue
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # --- XỬ LÝ DOCX (ĐỌC BẢNG ĐỂ LẤY QUY CHUẨN) ---
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    paras = [p.text for p in doc.paragraphs if p.text.strip()]
                    content += "\n".join(paras)
                    
                    # Đọc Bảng biểu (QCVN 10 và Phụ lục NĐ 105 toàn là bảng)
                    tables = []
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = [cell.text.strip() for cell in row.cells]
                            tables.append(" | ".join(row_text))
                    if tables:
                        content += "\n\n--- DỮ LIỆU BẢNG BIỂU ---\n" + "\n".join(tables)

                # --- XỬ LÝ PDF ---
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # PHÂN LOẠI CHÍNH XÁC
                    if "105" in fname: data_store["nd_105"].append(item)
                    elif any(x in fname for x in ["144", "109", "106", "xu phat"]): data_store["xu_phat"].append(item)
                    
                    # Nhóm Kỹ thuật: Ưu tiên QC 10, TCVN 3890, QCVN 06
                    elif any(x in fname for x in ["qc10", "10:2025", "3890", "06:2022", "ky thuat", "trang bi"]): 
                        data_store["ky_thuat"].append(item)
                    
                    else: data_store["nd_105"].append(item)
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (CHUẨN QCVN 10)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang đọc văn bản & Bảng biểu kỹ thuật...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} TÀI LIỆU"):
    st.info("Hệ thống đã tách biệt: Trang bị (QCVN 10) và Quản lý (NĐ 105).")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHIẾN THUẬT CHỌN TÀI LIỆU (TÁCH BIỆT RÕ RÀNG)
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. TRANG BỊ / LẮP ĐẶT -> BẮT BUỘC DÙNG KỸ THUẬT (QCVN 10)
    if any(x in p for x in ["trang bị", "lắp đặt", "bình chữa cháy", "báo cháy", "họng nước", "spinkler", "phương tiện"]):
        ctx = "\n".join(data_store["ky_thuat"]) 
        label = "Kỹ thuật (QCVN 10)"
        
    # 2. QUẢN LÝ / PHÂN CẤP -> NĐ 105
    elif any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp"]):
        ctx = "\n".join(data_store["nd_105"])
        label = "Nghị định 105"
        
    # 3. PHẠT -> Xử phạt
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nd_105"])
        label = "Xử phạt"
        
    else:
        ctx = "\n".join(data_store["nd_105"] + data_store["ky_thuat"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu trong {label}...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
