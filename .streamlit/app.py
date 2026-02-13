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

# --- 1. CẤU HÌNH ---
st.set_page_config(page_title="PCCC PC07 Phú Thọ (Ultimate)", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1.5rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;} .stChatInput {border-radius: 20px;}</style>""", unsafe_allow_html=True)

# --- 2. KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_string = st.secrets["GEMINI_API_KEYS"]
    else: keys_string = st.secrets["GEMINI_API_KEY"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("⚠️ Lỗi cấu hình Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ QUY TẮC CỨNG (RULES KHÔNG ĐỔI) ---
SYSTEM_RULES = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🛑 QUY TRÌNH SUY LUẬN (BẮT BUỘC):

=== NHÓM 1: XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (NĐ 105) ===
1. Kiểm tra thông tin: Diện tích, Tầng, Khối tích, Công năng. Nếu thiếu -> HỎI NGƯỢC LẠI.
2. Quy tắc 70%: Công năng > 70% là chính. Không có cái nào > 70% là Nhà hỗn hợp.
3. Đối chiếu Phụ lục I và II (NĐ 105).
4. Kết luận: Đạt tiêu chí Phụ lục II -> PC07 quản lý. Chỉ đạt Phụ lục I -> Huyện/Xã quản lý.

=== NHÓM 2: XỬ PHẠT VI PHẠM HÀNH CHÍNH (NĐ 106 & 189) ===
1. Mapping lỗi: Dịch ngôn ngữ đời thường sang thuật ngữ NĐ 106 (VD: 'Không có hồ sơ' -> 'Không lập hồ sơ').
2. Tra mức tiền: Lấy mức phạt Cá nhân trong NĐ 106 (Tổ chức = x2).
3. Sàng lọc thẩm quyền: So sánh mức phạt MAX với hạn mức trong NĐ 189.
   - Trưởng CA Xã: 5tr | Trưởng CA Huyện: 25tr | Trưởng PC07: 50tr | Giám đốc: 100tr.
4. Trình bày: Theo Form (Hành vi -> Mức phạt -> Thẩm quyền ký -> Đề xuất).

🛑 NGUYÊN TẮC VÀNG: 
- Trích dẫn chính xác Điều, Khoản. 
- Nếu có NĐ 189 trong dữ liệu, KHÔNG ĐƯỢC nói 'không tìm thấy thẩm quyền'.
"""

# --- 4. HÀM GỌI AI PHÂN LUỒNG ---
def call_gemini_ultimate(prompt, context):
    models = ["gemini-1.5-flash", "gemini-2.0-flash"]
    # Tối ưu context (Chỉ lấy 150k ký tự tinh túy nhất để tránh nghẽn)
    refined_context = context[:150000]
    
    full_prompt = f"DỮ LIỆU THAM CHIẾU:\n{refined_context}\n\nCÂU HỎI: {prompt}"
    
    for attempt in range(3):
        api_key = get_random_key()
        for model_name in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "system_instruction": {"parts": [{"text": SYSTEM_RULES}]},
                }
                response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=45)
                if response.status_code == 200:
                    return response.json()['candidates'][0]['content']['parts'][0]['text']
            except: continue
    return "⚠️ Lỗi kết nối. Đồng chí vui lòng thử lại sau 10 giây."

# --- 5. NẠP DỮ LIỆU (CƠ CHẾ ROUTER) ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_and_sort_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        db = {"xp": [], "ql": [], "kt": [], "cc": [], "khac": []}
        logs = []

        for f in files:
            name = f['name'].lower()
            # Lọc rác
            if any(x in name for x in ["136", "144", "50"]) and not any(y in name for y in ["105", "106", "189"]): continue
            
            try:
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, service.files().get_media(fileId=f['id']))
                done = False
                while not done: _, done = downloader.next_chunk()
                fh.seek(0)
                
                text = ""
                if f['name'].endswith(".docx"):
                    doc = Document(fh)
                    text = "\n".join([p.text for p in doc.paragraphs])
                    for t in doc.tables:
                        for r in t.rows: text += " | ".join([c.text.strip() for c in r.cells]) + "\n"
                elif f['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
                
                if text:
                    item = f"--- NGUỒN: {f['name']} ---\n{text}\n"
                    if any(x in name for x in ["106", "189", "xu phat"]): db["xp"].append(item)
                    elif "105" in name: db["ql"].append(item)
                    elif any(x in name for x in ["qcvn", "10:2025", "trang bi"]): db["kt"].append(item)
                    elif any(x in name for x in ["chua chay", "cnch"]): db["cc"].append(item)
                    else: db["khac"].append(item)
                    logs.append(f"✅ {f['name']}")
            except: continue
        return db, logs
    except: return None, []

# --- 6. GIAO DIỆN ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC - PHÒNG PC07 PHÚ THỌ</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang kiểm soát dữ liệu...'):
    data_store, file_logs = load_and_sort_data()

if not data_store: st.error("❌ Không thể kết nối dữ liệu."); st.stop()

# SIDEBAR DEBUG
with st.sidebar:
    st.header("📂 TRẠNG THÁI")
    xp_count = len(data_store["xp"])
    st.write(f"⚖️ Xử phạt: {xp_count} file (Sẵn sàng)")
    if any("189" in l for l in file_logs): st.success("Đã nạp NĐ 189")
    else: st.error("Thiếu NĐ 189")
    with st.expander("Danh sách file"):
        for l in file_logs: st.text(l)

# CHAT
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi nghiệp vụ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # --- ROUTER (ĐỊNH TUYẾN THÔNG MINH) ---
    p_lower = prompt.lower()
    relevant_data = []
    
    if any(x in p_lower for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi", "không lập", "không có hồ sơ"]):
        # ƯU TIÊN SỐ 1: Bốc giỏ Xử phạt (Chứa 106 và 189)
        relevant_data.extend(data_store["xp"])
        relevant_data.extend(data_store["ql"]) # NĐ 105 để hiểu hồ sơ
    elif any(x in p_lower for x in ["quản lý", "phân cấp", "ai quản", "karaoke", "bar", "khách sạn"]):
        relevant_data.extend(data_store["ql"])
    elif any(x in p_lower for x in ["trang bị", "lắp đặt", "hệ thống", "báo cháy"]):
        relevant_data.extend(data_store["kt"])
    else:
        relevant_data.extend(data_store["ql"] + data_store["xp"])

    with st.chat_message("assistant", avatar="🚒"):
        msg_area = st.empty()
        msg_area.markdown("🔎 *Đang tra cứu đúng văn bản pháp luật...*")
        
        final_context = "\n".join(relevant_data)
        response = call_gemini_ultimate(prompt, final_context)
        
        msg_area.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
