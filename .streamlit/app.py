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
st.set_page_config(page_title="Trợ lý Nghiệp vụ PCCC", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
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

# --- 3. BỘ NÃO TƯ DUY NGHIỆP VỤ (HƯỚNG DẪN CỤ THỂ) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC.
NHIỆM VỤ: Trả lời câu hỏi về THẨM QUYỀN QUẢN LÝ và XỬ PHẠT.

⚡ QUY TẮC "BẮT BUỘC" (STRICT RULES):

1. KHI HỎI "AI QUẢN LÝ / CƠ SỞ THUỘC DIỆN NÀO":
   - ⛔ KHÔNG ĐƯỢC trả lời chung chung theo Luật PCCC (kiểu "Bộ Công an quản lý", "UBND quản lý").
   - ✅ PHẢI TÌM TRONG "PHỤ LỤC" CỦA NGHỊ ĐỊNH (Ưu tiên NĐ 105/2025, NĐ 50/2024, NĐ 136/2020).
   - TƯ DUY PHÂN CẤP:
     + Tìm xem cơ sở (Ví dụ: Karaoke 3 tầng) nằm ở Phụ lục mấy? (Phụ lục I, II, III hay IV).
     + Nếu thuộc Phụ lục II -> Do Phòng Cảnh sát PCCC (PC07) quản lý.
     + Nếu thuộc Phụ lục III -> Do Công an cấp Huyện quản lý.
     + Nếu thuộc Phụ lục IV -> Do UBND cấp Xã quản lý.
   - TRẢ LỜI: "Cơ sở Karaoke 3 tầng thuộc Mục..., Phụ lục..., Nghị định... -> Do [Cơ quan] quản lý."

2. KHI HỎI VỀ "KARAOKE":
   - Chỉ cần CAO TỪ 3 TẦNG TRỞ LÊN hoặc KHỐI TÍCH TỪ 1.000 M3 -> Là thuộc diện quản lý của Cơ quan Công an cấp Tỉnh (PC07) theo Phụ lục II. (Không cần xét diện tích).

3. TRÍCH DẪN NGUỒN:
   - Phải ghi rõ thông tin lấy từ file nào trong Drive.
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    if len(context) > 35000: context = context[:35000] + "\n...(Cắt bớt)..."
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO TỪ DRIVE:
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: Áp dụng quy tắc Phân cấp quản lý. Không trả lời lý thuyết Luật chung.
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
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code in [404, 429, 500, 503]: continue
            except: continue
    return "⚠️ Hệ thống bận."

# --- 5. ĐỌC DỮ LIỆU (LỌC FILE THÔNG MINH) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=80, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"nghi_dinh": [], "luat_chung": [], "ky_thuat": [], "xu_phat": []}
        file_count = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # CHẾ ĐỘ ĐỌC MẠNH MẼ HƠN CHO DOCX (Để tìm Phụ lục)
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    # Đọc toàn bộ văn bản (DOCX thường nhẹ hơn PDF nên đọc hết được)
                    content = "\n".join([p.text for p in doc.paragraphs if len(p.text) > 5])
                
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Đọc 10 trang đầu + 20 trang cuối (Chứa Phụ lục)
                    content += "\n".join([p.extract_text() for p in reader.pages[:10] if p.extract_text()])
                    if len(reader.pages) > 20:
                        content += "\n...[PHỤ LỤC PHÂN CẤP]...\n"
                        content += "\n".join([p.extract_text() for p in reader.pages[-20:] if p.extract_text()])

                if content:
                    item = f"NGUỒN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # PHÂN LOẠI CHÍNH XÁC:
                    if any(x in fname for x in ["nghi dinh", "136", "50", "105", "nd-cp"]):
                        data_store["nghi_dinh"].append(item) # QUAN TRỌNG NHẤT
                    elif any(x in fname for x in ["luat", "quoc hoi"]):
                        data_store["luat_chung"].append(item) # Ít quan trọng hơn khi hỏi về chi tiết
                    elif any(x in fname for x in ["144", "109", "106", "xu phat"]):
                        data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["qcvn", "tcvn", "ky thuat"]):
                        data_store["ky_thuat"].append(item)
                    else:
                        data_store["nghi_dinh"].append(item)
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (ƯU TIÊN NGHỊ ĐỊNH)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang nạp dữ liệu (Chế độ đọc sâu Nghị định)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} VĂN BẢN"):
    st.write(f"- Nghị định (Phân cấp): {len(data_store['nghi_dinh'])} file")
    st.write(f"- Luật chung: {len(data_store['luat_chung'])} file")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHIẾN THUẬT CHỌN TÀI LIỆU (FIX LỖI CỦA ĐẠI ÚY)
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. HỎI "AI QUẢN LÝ / PHÂN CẤP":
    # -> BỎ QUA LUẬT CHUNG. CHỈ ĐỌC NGHỊ ĐỊNH.
    if any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp"]):
        ctx = "\n".join(data_store["nghi_dinh"]) # Chỉ đưa Nghị định vào để tránh bị Luật làm nhiễu
        label = "Nghị định (Phân cấp)"
        
    # 2. HỎI PHẠT:
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nghi_dinh"])
        label = "Xử phạt"
        
    # 3. KỸ THUẬT:
    elif any(x in p for x in ["trang bị", "lắp đặt", "kỹ thuật", "chiều cao"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Kỹ thuật"
        
    else:
        ctx = "\n".join(data_store["nghi_dinh"] + data_store["luat_chung"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu trong {label} (Bỏ qua Luật chung)...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
