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
st.set_page_config(page_title="Trợ lý PCCC (Full QCVN 10)", page_icon="🔥", layout="wide", initial_sidebar_state="collapsed")
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

# --- 3. BỘ NÃO TƯ DUY (CHUYÊN GIA SOI QUY CHUẨN) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Thẩm duyệt & Nghiệm thu PCCC.

⚡ NHIỆM VỤ TỐI THƯỢNG:
Trả lời chính xác các yêu cầu về TRANG BỊ PHƯƠNG TIỆN PCCC cho công trình.

⚡ QUY TẮC TRA CỨU "QCVN 10:2025/BCA":
1. Dữ liệu QCVN 10 nằm trong các BẢNG BIỂU (Table). Bạn phải đọc kỹ từng hàng, từng cột.
2. Tìm dòng "Cơ sở kinh doanh dịch vụ karaoke".
3. Đối chiếu với cột quy mô (Ví dụ: Cao từ 3 tầng trở lên).
4. Xác định các dấu đánh dấu (x) hoặc quy định bắt buộc ở các cột hệ thống:
   - Báo cháy tự động? (Có/Không)
   - Chữa cháy tự động (Sprinkler)? (Có/Không)
   - Cấp nước chữa cháy (Vách tường/Ngoài nhà)?
   - Phương tiện ban đầu (Bình chữa cháy)?

⚡ YÊU CẦU TRẢ LỜI:
- KHẲNG ĐỊNH: "Cơ sở Karaoke 3 tầng BẮT BUỘC trang bị..."
- TRÍCH DẪN: "Căn cứ Mục..., Bảng..., QCVN 10:2025/BCA".
- NẾU HỎI QUẢN LÝ: Tra cứu Phụ lục II Nghị định 105/2025 (PC07 quản lý).
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    # CHẾ ĐỘ MAX CONTEXT: Không cắt bớt dữ liệu nữa. 
    # Gemini 1.5 Flash có thể đọc tới 1 triệu token (khoảng 700.000 từ), nên ta cứ gửi hết.
    
    full_prompt = f"""
    DỮ LIỆU VĂN BẢN (BAO GỒM TOÀN BỘ CÁC BẢNG QUY CHUẨN):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: 
    1. Tìm kỹ trong các Bảng của QCVN 10 (đối với câu hỏi trang bị).
    2. Tìm kỹ trong Phụ lục NĐ 105 (đối với câu hỏi quản lý).
    3. Trả lời chi tiết, liệt kê các hệ thống bắt buộc.
    """
    
    models = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"] # Ưu tiên 2.5 và Pro để đọc bảng tốt hơn
    
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
                # Tăng timeout lên 90 giây vì phải xử lý dữ liệu cực lớn
                response = requests.post(url, headers=headers, json=payload, timeout=90)
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code in [404, 429, 500, 503]: continue
            except: continue
    return "⚠️ Hệ thống đang bận xử lý khối lượng dữ liệu lớn. Vui lòng thử lại."

# --- 5. ĐỌC DỮ LIỆU (CÔNG NGHỆ QUÉT BẢNG BIỂU TOÀN DIỆN) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_full_scan():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=80, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"qcvn_10": [], "nd_105": [], "xu_phat": [], "khac": []}
        file_count = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            if "136" in fname or "50" in fname: continue # Bỏ file cũ
            
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
                    
                    # 1. Đọc văn bản thường
                    paras = [p.text for p in doc.paragraphs if p.text.strip()]
                    content += "\n".join(paras)
                    
                    # 2. Đọc Bảng (Table) - Nơi chứa QCVN 10
                    tables_data = []
                    for table in doc.tables:
                        for row in table.rows:
                            # Biến mỗi hàng thành chuỗi dạng: | Ô 1 | Ô 2 | Ô 3 |
                            row_cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                            tables_data.append(" | ".join(row_cells))
                    
                    if tables_data:
                        content += "\n\n=== DỮ LIỆU BẢNG BIỂU (QUAN TRỌNG) ===\n"
                        content += "\n".join(tables_data)

                # --- XỬ LÝ PDF (ĐỌC KHÔNG GIỚI HẠN) ---
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # ĐỌC TOÀN BỘ TRANG (Không cắt nữa)
                    content = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # Ưu tiên QCVN 10
                    if any(x in fname for x in ["qc10", "10:2025", "3890", "trang bi", "phuong tien"]): 
                        data_store["qcvn_10"].append(item)
                    elif any(x in fname for x in ["105", "nghi dinh"]):
                        data_store["nd_105"].append(item)
                    elif any(x in fname for x in ["144", "109", "106", "xu phat"]):
                        data_store["xu_phat"].append(item)
                    else:
                        data_store["khac"].append(item)
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🔥</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (FULL POWER)</p><p>CHẾ ĐỘ ĐỌC TOÀN VĂN & BẢNG BIỂU</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang quét toàn bộ dữ liệu (Quá trình này có thể mất 15-20 giây)...'):
    data_store, file_count = load_data_full_scan()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} VĂN BẢN (KHÔNG CẮT BỚT)"):
    if len(data_store['qcvn_10']) > 0:
        st.success(f"✅ Đã tìm thấy {len(data_store['qcvn_10'])} file Quy chuẩn kỹ thuật (QCVN 10).")
    else:
        st.warning("⚠️ Cảnh báo: Chưa thấy file nào tên là 'QCVN 10' hoặc 'Trang bị'. Hãy kiểm tra lại tên file trong Drive.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHIẾN THUẬT CHỌN TÀI LIỆU
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. TRANG BỊ / LẮP ĐẶT -> Dùng QCVN 10
    if any(x in p for x in ["trang bị", "lắp đặt", "hệ thống", "báo cháy", "chữa cháy", "phương tiện", "cần những gì"]):
        ctx = "\n".join(data_store["qcvn_10"]) 
        label = "QCVN 10:2025"
        
    # 2. QUẢN LÝ / PHÂN CẤP -> Dùng NĐ 105
    elif any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp"]):
        ctx = "\n".join(data_store["nd_105"])
        label = "Nghị định 105"
        
    # 3. PHẠT
    elif any(x in p for x in ["phạt", "tiền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nd_105"])
        label = "Xử phạt"
        
    else:
        # Nếu không rõ, gửi cả Luật và QC10 (Gemini Flash chịu tải tốt)
        ctx = "\n".join(data_store["nd_105"] + data_store["qcvn_10"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang soi bảng biểu trong {label}...*")
        reply = call_gemini_logic(prompt, ctx)
        
        # Nếu vẫn báo không có dữ liệu -> Gợi ý kiểm tra file
        if "không có nội dung" in reply.lower():
             reply += "\n\n⚠️ **Lưu ý:** Nếu Đại úy đã up file QCVN 10 nhưng tôi vẫn không đọc được, hãy chuyển file đó sang định dạng **Word (.docx)** và đảm bảo nội dung là **Bảng (Table)** chứ không phải ảnh chụp."
        
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
