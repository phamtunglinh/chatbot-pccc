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

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="PCCC & CNCH Phú Thọ",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stChatInput {border-radius: 20px;}
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1.5rem; border-radius: 0 0 15px 15px;
        color: white; text-align: center; margin-top: -60px; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI ---
try:
    GEMINI_KEY = st.secrets["GEMINI_API_KEY"]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e:
    st.error(f"⚠️ Lỗi cấu hình: {str(e)}")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- MODEL ---
@st.cache_resource
def get_best_model():
    priority = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]
    try:
        available = [m.name.replace("models/", "") for m in genai.list_models()]
        for model in priority:
            if model in available: return model
        return "gemini-pro"
    except: return "gemini-pro"

ACTIVE_MODEL = get_best_model()

# --- HÀM ĐỌC DRIVE (5 GIỎ) ---
@st.cache_resource(ttl=3600)
def load_drive_data_categorized():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            pageSize=100, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        groups = {
            "phap_luat": "", "xu_phat": "", "quy_chuan": "", "chua_chay": "", "van_ban_khac": "",
            "debug": {"phap_luat": [], "xu_phat": [], "quy_chuan": [], "chua_chay": [], "van_ban_khac": []}
        }
        
        file_count = 0
        
        for file in files:
            fname = file['name'].lower()
            if "google-apps" in file['mimeType']: continue 
            
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                content = ""
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    for p in doc.paragraphs: content += p.text + "\n"
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    for page in reader.pages: content += page.extract_text() + "\n"
                
                if content:
                    formatted_content = f"\n=== FILE: {file['name']} ===\n{content}\n=== HẾT FILE ===\n"
                    
                    # LOGIC PHÂN LOẠI (Ưu tiên từ trên xuống)
                    if any(x in fname for x in ["xu phat", "vi pham", "106", "189", "144", "xphc"]):
                        groups["xu_phat"] += formatted_content
                        groups["debug"]["xu_phat"].append(file['name'])
                    elif any(x in fname for x in ["chua chay", "cuu nan", "cnch", "phuong an", "chien thuat"]):
                        groups["chua_chay"] += formatted_content
                        groups["debug"]["chua_chay"].append(file['name'])
                    elif any(x in fname for x in ["quy chuan", "tieu chuan", "qcvn", "tcvn", "qc10", "ky thuat", "06", "3890"]):
                        groups["quy_chuan"] += formatted_content
                        groups["debug"]["quy_chuan"].append(file['name'])
                    elif any(x in fname for x in ["luat", "nghi dinh", "thong tu", "nd", "tt", "136", "50", "105", "ho so", "thu tuc", "quan ly"]):
                        groups["phap_luat"] += formatted_content
                        groups["debug"]["phap_luat"].append(file['name'])
                    else:
                        groups["van_ban_khac"] += formatted_content
                        groups["debug"]["van_ban_khac"].append(file['name'])
                    
                    file_count += 1
            except: continue 
            
        return groups, file_count
    except Exception as e: return None, str(e)

# --- HÀM CHỌN DỮ LIỆU (LOGIC CỘNG DỒN THÔNG MINH) ---
def select_context(prompt, groups):
    p = prompt.lower()
    
    selected_content = ""
    source_list = []
    
    # 1. KIỂM TRA YẾU TỐ XỬ PHẠT (Nếu có -> Lấy Giỏ Xử phạt)
    if any(x in p for x in ["phạt", "tiền", "lỗi", "vi phạm", "xử lý"]):
        selected_content += groups["xu_phat"]
        source_list.append("Xử phạt")
        # Mẹo: Đã hỏi phạt thì thường cần cả Luật gốc để đối chiếu hành vi
        selected_content += groups["phap_luat"] 
        source_list.append("Pháp luật (tham chiếu)")

    # 2. KIỂM TRA YẾU TỐ KỸ THUẬT (Nếu có -> Lấy Giỏ Quy chuẩn)
    # (Ví dụ: hỏi "Lỗi cửa thoát nạn 0.8m phạt bao nhiêu" -> Lấy cả Xử phạt + Quy chuẩn)
    if any(x in p for x in ["mét", "chiều cao", "rộng", "khoảng cách", "trang bị", "lối thoát", "bậc", "cầu thang", "xe", "bơm"]):
        selected_content += groups["quy_chuan"]
        source_list.append("Quy chuẩn Kỹ thuật")

    # 3. KIỂM TRA YẾU TỐ THỦ TỤC/HỒ SƠ (Nếu có -> Lấy Giỏ Pháp luật)
    if any(x in p for x in ["hồ sơ", "thủ tục", "quản lý", "thẩm duyệt", "nghiệm thu", "ai quản lý"]):
        if "Pháp luật (tham chiếu)" not in source_list: # Tránh trùng lặp
            selected_content += groups["phap_luat"]
            source_list.append("Pháp luật (Thủ tục)")

    # 4. KIỂM TRA YẾU TỐ CHỮA CHÁY (Nếu có -> Lấy Giỏ Chữa cháy)
    if any(x in p for x in ["chữa cháy", "cứu nạn", "chiến thuật", "đội hình", "phương án"]):
        selected_content += groups["chua_chay"]
        source_list.append("Chữa cháy & CNCH")

    # 5. TRƯỜNG HỢP KHÔNG BẮT ĐƯỢC TỪ KHÓA NÀO -> Gửi tất cả (An toàn)
    # Hoặc nếu nội dung quá ngắn, sợ thiếu ý
    if not selected_content:
        selected_content = groups["phap_luat"] + groups["xu_phat"] + groups["quy_chuan"] + groups["chua_chay"] + groups["van_ban_khac"]
        source_list = ["TẤT CẢ (Tìm kiếm diện rộng)"]
        
    return selected_content, " + ".join(source_list)

# --- HÀM GỌI AI ---
def ask_gemini_safe(full_prompt):
    model = genai.GenerativeModel(ACTIVE_MODEL)
    try:
        response = model.generate_content(full_prompt)
        return response.text 
    except Exception as e:
        if "429" in str(e):
            time.sleep(5)
            try: return model.generate_content(full_prompt).text
            except: return "⚠️ Hệ thống đang bận. Vui lòng đợi 30s."
        return f"⚠️ Lỗi: {str(e)}"

# --- GIAO DIỆN ---
st.markdown("""
<div class="header-banner">
    <div style="font-size: 40px; margin-bottom: 5px;">🛡️</div>
    <p class="header-title">TRỢ LÝ AI PCCC & CNCH</p>
    <p class="header-subtitle">PHÒNG CẢNH SÁT PCCC & CNCH - CÔNG AN TỈNH PHÚ THỌ</p>
</div>
""", unsafe_allow_html=True)

with st.spinner('Đang phân loại dữ liệu đa chiều...'):
    data_groups, count = load_drive_data_categorized()

if not data_groups: st.error("Lỗi Drive"); st.stop()

# --- ADMIN PANEL ---
with st.expander("🛠️ KIỂM TRA 5 NHÓM DỮ LIỆU"):
    st.write(f"✅ Model: `{ACTIVE_MODEL}` | Tổng file: {count}")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: 
        st.info("1. PHÁP LUẬT")
        for f in data_groups["debug"]["phap_luat"]: st.caption(f"- {f}")
    with c2: 
        st.warning("2. XỬ PHẠT")
        for f in data_groups["debug"]["xu_phat"]: st.caption(f"- {f}")
    with c3: 
        st.success("3. QUY CHUẨN")
        for f in data_groups["debug"]["quy_chuan"]: st.caption(f"- {f}")
    with c4: 
        st.error("4. CHỮA CHÁY")
        for f in data_groups["debug"]["chua_chay"]: st.caption(f"- {f}")
    with c5: 
        st.write("5. KHÁC")
        for f in data_groups["debug"]["van_ban_khac"]: st.caption(f"- {f}")

# CHAT
if "messages" not in st.session_state: st.session_state.messages = []
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"): st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    chat_history = ""
    for msg in st.session_state.messages[-4:]: chat_history += f"{msg['role']}: {msg['content']}\n"
    
    # GỌI HÀM CHỌN DỮ LIỆU THÔNG MINH
    selected_knowledge, source_type = select_context(prompt, data_groups)
    
    final_prompt = f"""
    VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia PCCC.
    DỮ LIỆU (CONTEXT): {selected_knowledge}
    LỊCH SỬ CHAT: {chat_history}
    
    🛑 CHỈ THỊ:
    1. Chỉ trả lời dựa trên dữ liệu cung cấp.
    2. CÁC QUY TẮC NGHIỆP VỤ:
       - Câu hỏi hỗn hợp (Vừa kỹ thuật vừa phạt): Phải trích dẫn cả Tiêu chuẩn kỹ thuật bị vi phạm VÀ Mức phạt tương ứng.
       - Hỏi Xử phạt: Luôn áp dụng Sàng lọc thẩm quyền (Tiền + Bổ sung).
       - Hỏi Hồ sơ: Ưu tiên NĐ 105, 136.
    
    CÂU HỎI: {prompt}
    """
    
    with st.chat_message("assistant", avatar="🚒"):
        msg_ph = st.empty()
        # Hiển thị cho anh biết nó đang kết hợp những giỏ nào
        msg_ph.markdown(f"⏳ *Đang tổng hợp dữ liệu từ: {source_type}...*")
        reply = ask_gemini_safe(final_prompt)
        full_reply = reply + "\n\n---\n*Đại úy cần hỏi gì thêm không?*"
        msg_ph.markdown(full_reply)
        st.session_state.messages.append({"role": "assistant", "content": full_reply})
