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
st.set_page_config(page_title="Trợ lý PCCC (Nghiệp vụ Chuyên sâu)", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
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

# --- 3. BỘ NÃO NGHIỆP VỤ (HƯỚNG DẪN AI CÁCH XỬ LÝ KARAOKE) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC & CNCH.
NHIỆM VỤ: Trả lời câu hỏi nghiệp vụ chính xác dựa trên dữ liệu.

⚡ QUY TẮC XỬ LÝ QUAN TRỌNG:

1. ĐỐI VỚI CÂU HỎI VỀ "KARAOKE / VŨ TRƯỜNG":
   - Đây là cơ sở kinh doanh có điều kiện đặc biệt.
   - Để xác định AI QUẢN LÝ (Phân cấp), phải tìm trong "Phụ lục" của Nghị định 136/2020 hoặc Nghị định 50/2024 (Nếu có).
   - QUY TẮC "ƯU TIÊN CAO NHẤT": Chỉ cần cơ sở đạt 1 tiêu chí cao nhất là kết luận ngay.
     + Ví dụ: Karaoke cao >= 3 tầng HOẶC Khối tích >= 1.000 m3 -> Thuộc Phụ lục II -> Do Phòng Cảnh sát PCCC (PC07) quản lý.
     + Không cần xét diện tích nếu đã đủ số tầng.

2. ĐỐI VỚI CÂU HỎI VỀ "XỬ PHẠT":
   - Phải xác định rõ: Hành vi nào? -> Phạt bao nhiêu tiền? -> Ai có quyền ký?
   - Lưu ý: Thẩm quyền phạt của Trưởng phòng là tối đa 25 triệu (cá nhân)/50 triệu (tổ chức). Nếu mức phạt cao hơn phải đề xuất Giám đốc CA Tỉnh.

YÊU CẦU TRÌNH BÀY:
- Trả lời thẳng vào vấn đề.
- Trích dẫn văn bản pháp luật (Nghị định, Thông tư).
"""

# --- 4. HÀM GỌI AI ---
def call_gemini_logic(prompt, context):
    # Cắt ngắn context để tránh lỗi quá tải
    if len(context) > 35000: context = context[:35000] + "\n...(Đã lược bớt)..."

    full_prompt = f"DỮ LIỆU THAM KHẢO:\n{context}\n\nCÂU HỎI: {prompt}"
    
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
            
    return "⚠️ Hệ thống đang bận. Vui lòng thử lại câu hỏi ngắn hơn."

# --- 5. ĐỌC DỮ LIỆU (TÍNH NĂNG MỚI: ĐỌC ĐẦU + ĐUÔI VĂN BẢN) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=80, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        data_store = {"xu_phat": [], "phap_luat": [], "ky_thuat": [], "chua_chay": []}
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
                
                # XỬ LÝ PDF THÔNG MINH (ĐỌC ĐẦU + ĐUÔI ĐỂ LẤY PHỤ LỤC)
                if file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    num_pages = len(reader.pages)
                    # 1. Đọc 10 trang đầu (Điều khoản chung)
                    content += "\n".join([p.extract_text() for p in reader.pages[:10] if p.extract_text()])
                    # 2. Đọc 10 trang cuối (Nơi chứa PHỤ LỤC PHÂN CẤP)
                    if num_pages > 20:
                        content += "\n...[Nội dung giữa]...\n"
                        content += "\n".join([p.extract_text() for p in reader.pages[-10:] if p.extract_text()])
                
                elif file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if len(p.text) > 10])

                if content:
                    item = f"VĂN BẢN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    # PHÂN LOẠI
                    if any(x in fname for x in ["144", "109", "106", "189", "xu phat"]): data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "ky thuat"]): data_store["ky_thuat"].append(item)
                    elif any(x in fname for x in ["chua chay", "cnch"]): data_store["chua_chay"].append(item)
                    # Mặc định tất cả các file Nghị định, Thông tư còn lại vào Pháp luật
                    else: data_store["phap_luat"].append(item)
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ NGHIỆP VỤ PCCC</p><p>PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang nạp dữ liệu (Đã kích hoạt chế độ đọc Phụ lục)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ ĐÃ NẠP {file_count} VĂN BẢN (CHẾ ĐỘ ĐỌC PHỤ LỤC)"):
    st.info("Hệ thống đã đọc được trang đầu và trang cuối của văn bản để tìm Phụ lục phân cấp.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHỌN DỮ LIỆU THÔNG MINH (SỬA LỖI KARAOKE)
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. HỎI KARAOKE / QUẢN LÝ -> Bắt buộc lấy PHÁP LUẬT (Chứa NĐ 136/50)
    if any(x in p for x in ["karaoke", "vũ trường", "quản lý", "phân cấp", "thuộc diện"]):
        ctx = "\n".join(data_store["phap_luat"])
        # Nếu hỏi Karaoke thì lấy thêm kỹ thuật để check quy mô nếu cần
        if "karaoke" in p: ctx += "\n".join(data_store["ky_thuat"])
        label = "Pháp lý & Phân cấp"
        
    # 2. HỎI PHẠT -> Lấy Xử phạt + Pháp luật
    elif any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["phap_luat"])
        label = "Xử phạt"
        
    # 3. KỸ THUẬT -> Lấy Kỹ thuật
    elif any(x in p for x in ["kỹ thuật", "mét", "chiều cao", "bậc", "thang"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Quy chuẩn"
        
    else: ctx = "\n".join(data_store["phap_luat"])

    # GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang tra cứu ({label})...*")
        reply = call_gemini_logic(prompt, ctx)
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
