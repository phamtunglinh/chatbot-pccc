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
st.set_page_config(page_title="Trợ lý PCCC (Chỉ đọc Drive)", page_icon="🔒", layout="wide", initial_sidebar_state="collapsed")
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

# --- 3. BỘ NÃO KỶ LUẬT SẮT (STRICT GROUNDING) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Bạn là Cỗ máy trích xuất thông tin văn bản.
BẠN KHÔNG PHẢI LÀ LUẬT SƯ, BẠN CHỈ LÀ NGƯỜI ĐỌC VĂN BẢN.

🛑 QUY TẮC BẤT DI BẤT DỊCH (VI PHẠM SẼ BỊ KHÓA):
1. CHỈ ĐƯỢC sử dụng thông tin có trong phần "DỮ LIỆU THAM KHẢO" bên dưới.
2. TUYỆT ĐỐI KHÔNG sử dụng kiến thức được huấn luyện từ trước (như NĐ 136 cũ, NĐ 79 cũ...). Nếu Dữ liệu tham khảo không có, hãy trả lời: "Tài liệu trong Drive chưa cập nhật thông tin này".
3. TRÍCH DẪN NGUỒN: Mọi câu trả lời bắt buộc phải ghi rõ lấy từ file nào. Ví dụ: (Trích từ file: Nghi_dinh_105.pdf).
4. ƯU TIÊN NGHỊ ĐỊNH 105: Nếu thấy thông tin mâu thuẫn, BẮT BUỘC lấy theo Nghị định 105/2025/NĐ-CP có trong dữ liệu.

⚡ XỬ LÝ CÂU HỎI:
- Nếu hỏi "Ai quản lý/Phân cấp": Tìm Phụ lục trong file NĐ 105/2025 hoặc NĐ 50/2024.
- Nếu hỏi "Phạt": Tìm trong file NĐ 144/109/106.
- Nếu hỏi "Trang bị": Tìm trong file QCVN/TCVN.
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    if len(context) > 35000: context = context[:35000] + "\n...(Cắt bớt để tránh lỗi)..."
    
    # Prompt ép buộc trích xuất
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO TỪ DRIVE (CHỈ ĐƯỢC DÙNG CÁI NÀY):
    {context}
    
    ---------------------------------------------------
    CÂU HỎI: "{prompt}"
    
    YÊU CẦU: Trả lời chính xác dựa trên dữ liệu trên. Ghi rõ nguồn file. Nếu không thấy trong dữ liệu trên thì nói không biết.
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
    return "⚠️ Hệ thống bận. Vui lòng thử lại."

# --- 5. ĐỌC DỮ LIỆU (ĐỌC KỸ PHỤ LỤC) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=80, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"xu_phat": [], "phap_luat": [], "ky_thuat": []}
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
                
                # CHẾ ĐỘ QUÉT FILE (QUAN TRỌNG: LẤY TÊN FILE ĐỂ TRÍCH DẪN)
                prefix = f"[[NGUỒN FILE: {file['name']}]]\n" 
                
                if file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Lấy 15 trang đầu (Luật) + 20 trang cuối (Phụ lục)
                    content += "\n".join([p.extract_text() for p in reader.pages[:15] if p.extract_text()])
                    if len(reader.pages) > 20:
                        content += "\n...[PHỤ LỤC]...\n"
                        content += "\n".join([p.extract_text() for p in reader.pages[-20:] if p.extract_text()])
                
                elif file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if len(p.text) > 10])

                if content:
                    item = prefix + content + "\n---\n"
                    
                    if any(x in fname for x in ["144", "109", "106", "189", "xu phat"]): data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "ky thuat", "trang bi"]): data_store["ky_thuat"].append(item)
                    # Gom hết NĐ 105, 136, 50, Hồ sơ vào Pháp luật
                    else: data_store["phap_luat"].append(item)
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🔒</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (CHẾ ĐỘ CHỈ ĐỌC DRIVE)</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang quét Drive...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Không đọc được dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} TÀI LIỆU (CHẾ ĐỘ CHẶT CHẼ)"):
    st.info("Hệ thống đã được thiết lập để CHỈ TRẢ LỜI nội dung có trong file. Nếu không có file NĐ 105, hệ thống sẽ báo không biết.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHỌN TÀI LIỆU
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. KỸ THUẬT (Chỉ khi hỏi trang bị/lắp đặt/quy chuẩn)
    if any(x in p for x in ["trang bị", "lắp đặt", "khoảng cách", "chiều cao", "bậc chịu lửa", "lối thoát"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Kỹ thuật (QCVN/TCVN)"
        
    # 2. XỬ PHẠT (Cần cả Luật để đối chiếu)
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["phap_luat"])
        label = "Xử phạt"
        
    # 3. QUẢN LÝ / HỒ SƠ (Chỉ lấy Pháp luật)
    else:
        ctx = "\n".join(data_store["phap_luat"])
        label = "Pháp lý (NĐ 105/136)"

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang quét file trong Drive ({label})...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
