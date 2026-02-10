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
st.set_page_config(page_title="Trợ lý PCCC (Full Context)", page_icon="🔥", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #b92b27 0%, #1565C0 100%); padding: 1.5rem; border-radius: 0 0 15px 15px; color: white; text-align: center; margin-top: -60px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);} .stChatInput {border-radius: 20px;}</style>""", unsafe_allow_html=True)

# --- 2. KẾT NỐI KEY & DRIVE ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_string = st.secrets["GEMINI_API_KEYS"]
    else: keys_string = st.secrets["GEMINI_API_KEY"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("⚠️ Lỗi cấu hình Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO TƯ DUY (ĐÃ CẬP NHẬT LOGIC PHỤ LỤC II) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC.

⚡ QUY TẮC "PHÂN CẤP QUẢN LÝ" (QUAN TRỌNG):

1. ĐỐI TƯỢNG: Khi hỏi về Karaoke, Vũ trường, Bar, Khách sạn, Nhà cao tầng...
2. CĂN CỨ: Phải tìm trong **PHỤ LỤC II** (Danh mục cơ sở có nguy hiểm về cháy, nổ) của Nghị định 105/2025/NĐ-CP (hoặc NĐ 50/2024).
3. LOGIC KẾT LUẬN:
   - Nếu cơ sở có tên trong **Phụ lục II** -> Thuộc thẩm quyền quản lý của **Phòng Cảnh sát PCCC & CNCH (PC07)**.
   - Ví dụ: Karaoke cao từ 3 tầng trở lên HOẶC khối tích từ 1.000 m3 trở lên -> Nằm trong Phụ lục II -> PC07 quản lý.
   - Không trả lời chung chung kiểu "Cơ quan Công an quản lý". Phải chỉ rõ là PC07 hay Công an Huyện.

⚡ QUY TẮC "CẤM VẬN":
- KHÔNG DÙNG NĐ 136/2020 (Đã hết hiệu lực về phân cấp).
- Nếu không tìm thấy file NĐ 105, hãy báo cáo trung thực.
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    # Gemini Flash chịu được 1 triệu token, nên ta có thể gửi nhiều dữ liệu hơn.
    # Tuy nhiên vẫn giới hạn 100.000 ký tự để đảm bảo tốc độ phản hồi nhanh.
    if len(context) > 100000: context = context[:100000] + "\n...(Đã cắt bớt phần thừa)..."
    
    full_prompt = f"""
    DỮ LIỆU VĂN BẢN (TOÀN VĂN):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU:
    - Kiểm tra kỹ PHỤ LỤC II trong dữ liệu trên.
    - Trả lời ngắn gọn, chính xác thẩm quyền quản lý.
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
                # Tăng timeout lên 60s vì gửi nhiều dữ liệu hơn
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code in [404, 429, 500, 503]: continue
            except: continue
    return "⚠️ Hệ thống bận hoặc xử lý quá lâu."

# --- 5. ĐỌC DỮ LIỆU (CHẾ ĐỘ FULL TEXT - KHÔNG BỎ SÓT) ---
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
                
                # --- NÂNG CẤP: ĐỌC TOÀN BỘ FILE (FULL READ) ---
                if file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Đọc TOÀN BỘ các trang (Không giới hạn nữa)
                    # Để tránh lỗi memory với file quá lớn (>100 trang), ta giới hạn 100 trang đầu
                    # Vì Phụ lục thường nằm trong khoảng trang 1-100 của Nghị định.
                    content = "\n".join([p.extract_text() for p in reader.pages[:100] if p.extract_text()])
                
                elif file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs]) # Đọc hết

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    if "105" in fname: data_store["nd_105"].append(item)
                    elif any(x in fname for x in ["144", "109", "106", "xu phat"]): data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "ky thuat"]): data_store["ky_thuat"].append(item)
                    else: data_store["nd_105"].append(item) # Gom các file luật khác vào chung nhóm
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🔥</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (FULL CONTEXT)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang đọc toàn bộ văn bản (Chế độ Full)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} VĂN BẢN (ĐỌC SÂU)"):
    st.info("Hệ thống đã đọc toàn bộ nội dung file (bao gồm cả Phụ lục ở cuối).")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHỌN TÀI LIỆU
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. QUẢN LÝ / PHÂN CẤP -> NĐ 105
    if any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp", "karaoke"]):
        ctx = "\n".join(data_store["nd_105"]) 
        label = "Nghị định 105 (Phụ lục)"
        
    # 2. PHẠT -> Xử phạt + NĐ 105
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nd_105"])
        label = "Xử phạt"
        
    # 3. KỸ THUẬT -> Kỹ thuật
    elif any(x in p for x in ["trang bị", "lắp đặt", "kỹ thuật"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Kỹ thuật"
        
    else:
        ctx = "\n".join(data_store["nd_105"] + data_store["khac"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu kỹ Phụ lục trong {label}...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
