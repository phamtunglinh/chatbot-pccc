import streamlit as st
import google.generativeai as genai # Dùng thư viện chính hãng
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
st.set_page_config(page_title="PCCC PC07 (SDK Stable)", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
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

# --- 3. BỘ NÃO TƯ DUY (RULES BẤT DI BẤT DỊCH) ---
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Nghiệp vụ PCCC & CNCH.

⚡ DỮ LIỆU ĐƯỢC CUNG CẤP:
1. [NĐ 105]: Quản lý, Hồ sơ.
2. [NĐ 106]: Hành vi & Mức phạt.
3. [NĐ 189]: Thẩm quyền xử phạt.
4. [QCVN 10]: Kỹ thuật.

🧠 KỸ NĂNG SUY LUẬN LỖI (MAPPING):
   - "Không có..." -> Tìm: "Không lập", "Không trang bị", "Không lắp đặt".
   - "Hồ sơ" -> Tìm: "Vi phạm quy định về hồ sơ quản lý".
   - "Thiếu..." -> Tìm: "Không đầy đủ".

🔴 QUY TRÌNH 1: XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (NĐ 105)
    BƯỚC 1: KIỂM TRA DỮ LIỆU ĐẦU VÀO (Diện tích, Tầng, Khối tích, Công năng).
    BƯỚC 2: XÁC ĐỊNH CÔNG NĂNG CHÍNH (QUY TẮC 70%)
    - > 70% diện tích -> Công năng chính.
    - Nhà ở > 70% -> Nhà ở kết hợp SXKD.
    - Không có > 70% -> NHÀ HỖN HỢP.
    BƯỚC 3: ĐỐI CHIẾU PHỤ LỤC (Nghị định 105/2025).
    BƯỚC 4: KẾT LUẬN (ƯU TIÊN TUYỆT ĐỐI)
    - Có tên trong Phụ lục II -> PC07 quản lý.
    - Chỉ thuộc Phụ lục I (không thuộc II) -> Công an Huyện hoặc Xã.

🔴 QUY TRÌNH 2: XỬ PHẠT VI PHẠM HÀNH CHÍNH (NĐ 106 & 189)
    BƯỚC 1: XÁC ĐỊNH MỨC PHẠT (NĐ 106)
    - Tìm hành vi (dùng kỹ năng suy luận).
    - Xác định Mức phạt tiền (Cá nhân & Tổ chức).
    BƯỚC 2: SÀNG LỌC THẨM QUYỀN (NĐ 189)
    - So sánh mức phạt tối đa với quyền hạn các chức danh.
    - LOẠI BỎ NGAY chức danh không đủ tiền hoặc không đủ quyền phạt bổ sung.
    BƯỚC 3: TRÌNH BÀY (FORM MẪU):
    1. Hành vi: [Tên pháp lý]
    2. Mức phạt: 
       - Cá nhân: ... (Căn cứ NĐ 106).
       - Tổ chức: ...
    3. Biện pháp bổ sung/KPHQ: ...
    4. Phân tích thẩm quyền (BẮT BUỘC):
       - [Chức danh A]: Quyền phạt ... -> ĐỦ/KHÔNG.
       - [Chức danh B]: Quyền phạt ... -> ĐỦ/KHÔNG.
    5. Đề xuất: Trình [Chức danh thấp nhất đủ quyền] ra quyết định.

🟢 QUY TRÌNH 3: TRANG BỊ KỸ THUẬT (QCVN 10)
    - Tra cứu Bảng biểu -> Liệt kê hệ thống bắt buộc.

🛑 NGUYÊN TẮC VÀNG: KHÔNG trả lời chung chung. TRÍCH DẪN CỤ THỂ.
"""

# --- 4. HÀM GỌI AI (DÙNG SDK CHÍNH HÃNG - SIÊU ỔN ĐỊNH) ---
def call_gemini_sdk(prompt, context):
    # Cắt context an toàn (300k ký tự)
    if len(context) > 300000: context = context[:300000]
    
    full_prompt = f"""
    DỮ LIỆU THAM KHẢO (ĐÃ ƯU TIÊN 189, 106):
    {context}
    
    CÂU HỎI: "{prompt}"
    """
    
    # Thử tối đa 3 lần đổi key nếu lỗi
    for attempt in range(3):
        try:
            api_key = get_random_key()
            genai.configure(api_key=api_key)
            
            # Cấu hình model
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',
                system_instruction=ALGORITHMS_INSTRUCTION # Nạp Rule vào não
            )
            
            # Gửi lệnh
            response = model.generate_content(full_prompt)
            return response.text
            
        except Exception as e:
            time.sleep(1) # Nghỉ 1s rồi thử key khác
            continue
            
    return "⚠️ Hệ thống đang bảo trì kết nối. Vui lòng thử lại sau giây lát."

# --- 5. NẠP DỮ LIỆU (CƠ CHẾ SĂN TÌM VIP) ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_data_sdk():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        
        buckets = {"xp": [], "ql": [], "kt": [], "khac": []}
        logs = []
        processed = set()

        # 1. SĂN TÌM VIP (189, 106, 105)
        queries = ["name contains '189'", "name contains '106'", "name contains '105'", "name contains '10'", "name contains 'xu phat'"]
        files = []
        for q in queries:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and {q}", fields="files(id, name)").execute().get('files', []))
            except: pass
        
        # 2. LẤY BỔ SUNG
        try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name)").execute().get('files', []))
        except: pass

        for f in files:
            if f['id'] in processed: continue
            processed.add(f['id'])
            name = f['name'].lower()

            # Lọc rác (144, 136)
            if "144" in name and "106" not in name and "189" not in name: continue
            if "136" in name and "105" not in name: continue

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
                    if any(x in name for x in ["106", "189", "xu phat"]): buckets["xp"].append(item)
                    elif "105" in name: buckets["ql"].append(item)
                    elif any(x in name for x in ["qcvn", "10:2025", "trang bi"]): buckets["kt"].append(item)
                    else: buckets["khac"].append(item)
                    logs.append(f"✅ {f['name']}")
            except: continue
        return buckets, logs
    except: return None, []

# --- 6. GIAO DIỆN ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC (CÔNG NGHỆ SDK)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang kết nối SDK & Nạp Rules...'):
    data_store, file_logs = load_data_sdk()

if not data_store: st.error("❌ Lỗi dữ liệu."); st.stop()

# SIDEBAR CHECK
with st.sidebar:
    st.header("TRẠNG THÁI")
    if any("189" in l for l in file_logs): st.success("✅ Đã nạp NĐ 189")
    else: st.error("❌ Thiếu NĐ 189")
    with st.expander("File đã nạp"):
        for l in file_logs: st.text(l)

# CHAT
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    # ROUTER (ĐỊNH TUYẾN)
    p_lower = prompt.lower()
    ctx = []
    
    # XỬ PHẠT
    if any(x in p_lower for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi", "hồ sơ", "thiếu"]):
        ctx.extend([x for x in data_store["xp"] if "189" in x]) # Ưu tiên 189
        ctx.extend([x for x in data_store["xp"] if "106" in x])
        ctx.extend(data_store["ql"])
        
    # QUẢN LÝ
    elif any(x in p_lower for x in ["quản lý", "phân cấp", "karaoke"]):
        ctx.extend(data_store["ql"])
        
    # KỸ THUẬT
    elif any(x in p_lower for x in ["trang bị", "lắp đặt"]):
        ctx.extend(data_store["kt"])
        
    # MẶC ĐỊNH (Cho câu Xin chào...)
    else:
        ctx.extend(data_store["ql"]) 

    # Nếu ctx vẫn rỗng (trường hợp lạ), lấy hết
    if not ctx: ctx = data_store["ql"] + data_store["xp"]

    with st.chat_message("assistant", avatar="🚒"):
        msg_area = st.empty()
        msg_area.markdown("⚡ *Đang xử lý...*")
        
        final_context = "\n".join(ctx)
        response = call_gemini_sdk(prompt, final_context)
        
        msg_area.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
