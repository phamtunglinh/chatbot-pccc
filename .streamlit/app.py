import streamlit as st
import requests
import json
import random
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="Trợ lý PCCC & CNCH", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem; color: white; text-align: center; 
        border-radius: 0 0 15px 15px; margin-top: -60px; margin-bottom: 20px;
    }
    .stChatInput {border-radius: 20px;}
    .reportview-container .main .block-container {padding-top: 2rem;}
</style>
<div class="header-banner">
    <h2>🛡️ HỆ THỐNG TRỢ LÝ PCCC & CNCH</h2>
    <p>Tra cứu Luật - Xử phạt - Quy chuẩn Kỹ thuật</p>
</div>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI KEY & DRIVE ---
try:
    # Lấy Key (Hỗ trợ cả tên biến có S và không S)
    if "GEMINI_API_KEYS" in st.secrets: keys_str = st.secrets["GEMINI_API_KEYS"]
    else: keys_str = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    
    FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: 
    st.error("⚠️ Lỗi cấu hình Secrets. Vui lòng kiểm tra lại Key và JSON."); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- 3. HÀM PHÂN LOẠI & ĐỌC DỮ LIỆU (CORE ENGINE) ---
@st.cache_resource(ttl=3600) # Lưu bộ nhớ đệm 1 tiếng để đỡ tốn thời gian đọc lại
def load_data_smart():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        # Lấy tối đa 100 file
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        # 4 CÁI GIỎ ĐỰNG TÀI LIỆU
        buckets = {
            "xu_phat": "",    # Chứa Nghị định 144, 109...
            "quy_chuan": "",  # Chứa QCVN 06, TCVN 3890...
            "phap_luat": "",  # Chứa Luật PCCC, NĐ 136...
            "chua_chay": ""   # Chứa chiến thuật, đội hình...
        }
        
        file_list = [] # Để hiển thị cho Đại úy xem đã đọc được gì

        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue # Bỏ qua file Google Doc/Sheet online
            
            try:
                # Tải nội dung file về RAM
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False; 
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                
                content = ""
                # Xử lý file Word
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                # Xử lý file PDF
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Giới hạn 50 trang đầu mỗi file để tránh quá tải
                    content = "\n".join([p.extract_text() for p in reader.pages[:50] if p.extract_text()])

                if content:
                    # Đóng gói văn bản
                    formatted_text = f"\n=== TÀI LIỆU: {file['name']} ===\n{content}\n=== HẾT VĂN BẢN ===\n"
                    
                    # --- BỘ LỌC THÔNG MINH ---
                    # 1. Nhóm Xử phạt
                    if any(x in fname for x in ["xu phat", "vi pham", "144", "109", "xphc", "phat"]):
                        buckets["xu_phat"] += formatted_text
                        file_list.append(f"🔴 Xử phạt: {file['name']}")
                    
                    # 2. Nhóm Quy chuẩn (Kỹ thuật)
                    elif any(x in fname for x in ["quy chuan", "tieu chuan", "qcvn", "tcvn", "06", "3890", "2622"]):
                        buckets["quy_chuan"] += formatted_text
                        file_list.append(f"🔵 Kỹ thuật: {file['name']}")
                    
                    # 3. Nhóm Chữa cháy (Chiến thuật)
                    elif any(x in fname for x in ["chien thuat", "doi hinh", "cuu nan", "cnch", "phuong an"]):
                        buckets["chua_chay"] += formatted_text
                        file_list.append(f"🟠 Chữa cháy: {file['name']}")
                        
                    # 4. Nhóm Pháp luật chung (Mặc định)
                    else:
                        buckets["phap_luat"] += formatted_text
                        file_list.append(f"🟢 Pháp luật: {file['name']}")
                        
            except: continue
            
        return buckets, file_list
    except Exception as e: return None, str(e)

# --- 4. HÀM CHỌN DỮ LIỆU THEO CÂU HỎI ---
def select_context(query, buckets):
    q = query.lower()
    selected_text = ""
    sources = []
    
    # Logic phát hiện ý định (Intent Detection)
    
    # 4.1. Hỏi về TIỀN/PHẠT -> Lấy Xử phạt + Luật gốc
    if any(x in q for x in ["phạt", "tiền", "lỗi", "bao nhiêu", "vi phạm", "xử lý"]):
        selected_text += buckets["xu_phat"] + buckets["phap_luat"]
        sources.append("Nghị định Xử phạt & Pháp lý")
        
    # 4.2. Hỏi về KỸ THUẬT/KÍCH THƯỚC -> Lấy Quy chuẩn
    elif any(x in q for x in ["mét", "chiều cao", "rộng", "bậc", "thang", "cửa", "lối thoát", "khoảng cách", "trang bị", "bình chữa cháy"]):
        selected_text += buckets["quy_chuan"]
        sources.append("QCVN & TCVN Kỹ thuật")
        
    # 4.3. Hỏi về CHIẾN THUẬT -> Lấy Chữa cháy
    elif any(x in q for x in ["chiến thuật", "đội hình", "xe", "bơm", "lăng", "vòi"]):
        selected_text += buckets["chua_chay"]
        sources.append("Chiến thuật Chữa cháy")
        
    # 4.4. Hỏi về THỦ TỤC -> Lấy Pháp luật
    elif any(x in q for x in ["hồ sơ", "thẩm duyệt", "nghiệm thu", "giấy phép", "thủ tục"]):
        selected_text += buckets["phap_luat"]
        sources.append("Thủ tục Hành chính")

    # Mặc định: Nếu không bắt được từ khóa, lấy Pháp luật + Quy chuẩn (Cơ bản nhất)
    if not selected_text:
        selected_text = buckets["phap_luat"]
        sources = ["Văn bản Pháp luật chung"]
        
    return selected_text, " + ".join(sources)

# --- 5. GỌI GEMINI (DIRECT API - XOAY VÒNG KEY) ---
def call_gemini(prompt, system_instruction):
    # Danh sách model xịn nhất (Flash 2.5)
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    for _ in range(3): # Thử tối đa 3 lần (đổi key hoặc đổi model)
        api_key = get_random_key()
        model = models[0] # Ưu tiên model mới nhất
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "temperature": 0.3, # 0.3 giúp AI trả lời chính xác, ít sáng tạo linh tinh
                "maxOutputTokens": 4000
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=40)
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 429:
                time.sleep(2); continue # Quá tải thì thử key khác
            else:
                continue # Lỗi khác cũng thử lại
        except: continue
            
    return "⚠️ Hệ thống đang bận hoặc văn bản quá dài. Đại úy vui lòng hỏi ngắn gọn hơn."

# --- 6. GIAO DIỆN CHÍNH ---
with st.spinner("Đang khởi động hệ thống dữ liệu PCCC..."):
    buckets, debug_info = load_data_smart()

if not buckets: st.error("Lỗi kết nối Drive"); st.stop()

# Sidebar: Hiển thị trạng thái dữ liệu
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Police_badge_of_Vietnam.svg/1200px-Police_badge_of_Vietnam.svg.png", width=100)
    st.success(f"✅ Đã nạp xong {len(debug_info)} tài liệu")
    with st.expander("📂 Danh sách tài liệu"):
        for f in debug_info: st.caption(f)
    st.info("💡 Mẹo: Hệ thống tự động chọn tài liệu Xử phạt hoặc Quy chuẩn dựa trên câu hỏi của Đại úy.")

# Chat UI
if "messages" not in st.session_state: 
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": "Chào Đại úy Linh! Tôi đã sẵn sàng tra cứu Luật, Xử phạt và Quy chuẩn. Đại úy cần hỗ trợ gì?"})

for msg in st.session_state.messages:
    st.chat_message(msg["role"], avatar="👮‍♂️" if msg["role"]=="user" else "🤖").write(msg["content"])

if query := st.chat_input("Nhập câu hỏi (Ví dụ: Lỗi không có hồ sơ phương án chữa cháy phạt bao nhiêu?)..."):
    st.session_state.messages.append({"role": "user", "content": query})
    st.chat_message("user", avatar="👮‍♂️").write(query)
    
    # 1. Chọn dữ liệu phù hợp
    context_text, source_type = select_context(query, buckets)
    
    # 2. Xây dựng Prompt (Kỹ thuật Prompt Engineering)
    system_instruction = """
    Bạn là Trợ lý ảo chuyên ngành PCCC & CNCH của Cảnh sát Việt Nam.
    Nhiệm vụ: Trả lời câu hỏi dựa trên văn bản pháp luật được cung cấp.
    
    QUY TẮC TRẢ LỜI:
    1. Căn cứ pháp lý: Phải trích dẫn rõ "Theo Khoản X, Điều Y, Nghị định/Thông tư Z".
    2. Nếu hỏi về Xử phạt: Phải nêu rõ mức phạt tiền (đối với cá nhân/tổ chức) và biện pháp khắc phục (nếu có).
    3. Nếu hỏi về Quy chuẩn: Phải nêu rõ thông số kỹ thuật chính xác.
    4. Không bịa đặt: Nếu không thấy thông tin trong văn bản, hãy nói "Trong các tài liệu hiện có không đề cập vấn đề này".
    5. Văn phong: Trang trọng, ngắn gọn, quân sự.
    """
    
    final_prompt = f"""
    DỮ LIỆU THAM KHẢO (Đã lọc: {source_type}):
    {context_text}
    
    CÂU HỎI: {query}
    """
    
    with st.chat_message("assistant", avatar="🤖"):
        msg_box = st.empty()
        msg_box.markdown(f"⏳ *Đang tra cứu trong: {source_type}...*")
        
        reply = call_gemini(final_prompt, system_instruction)
        
        msg_box.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
