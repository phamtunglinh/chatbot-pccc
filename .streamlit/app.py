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
    page_title="Hệ thống Trợ lý PCCC (Nghiệp vụ Chuyên sâu)",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #b92b27 0%, #1565C0 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình Secrets: {str(e)}"); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO NGHIỆP VỤ (ĐÃ NÂNG CẤP LOGIC KARAOKE) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Bạn là Đại úy Phạm Tùng Linh - Chuyên gia Xử lý nghiệp vụ PCCC & CNCH.
NHIỆM VỤ: Trả lời câu hỏi dựa trên DỮ LIỆU ĐƯỢC CUNG CẤP.

⚡ QUY TẮC TƯ DUY NGHIỆP VỤ (BẮT BUỘC ÁP DỤNG):

🔵 1. THUẬT TOÁN PHÂN CẤP QUẢN LÝ (Ai quản lý?):
   - NGUYÊN TẮC "CHỐT HẠ": Chỉ cần cơ sở thỏa mãn 01 điều kiện cao nhất là KẾT LUẬN NGAY. (Ví dụ: Đã đủ số tầng thì không cần xét diện tích/khối tích nữa).
   - Ví dụ cụ thể: Karaoke cao >= 3 tầng -> Kết luận ngay thuộc Phụ lục II (Do PC07 quản lý). Không nói "nếu... thì...".
   - Quy trình:
     + B1: So sánh Số tầng của cơ sở với Phụ lục trong dữ liệu (NĐ 50 hoặc NĐ 136/105).
     + B2: Nếu Số tầng đạt -> Kết luận luôn. Nếu chưa đạt -> So tiếp Khối tích/Diện tích.
     + B3: Kết luận thẩm quyền (PC07 hay Công an Huyện/UBND Xã).

🔴 2. THUẬT TOÁN XỬ PHẠT (Lỗi này phạt bao nhiêu? Ai ký?):
   - B1: Tìm hành vi trong NĐ 144/109/106.
   - B2: Xác định khung tiền phạt (Cá nhân & Tổ chức).
   - B3: SÀNG LỌC THẨM QUYỀN (Rất quan trọng):
     + So sánh mức phạt tối đa của hành vi với thẩm quyền của: Chiến sĩ -> Đội trưởng -> Trưởng phòng -> Giám đốc CA Tỉnh -> Chủ tịch UBND.
     + CHỌN NGƯỜI CÓ THẨM QUYỀN THẤP NHẤT NHƯNG ĐỦ QUYỀN PHẠT.
     + Ví dụ: Lỗi phạt 40 triệu -> Trưởng phòng (max 25tr) không ký được -> Phải đề xuất Giám đốc CA Tỉnh.

🟢 3. HỒ SƠ / THỦ TỤC:
   - Ưu tiên tìm trong NĐ 105/2025 hoặc NĐ 136. Trả lời chính xác danh mục hồ sơ.

YÊU CẦU TRÌNH BÀY:
- Ngắn gọn, dứt khoát. Không giải thích dông dài.
- Trích dẫn: "Theo Khoản..., Điều..., Văn bản...".
"""

# --- 4. HÀM GỌI AI (FIX LỖI QUÁ TẢI) ---
def call_gemini_logic(prompt, context):
    # GIỚI HẠN DỮ LIỆU: Chỉ lấy 30.000 ký tự đầu tiên để tránh lỗi quá tải
    if len(context) > 30000:
        context = context[:30000] + "\n...(Đã lược bớt văn bản cũ)..."

    full_prompt = f"""
    DỮ LIỆU (CONTEXT):
    {context}
    
    CÂU HỎI:
    {prompt}
    """
    
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    for attempt in range(3): # Thử 3 lần
        api_key = get_random_key()
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {'Content-Type': 'application/json'}
            
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "system_instruction": {"parts": [{"text": ALGORITHMS_INSTRUCTION}]},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                ]
            }

            try:
                # Timeout ngắn (30s) để fail nhanh còn thử cái khác
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    try: return response.json()['candidates'][0]['content']['parts'][0]['text']
                    except: continue
                elif response.status_code == 429: # Quá tải
                    time.sleep(2); continue
                elif response.status_code == 404: # Model không có
                    continue
                else: continue
            except: continue
            
    return "⚠️ Hệ thống đang quá tải hoặc dữ liệu quá lớn. Đại úy vui lòng hỏi ngắn gọn lại hoặc thử lại sau 1 phút."

# --- 5. ĐỌC DỮ LIỆU (TỐI ƯU HÓA) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=80, fields="files(id, name, mimeType)").execute() # Giảm xuống 80 file
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
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    # Chỉ lấy văn bản, bỏ qua bảng biểu phức tạp để nhẹ gánh
                    content = "\n".join([p.text for p in doc.paragraphs if len(p.text) > 5])
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # CHỈ ĐỌC 15 TRANG ĐẦU MỖI FILE (Để tránh lỗi quá tải)
                    content = "\n".join([p.extract_text() for p in reader.pages[:15] if p.extract_text()])
                
                if content:
                    item = f"VB: {file['name']}\nND:\n{content}\n---\n"
                    
                    if any(x in fname for x in ["144", "109", "106", "189", "xu phat"]):
                        data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "3890"]):
                        data_store["ky_thuat"].append(item)
                    elif any(x in fname for x in ["chua chay", "cnch"]):
                        data_store["chua_chay"].append(item)
                    else:
                        data_store["phap_luat"].append(item)
                    
                    file_count += 1
            except: continue
        return data_store, file_count
    except Exception as e: return None, str(e)

# --- GIAO DIỆN ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🛡️</div>
    <p style="font-size: 24px; font-weight: 900; margin: 0;">TRỢ LÝ NGHIỆP VỤ PCCC</p>
    <p style="font-size: 14px;">PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi tạo bộ não nghiệp vụ (V2)...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ TRẠNG THÁI: {file_count} VĂN BẢN (ĐÃ TỐI ƯU DUNG LƯỢNG)"):
    st.info("Đã kích hoạt chế độ: 'Chốt phương án' & 'Sàng lọc quá tải'.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # CHỌN DỮ LIỆU THÔNG MINH
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    # 1. Nếu hỏi Phạt (cần cả Luật để tra thẩm quyền)
    if any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký"]):
        ctx = "\n".join(data_store["xu_phat"] + data_store["phap_luat"])
        label = "Xử phạt & Thẩm quyền"
    
    # 2. Nếu hỏi Phân cấp/Quản lý (cần Luật)
    elif any(x in p for x in ["quản lý", "phân cấp", "karaoke", "nhà hàng"]):
        ctx = "\n".join(data_store["phap_luat"])
        label = "Phân cấp quản lý"
        
    # 3. Kỹ thuật
    elif any(x in p for x in ["kỹ thuật", "mét", "chiều cao"]):
        ctx = "\n".join(data_store["ky_thuat"])
        label = "Quy chuẩn"
        
    else: # Mặc định lấy Luật
        ctx = "\n".join(data_store["phap_luat"])

    # 4. GỌI AI
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang xử lý ({label})...*")
        
        reply = call_gemini_logic(prompt, ctx)
        
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
