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

# --- 3. BỘ NÃO NGHIỆP VỤ (SYSTEM INSTRUCTION) ---
# Đây là phần quan trọng nhất: Chứa 3 thuật toán tư duy anh yêu cầu
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Bạn là Đại úy Phạm Tùng Linh - Chuyên gia Xử lý nghiệp vụ PCCC & CNCH.
NHIỆM VỤ: Trả lời câu hỏi dựa trên DỮ LIỆU ĐƯỢC CUNG CẤP (Context).

⚡ CÁC THUẬT TOÁN TƯ DUY BẮT BUỘC PHẢI ÁP DỤNG KHI TRẢ LỜI:

🔵 1. KHI HỎI VỀ PHÂN CẤP QUẢN LÝ (Ai quản lý? Thuộc phụ lục nào?):
   - Bước 1: Xác định công năng chính (Nếu 1 công năng > 70% diện tích -> Công năng chính. Nếu không -> Hỗn hợp).
   - Bước 2: Tìm kiếm Phụ lục phân cấp (Phụ lục I, II, III, IV...) trong Nghị định 136 hoặc Nghị định 50 có trong dữ liệu.
   - Bước 3: Đối chiếu thông số (Số tầng, Khối tích m3) của cơ sở với Phụ lục tìm được.
   - Bước 4: Kết luận: Cơ sở thuộc Phụ lục mấy? Do Công an cấp Tỉnh (PC07) hay Công an cấp Huyện quản lý?

🔴 2. KHI HỎI VỀ XỬ PHẠT (Lỗi này phạt bao nhiêu? Ai ký quyết định?):
   - Bước 1: Tìm hành vi trong Nghị định xử phạt (NĐ 144, NĐ 106...) có trong dữ liệu.
   - Bước 2: Xác định Khung tiền phạt (Lưu ý: Phạt Tổ chức = 2 lần Phạt Cá nhân). Xác định Phạt bổ sung (Tạm đình chỉ, Tịch thu...) và Biện pháp khắc phục hậu quả.
   - Bước 3: SÀNG LỌC THẨM QUYỀN (Dựa trên NĐ 189 hoặc Luật XLVPHC):
     + Loại bỏ ngay người có Thẩm quyền phạt tiền tối đa < Mức phạt của hành vi này.
     + Loại bỏ người không có quyền áp dụng hình thức phạt bổ sung (nếu hành vi đó có phạt bổ sung).
   - Bước 4: ĐỀ XUẤT: Chọn người có thẩm quyền thấp nhất nhưng đủ quyền hạn để ký quyết định.

🟢 3. KHI HỎI VỀ HỒ SƠ / THỦ TỤC:
   - Ưu tiên số 1: Tìm kiếm trong **Nghị định 105/2025/NĐ-CP** (nếu có trong dữ liệu).
   - Ưu tiên số 2: Nếu không có NĐ 105 mới tìm trong NĐ 136/2020.
   - Tuyệt đối không tự bịa ra danh mục hồ sơ. Không lấy danh mục hồ sơ từ văn bản xử phạt.

YÊU CẦU TRÌNH BÀY:
- Trích dẫn rõ ràng: "Theo Khoản..., Điều..., Văn bản...".
- Văn phong: Quân sự, dứt khoát, chính xác.
- Nếu dữ liệu không có thông tin: Trả lời "Trong các văn bản hiện có chưa cập nhật nội dung này."
"""

# --- 4. HÀM GỌI AI TRỰC TIẾP (DIRECT API) ---
def call_gemini_logic(prompt, context):
    api_key = get_random_key()
    # Ưu tiên Flash 2.5 (Tư duy nhanh) -> Pro (Tư duy sâu)
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    
    # Ghép Prompt cuối cùng
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (CONTEXT):
    {context}
    
    CÂU HỎI CỦA NGƯỜI DÙNG:
    {prompt}
    """
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "system_instruction": {"parts": [{"text": ALGORITHMS_INSTRUCTION}]}, # Gửi kèm thuật toán
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=50) # Tăng timeout để AI "suy nghĩ"
            if response.status_code == 200:
                result = response.json()
                try: return result['candidates'][0]['content']['parts'][0]['text']
                except: return "⚠️ AI trả lời rỗng."
            elif response.status_code == 404: continue 
            elif response.status_code == 429: time.sleep(2); continue 
            else: continue
        except: continue
            
    return "⚠️ Hệ thống đang bận. Vui lòng thử lại sau."

# --- 5. ĐỌC DỮ LIỆU DRIVE (SMART FILTER) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        # Phân loại kỹ hơn để phục vụ Thuật toán
        data_store = {
            "xu_phat": [],    # NĐ 144, 109, 106, 189 (Thẩm quyền)
            "phap_luat": [],  # NĐ 136, 105 (Thủ tục), 50 (Phân cấp)
            "ky_thuat": [],   # QCVN, TCVN
            "chua_chay": []   # Chiến thuật
        }
        
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
                    for p in doc.paragraphs: content += p.text + "\n"
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    for page in reader.pages[:25]: # Đọc 25 trang đầu
                        if page.extract_text(): content += page.extract_text() + "\n"
                
                if content:
                    item = f"VĂN BẢN: {file['name']}\nNỘI DUNG:\n{content}\n---\n"
                    
                    # LOGIC PHÂN LOẠI MỚI (Cập nhật NĐ 105, 106)
                    if any(x in fname for x in ["144", "109", "106", "189", "xu phat", "vi pham"]):
                        data_store["xu_phat"].append(item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "3890"]):
                        data_store["ky_thuat"].append(item)
                    elif any(x in fname for x in ["chua chay", "cnch", "phuong an"]):
                        data_store["chua_chay"].append(item)
                    # Ưu tiên NĐ 105, 136, 50 vào nhóm Pháp luật
                    elif any(x in fname for x in ["136", "50", "105", "luat", "nghi dinh", "ho so"]):
                        data_store["phap_luat"].append(item)
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

with st.spinner('🚀 Đang khởi tạo bộ não nghiệp vụ...'):
    data_store, file_count = load_data_smart()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

with st.expander(f"✅ TRẠNG THÁI: {file_count} VĂN BẢN ĐÃ NẠP"):
    st.info("Hệ thống đã tích hợp thuật toán: Sàng lọc thẩm quyền xử phạt & Phân cấp quản lý.")

# --- CHAT ENGINE ---
if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "👮"):
        st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi (Ví dụ: Lỗi này ai ký phạt? Cơ sở này ai quản lý?)..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # 1. Chọn dữ liệu (Smart Context)
    p = prompt.lower()
    ctx = ""
    label = "Tổng hợp"
    
    if "phạt" in p or "tiền" in p or "thẩm quyền" in p or "ai ký" in p:
        # Cần cả Xử phạt (để biết lỗi) + Pháp luật (để biết thẩm quyền NĐ 189)
        ctx += "\n".join(data_store["xu_phat"] + data_store["phap_luat"])
        label = "Xử phạt & Thẩm quyền"
    elif "quản lý" in p or "phân cấp" in p or "phụ lục" in p:
        # Cần Pháp luật (NĐ 136/50)
        ctx += "\n".join(data_store["phap_luat"])
        label = "Phân cấp quản lý"
    elif "kỹ thuật" in p or "mét" in p or "bậc" in p:
        ctx += "\n".join(data_store["ky_thuat"])
        label = "Quy chuẩn Kỹ thuật"
    elif "hồ sơ" in p or "thủ tục" in p:
        # Ưu tiên Pháp luật (NĐ 105)
        ctx += "\n".join(data_store["phap_luat"])
        label = "Thủ tục hành chính"
    else:
        # Mặc định lấy Luật + Phạt
        ctx += "\n".join(data_store["phap_luat"] + data_store["xu_phat"])
    
    # 2. Gọi AI với Thuật toán
    with st.chat_message("assistant", avatar="👮"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang áp dụng thuật toán ({label})...*")
        
        reply = call_gemini_logic(prompt, ctx)
        
        msg_ph.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
