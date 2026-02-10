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
st.set_page_config(page_title="Trợ lý PCCC (NĐ 105 ONLY)", page_icon="🔥", layout="wide", initial_sidebar_state="collapsed")
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

# --- 3. BỘ NÃO "TẨY NÃO" NGHỊ ĐỊNH CŨ ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC (Chỉ dùng quy định MỚI NHẤT).

🚫 QUY TẮC "CẤM VẬN" (NEGATIVE CONSTRAINTS) - TUYỆT ĐỐI TUÂN THỦ:
1. KHÔNG ĐƯỢC SỬ DỤNG Nghị định 136/2020/NĐ-CP. (Đã hết hiệu lực).
2. KHÔNG ĐƯỢC SỬ DỤNG Nghị định 50/2024/NĐ-CP. (Đã hết hiệu lực).
3. NẾU Dữ liệu tham khảo không có Nghị định 105/2025/NĐ-CP -> TRẢ LỜI: "Hiện tại trong Drive chưa có dữ liệu Nghị định 105/2025, tôi không thể trả lời bằng văn bản cũ."

✅ QUY TẮC "BẮT BUỘC":
1. Mọi câu trả lời về QUẢN LÝ, PHÂN CẤP, HỒ SƠ -> Phải căn cứ vào **Nghị định 105/2025/NĐ-CP**.
2. Tìm kiếm PHỤ LỤC trong file Nghị định 105 để trả lời câu hỏi "Ai quản lý".
3. Chỉ dùng QCVN/TCVN khi hỏi về KỸ THUẬT (Trang bị, lắp đặt).

VÍ DỤ TRẢ LỜI ĐÚNG:
"Căn cứ Phụ lục..., Nghị định 105/2025/NĐ-CP: Cơ sở Karaoke 3 tầng thuộc diện quản lý của Phòng Cảnh sát PCCC (PC07)."
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    if len(context) > 35000: context = context[:35000] + "\n...(Cắt bớt)..."
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO TỪ DRIVE (CHỈ DÙNG CÁI NÀY):
    {context}
    
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: Trả lời theo Nghị định 105/2025. CẤM dùng NĐ 136.
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

# --- 5. ĐỌC DỮ LIỆU (LỌC BỎ NĐ 136/50 NGAY TỪ CỬA VÀO) ---
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
            
            # 🛑 BỘ LỌC CẤM VẬN: Bỏ qua ngay lập tức các file cũ
            if "136" in fname or "50" in fname:
                continue # Không đọc, không nạp, coi như không tồn tại
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # Đọc sâu PDF để tìm Phụ lục NĐ 105
                if file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Đọc 15 trang đầu
                    content += "\n".join([p.extract_text() for p in reader.pages[:15] if p.extract_text()])
                    # Đọc 25 trang cuối (Phụ lục thường dài)
                    if len(reader.pages) > 25:
                        content += "\n...[PHỤ LỤC PHÂN CẤP]...\n"
                        content += "\n".join([p.extract_text() for p in reader.pages[-25:] if p.extract_text()])
                
                elif file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if len(p.text) > 10])

                if content:
                    # Gắn nhãn rõ ràng để AI biết đây là file gì
                    item = f"TÀI LIỆU: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # PHÂN LOẠI ƯU TIÊN 105
                    if "105" in fname:
                        data_store["nd_105"].append(item) # Nhóm VIP
                    elif any(x in fname for x in ["144", "109", "106", "189", "xu phat"]):
                        data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "ky thuat"]):
                        data_store["ky_thuat"].append(item)
                    else:
                        data_store["khac"].append(item)
                        
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🔥</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (NĐ 105/2025)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang nạp dữ liệu (Đã chặn NĐ 136/50)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} VĂN BẢN HIỆN HÀNH"):
    if len(data_store['nd_105']) > 0:
        st.success(f"✅ Đã tìm thấy {len(data_store['nd_105'])} file Nghị định 105/2025.")
    else:
        st.warning("⚠️ CẢNH BÁO: Chưa thấy file tên có chữ '105' trong Drive. AI có thể sẽ không trả lời được câu hỏi phân cấp.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHIẾN THUẬT CHỌN TÀI LIỆU (105 LÀ VUA)
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. HỎI QUẢN LÝ / PHÂN CẤP -> CHỈ ĐƯA NĐ 105 VÀO
    if any(x in p for x in ["quản lý", "ai", "thuộc diện", "phân cấp", "karaoke"]):
        ctx = "\n".join(data_store["nd_105"]) 
        if not ctx: ctx = "\n".join(data_store["khac"]) # Fallback nếu chưa up file 105
        label = "Nghị định 105/2025"
        
    # 2. HỎI PHẠT
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["nd_105"])
        label = "Xử phạt & NĐ 105"
        
    # 3. KỸ THUẬT
    elif any(x in p for x in ["trang bị", "lắp đặt", "kỹ thuật", "chiều cao"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Kỹ thuật"
        
    else:
        ctx = "\n".join(data_store["nd_105"] + data_store["khac"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu trong {label} (Tuyệt đối không dùng NĐ cũ)...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
