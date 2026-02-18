import streamlit as st
import google.generativeai as genai
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
st.set_page_config(page_title="PCCC PC07 (Ultimate Intelligence)", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1.5rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;} .stChatInput {border-radius: 20px;} .citation-box {background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #d32f2f; margin-top: 10px; font-size: 0.9em;}</style>""", unsafe_allow_html=True)

# --- 2. KẾT NỐI API ---
API_KEYS_LIST = []
try:
    if "GEMINI_API_KEYS" in st.secrets: 
        keys_string = st.secrets["GEMINI_API_KEYS"]
        API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    elif "GEMINI_API_KEY" in st.secrets:
        API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]
    
    if not API_KEYS_LIST: st.error("❌ LỖI: Không tìm thấy API Key!"); st.stop()
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e: st.error(f"⚠️ Lỗi cấu hình: {str(e)}"); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO THAM MƯU (SMART ROUTER - ĐẦY ĐỦ QUY TẮC CHỌN SÁCH) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: PHÂN TÍCH CÂU HỎI để chọn tài liệu TIẾT KIỆM nhưng CHÍNH XÁC NHẤT:

1. GIỎ PHÁP LÝ & QUẢN LÝ (Hình tháp pháp lý):
   - Tài liệu: [Luật PCCC], [Nghị định 105], [Thông tư 36].
   - Dấu hiệu: Hỏi về trách nhiệm người đứng đầu, hồ sơ quản lý, thẩm duyệt, nghiệm thu.
   - QUY TẮC: Nếu hỏi về "Trách nhiệm" hoặc "Hồ sơ" -> BẮT BUỘC CHỌN CẢ 3 (Luật + 105 + 36).

2. GIỎ XỬ PHẠT (Quy tắc tách biệt):
   - Tài liệu: [Nghị định 106] (Mức phạt), [Nghị định 189] (Thẩm quyền).
   - QUY TẮC:
     + Nếu chỉ hỏi "Phạt bao nhiêu", "Lỗi này bị sao" -> CHỈ CHỌN [NĐ 106].
     + Nếu hỏi "Ai phạt", "Ai ký", "Thẩm quyền", "Công an xã phạt được không" -> CHỌN CẢ [NĐ 106] VÀ [NĐ 189].

3. GIỎ LỰC LƯỢNG:
   - Tài liệu: [TT 37] (Đội PCCC cơ sở), [TT 48] (Trang phục).
   - Dấu hiệu: Đội dân phòng, cơ sở, chuyên ngành, trang phục, huấn luyện.

4. GIỎ HUY ĐỘNG:
   - Tài liệu: [Công văn huy động lực lượng].
   - Dấu hiệu: Điều động xe, chi viện, báo cháy 114.

5. GIỎ KỸ THUẬT & TRANG BỊ:
   - Tài liệu: [QCVN 10] (Trang bị phương tiện), [QCVN 06] (Lối thoát nạn).
   - Dấu hiệu: Hỏi "Cần trang bị gì?", "Lắp hệ thống nào?", "Cầu thang rộng bao nhiêu?".
   - QUY TẮC CỨNG: Nếu hỏi về trang bị/lắp đặt -> BẮT BUỘC chọn [QCVN 10].

OUTPUT: Chỉ trả về danh sách tên file cần thiết có trong kho, ngăn cách bằng dấu phẩy.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE HIỆN CÓ: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    try:
        api_key = get_random_key()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except: return ""

# --- 4. BỘ NÃO CHUYÊN GIA (EXPERT - ĐẦY ĐỦ RULE NGHIỆP VỤ) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🚫 NGUYÊN TẮC CỐT TỬ (GROUNDING):
1. TUYỆT ĐỐI KHÔNG SÁNG TẠO: Chỉ trả lời dựa trên tài liệu được cung cấp. Nếu không có -> Nói "Không có thông tin".
2. TRÍCH DẪN CHÍNH XÁC: Phải ghi rõ nguồn (Điểm, Khoản, Điều, Bảng, Tên văn bản).

⚡ QUY TRÌNH NGHIỆP VỤ (LOGIC BẮT BUỘC PHẢI CHẠY):

1️⃣ KỸ NĂNG MAPPING (DỊCH LỖI):
   - Dân nói: "Không có/thiếu" -> Dịch sang luật: "Không lập/Không trang bị đầy đủ".
   - Dân nói: "Hồ sơ" -> Dịch sang luật: "Vi phạm quy định về hồ sơ quản lý".

2️⃣ QUY TRÌNH HÌNH THÁP PHÁP LÝ (KHI HỎI TRÁCH NHIỆM/HỒ SƠ):
   - Bước 1 (Gốc): Trích dẫn quy định chung tại Luật PCCC.
   - Bước 2 (Cành): Cụ thể hóa tại Nghị định 105.
   - Bước 3 (Lá): Hướng dẫn biểu mẫu tại Thông tư 36.
   -> Tổng hợp thành câu trả lời mạch lạc.

3️⃣ QUY TRÌNH XỬ PHẠT (NĐ 106 & 189):
   - B1 (Tra tiền): Tìm hành vi trong NĐ 106 -> Lấy mức phạt tiền (Cá nhân & Tổ chức).
   - B2 (Tra quyền - QUAN TRỌNG): So sánh mức phạt tối đa của khung tiền với thẩm quyền:
     + Trưởng CA Xã: ...
     + Trưởng CA Huyện: ...
     + Trưởng Phòng PC07: ...
     + Giám đốc CA Tỉnh: ...
   - B3 (Kết luận): Ai là chức danh thấp nhất có đủ quyền ký phạt?

4️⃣ QUY TRÌNH QUẢN LÝ (NĐ 105):
   - B1: Kiểm tra số liệu (Diện tích, Tầng, Khối tích).
   - B2: Áp dụng QUY TẮC 70%: Công năng chính > 70% diện tích (Nếu không có -> Hỗn hợp).
   - B3: Đối chiếu Phụ lục I & II NĐ 105 -> Kết luận PC07 hay Huyện/Xã quản lý.

5️⃣ QUY TRÌNH TRANG BỊ KỸ THUẬT (QCVN 10):
   - B1: Xác định loại hình cơ sở (Kho, Xưởng, Karaoke...).
   - B2: Tra cứu Bảng quy định trong QCVN 10.
   - B3: Liệt kê hệ thống bắt buộc.
   - B4: Trích dẫn cụ thể (Ví dụ: "Theo Bảng 1, Mục 5, QCVN 10:2025").

6️⃣ CÁC CÂU HỎI KHÁC: Trả lời ngắn gọn theo văn bản (TT 37, TT 48, Công văn...).
"""

def call_gemini_expert(prompt, context):
    # Dùng Gemini 1.5 Pro hoặc Flash để có bộ nhớ lớn
    models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    
    if not context: 
        full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự, giới thiệu mình là Trợ lý PCCC PC07."
    else: 
        full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU ĐƯỢC CHỌN LỌC TỪ KHO ===\n{context}\n\n=== CÂU HỎI CỦA ĐẠI ÚY ===\n{prompt}"

    for model_name in models:
        try:
            api_key = get_random_key()
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(full_prompt)
            return response.text
        except: time.sleep(1); continue
    return "⚠️ Hệ thống đang bảo trì kết nối. Vui lòng thử lại."

# --- 5. NẠP DỮ LIỆU (QUÉT TOÀN BỘ 5 GIỎ) ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_database_final():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        db = {} 
        logs = []
        processed = set()
        
        # Từ khóa quét đủ 5 giỏ
        keywords = [
            "189", "106", "105",       # Giỏ Phạt & Quản lý
            "36", "37", "48",          # Giỏ Pháp lý & Lực lượng
            "luat", "huy dong",        # Giỏ Luật & Huy động
            "qcvn", "10:2025", "06",   # Giỏ Kỹ thuật
            "10"                       # Bắt QCVN 10 nếu tên file ngắn
        ]
        
        files = []
        for k in keywords:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and name contains '{k}'", fields="files(id, name)").execute().get('files', []))
            except: pass
        try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name)").execute().get('files', []))
        except: pass

        for f in files:
            if f['id'] in processed: continue
            processed.add(f['id'])
            
            # Lọc file rác (tránh nhầm lẫn 106 cũ)
            if "144" in f['name'] and "106" not in f['name']: continue

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
                    db[f['name']] = text
                    logs.append(f"✅ {f['name']}")
            except: continue
        return db, logs
    except Exception as e: return None, [str(e)]

# --- 6. GIAO DIỆN ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC (FULL INTELLIGENCE)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang kích hoạt toàn bộ quy trình nghiệp vụ...'):
    database, logs = load_database_final()

if not database: st.error(f"❌ Lỗi dữ liệu: {logs[0]}"); st.stop()

# Sidebar
with st.sidebar:
    st.header("TRẠNG THÁI")
    
    # Kiểm tra nhanh các file "Trụ cột"
    has_106 = any("106" in k for k in database.keys())
    has_189 = any("189" in k for k in database.keys())
    has_law = any("luat" in k.lower() for k in database.keys())
    has_36 = any("36" in k for k in database.keys())
    
    if has_106: st.success("✅ NĐ 106 (Xử phạt)")
    if has_189: st.success("✅ NĐ 189 (Thẩm quyền)")
    if has_law: st.success("✅ Luật PCCC")
    if has_36: st.success("✅ TT 36 (Hồ sơ)")
    
    with st.expander("Danh sách file"):
        for l in logs: st.text(l)

# Chat
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    with st.chat_message("assistant", avatar="🚒"):
        router_box = st.empty()
        
        # BƯỚC 1: ROUTER (THAM MƯU THÔNG MINH)
        router_box.markdown("🧠 *Đang phân tích câu hỏi để chọn tài liệu tối ưu...*")
        all_files = list(database.keys())
        selected_files_str = smart_router(prompt, all_files)
        
        # BƯỚC 2: TRÍCH XUẤT (LẤY DỮ LIỆU)
        relevant_context = ""
        used_files = []
        
        if selected_files_str:
            for fname in all_files:
                if fname in selected_files_str:
                    relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
                    used_files.append(fname)
        
        # BACKUP LOGIC (DỰ PHÒNG AN TOÀN TUYỆT ĐỐI)
        # Nếu Router AI bị lỗi, Code Python sẽ tự tay chọn file
        if not relevant_context:
            for fname, content in database.items():
                # Logic Xử phạt
                if "106" in fname and ("phạt" in prompt or "lỗi" in prompt): 
                    relevant_context += content; used_files.append(fname)
                if "189" in fname and ("ai" in prompt or "thẩm quyền" in prompt or "ký" in prompt): 
                    relevant_context += content; used_files.append(fname)
                
                # Logic Pháp lý & Trách nhiệm (Lấy Combo 3)
                if ("trách nhiệm" in prompt or "hồ sơ" in prompt) and any(x in fname for x in ["luat", "105", "36"]):
                    relevant_context += content; used_files.append(fname)
                
                # Logic Kỹ thuật
                if ("10" in fname or "qc" in fname) and ("trang bị" in prompt or "lắp" in prompt): 
                    relevant_context += content; used_files.append(fname)
                
                # Logic Lực lượng
                if "37" in fname and "đội" in prompt: 
                    relevant_context += content; used_files.append(fname)

        if used_files:
            router_box.info(f"📚 Căn cứ pháp lý: {', '.join(used_files)}")
        else:
            router_box.empty()
            
        # BƯỚC 3: TRẢ LỜI (CHUYÊN GIA FULL RULES)
        response = call_gemini_expert(prompt, relevant_context)
        
        if not used_files: router_box.empty()
        
        st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
