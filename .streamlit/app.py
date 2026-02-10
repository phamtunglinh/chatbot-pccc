import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from docx import Document
from pypdf import PdfReader
import io
import json
import time
import random

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(
    page_title="Hệ thống Trợ lý ảo PCCC & CNCH (Pro)",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatInput {border-radius: 20px;}
    .header-banner {
        background: linear-gradient(90deg, #b92b27 0%, #1565C0 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .user-msg {text-align: right; background-color: #e3f2fd; padding: 10px; border-radius: 10px; margin: 5px 0;}
    .bot-msg {text-align: left; background-color: #f1f1f1; padding: 10px; border-radius: 10px; margin: 5px 0;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI & QUẢN LÝ "KHO ĐẠN" (API KEYS) ---
try:
    if "GEMINI_API_KEYS" in st.secrets:
        keys_string = st.secrets["GEMINI_API_KEYS"]
    else:
        keys_string = st.secrets["GEMINI_API_KEY"]
        
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình Secrets: {str(e)}")
    st.stop()

# Cơ chế xoay vòng Key thông minh (Load Balancing)
if "key_index" not in st.session_state: st.session_state.key_index = 0

def get_next_key():
    # Lấy key tiếp theo trong danh sách, xoay vòng
    current = API_KEYS_LIST[st.session_state.key_index]
    st.session_state.key_index = (st.session_state.key_index + 1) % len(API_KEYS_LIST)
    return current

# --- 3. CORE: ĐỌC DỮ LIỆU SIÊU TỐC (SMART CACHING) ---
# Dùng cache_data để lưu vĩnh viễn trong RAM, không tải lại khi F5
@st.cache_data(ttl=7200, show_spinner=False) 
def load_and_process_drive_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        # Cấu trúc dữ liệu mới: Dictionary
        data_store = {
            "phap_luat": [], "xu_phat": [], "ky_thuat": [], "chua_chay": [], "khac": []
        }
        
        total_files = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            try:
                # Tải file
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                # Đọc nội dung
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    for p in doc.paragraphs: 
                        if p.text.strip(): content += p.text + "\n"
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Giới hạn 30 trang đầu để tránh quá tải
                    for page in reader.pages[:30]: 
                        if page.extract_text(): content += page.extract_text() + "\n"
                
                if content:
                    # Đóng gói văn bản sạch sẽ
                    doc_item = f"SOURCE: {file['name']}\nCONTENT:\n{content}\n----------------\n"
                    
                    # PHÂN LOẠI THÔNG MINH
                    if any(x in fname for x in ["106", "189", "144", "xu phat", "vi pham"]):
                        data_store["xu_phat"].append(doc_item)
                    elif any(x in fname for x in ["06", "qc10", "tcvn", "ky thuat", "tieu chuan"]):
                        data_store["ky_thuat"].append(doc_item)
                    elif any(x in fname for x in ["chua chay", "cnch", "phuong an", "chien thuat"]):
                        data_store["chua_chay"].append(doc_item)
                    elif any(x in fname for x in ["136", "50", "105", "luat", "nghi dinh", "ho so", "thu tuc"]):
                        data_store["phap_luat"].append(doc_item)
                    else:
                        data_store["khac"].append(doc_item)
                    
                    total_files += 1
            except: continue
            
        return data_store, total_files
    except Exception as e: return None, str(e)

# --- 4. ENGINE: TƯ DUY & TRẢ LỜI (SMART ENGINE) ---

def smart_context_retrieval(prompt, data_store):
    """
    Hàm chọn lọc dữ liệu thông minh "Cộng dồn"
    """
    p = prompt.lower()
    context = ""
    sources = []
    
    # Logic cộng dồn (Không loại trừ)
    # 1. Nếu hỏi phạt -> Cần Xử phạt + Luật gốc (để xem hành vi)
    if any(x in p for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        context += "\n".join(data_store["xu_phat"])
        context += "\n".join(data_store["phap_luat"]) 
        sources.append("Xử phạt + Pháp lý")
        
    # 2. Nếu hỏi kỹ thuật -> Cần Quy chuẩn
    if any(x in p for x in ["mét", "cao", "rộng", "cách", "trang bị", "lối", "bậc", "thang", "cửa"]):
        context += "\n".join(data_store["ky_thuat"])
        sources.append("Kỹ thuật")
        
    # 3. Nếu hỏi thủ tục/hồ sơ -> Cần Pháp luật
    if any(x in p for x in ["hồ sơ", "thủ tục", "thẩm duyệt", "nghiệm thu", "quản lý", "gồm những gì"]):
        context += "\n".join(data_store["phap_luat"])
        sources.append("Thủ tục")
        
    # 4. Nếu hỏi chữa cháy -> Cần Chữa cháy + Kỹ thuật (để xem thông số xe)
    if any(x in p for x in ["chữa cháy", "cứu nạn", "xe", "bơm", "đội hình", "phương án"]):
        context += "\n".join(data_store["chua_chay"])
        context += "\n".join(data_store["ky_thuat"])
        sources.append("Chữa cháy")

    # Fallback: Nếu không bắt được từ khóa
    if len(context) < 100: 
        all_docs = []
        # Ưu tiên lấy Pháp luật và Quy chuẩn nếu không rõ ý định
        all_docs.extend(data_store["phap_luat"])
        all_docs.extend(data_store["ky_thuat"])
        context = "\n".join(all_docs)
        sources = ["Tài liệu cơ bản"]
        
    return context, ", ".join(list(set(sources)))

def ask_gemini_advanced(full_prompt):
    """
    Hàm gọi AI tự động xử lý lỗi
    """
    # Danh sách model ưu tiên (Flash nhanh nhất -> Pro thông minh hơn)
    # Lưu ý: Code này dùng thư viện, nếu thư viện cũ quá nó sẽ tự thử model cũ
    models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    last_error = ""
    
    for attempt in range(5): # Thử tối đa 5 lần
        try:
            current_key = get_next_key() # Đổi key
            genai.configure(api_key=current_key)
            
            # Thử lần lượt từng model trong danh sách
            for model_name in models:
                try:
                    model = genai.GenerativeModel(model_name)
                    # Gửi yêu cầu
                    response = model.generate_content(full_prompt)
                    return response.text
                except Exception as inner_e:
                    # Nếu model này không có (404) -> Thử model tiếp theo trong list
                    if "404" in str(inner_e): continue 
                    # Nếu lỗi khác (ví dụ quá tải 429) -> Thoát vòng lặp model để đổi Key
                    raise inner_e 

        except Exception as e:
            error_msg = str(e).lower()
            last_error = error_msg
            if "429" in error_msg or "quota" in error_msg:
                time.sleep(1) # Nghỉ xíu rồi đổi key thử lại
                continue 
            time.sleep(1)
            
    return f"⚠️ Hệ thống đang bận. Vui lòng thử lại sau. (Chi tiết: {last_error})"

# --- GIAO DIỆN CHÍNH ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🔥</div>
    <p style="font-size: 24px; font-weight: 900; margin: 0;">TRỢ LÝ AI PCCC & CNCH</p>
    <p style="font-size: 14px; opacity: 0.9;">PHÒNG PC07 - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

# Load dữ liệu (Chỉ chạy 1 lần khi khởi động)
with st.spinner('🚀 Đang khởi động hệ thống siêu tốc...'):
    data_store, file_count = load_and_process_drive_data()

if not data_store: 
    st.error("❌ Không kết nối được dữ liệu Drive.")
    st.stop()

# Hiển thị trạng thái Admin (Gọn gàng)
with st.expander(f"✅ HỆ THỐNG SẴN SÀNG | {file_count} TÀI LIỆU | {len(API_KEYS_LIST)} API KEYS"):
    cols = st.columns(5)
    cols[0].metric("Pháp luật", len(data_store["phap_luat"]))
    cols[1].metric("Xử phạt", len(data_store["xu_phat"]))
    cols[2].metric("Kỹ thuật", len(data_store["ky_thuat"]))
    cols[3].metric("Chữa cháy", len(data_store["chua_chay"]))
    cols[4].metric("Khác", len(data_store["khac"]))

# --- CHAT ---
if "messages" not in st.session_state: st.session_state.messages = []

# Hiển thị lịch sử
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"):
        st.markdown(msg["content"])

# Xử lý câu hỏi
if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # 1. Lấy dữ liệu liên quan
    context_text, source_type = smart_context_retrieval(prompt, data_store)
    
    # 2. Tạo Prompt 
    final_prompt = f"""
    VAI TRÒ: Bạn là Đại úy Phạm Tùng Linh - Trợ lý nghiệp vụ PCCC & CNCH uy tín, chính xác.
    
    DỮ LIỆU THAM KHẢO (CONTEXT):
    {context_text}
    
    CÂU HỎI: "{prompt}"
    
    🛑 NHIỆM VỤ:
    Hãy thực hiện quy trình suy luận từng bước (Chain of Thought) trước khi đưa ra câu trả lời cuối cùng:
    
    1. **PHÂN TÍCH:** Xác định câu hỏi thuộc lĩnh vực nào (Phạt, Hồ sơ, hay Kỹ thuật)?
    2. **TÌM KIẾM:** Rà soát trong DỮ LIỆU THAM KHẢO để tìm các điều khoản chính xác.
    3. **KIỂM TRA CHÉO:** - Nếu là Xử phạt: Kiểm tra mức tiền + Thẩm quyền.
       - Nếu là Kỹ thuật: Kiểm tra thông số cụ thể trong QCVN/TCVN.
       - Nếu là Hồ sơ: Kiểm tra NĐ 105/136.
    4. **TỔNG HỢP:** Trả lời ngắn gọn, súc tích, trích dẫn văn bản pháp luật (Điều, Khoản, Nghị định...).
    
    YÊU CẦU ĐẦU RA:
    - Không hiển thị quá trình suy luận, chỉ hiển thị KẾT QUẢ CUỐI CÙNG.
    - Văn phong: Chuyên nghiệp, quân sự, rõ ràng.
    - Nếu không có dữ liệu: Trả lời "Nội dung này chưa được cập nhật trong hệ thống văn bản hiện tại."
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        msg_ph.markdown(f"⚡ *Đang truy xuất dữ liệu ({source_type}) và suy luận pháp lý...*")
        
        # Gọi AI
        reply = ask_gemini_advanced(final_prompt)
        
        full_reply = reply + "\n\n---\n*Đại úy cần tra cứu thêm nội dung gì không?*"
        msg_ph.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
