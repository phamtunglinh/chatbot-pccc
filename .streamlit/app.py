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

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="PCCC PC07 (Final Logic)", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1.5rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;}
    .stChatInput {border-radius: 20px;}
    .router-box {background-color: #e3f2fd; padding: 10px; border-radius: 5px; border-left: 5px solid #2196f3; margin-bottom: 10px; font-size: 0.9em;}
    .success-box {background-color: #e8f5e9; padding: 5px; border-radius: 5px; font-size: 0.8em; color: #2e7d32; margin-top: 5px;}
</style>
""", unsafe_allow_html=True)

# --- 2. KẾT NỐI API (FAILOVER - TUẦN TỰ) ---
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

# --- 3. BỘ NÃO THAM MƯU (ROUTER - ĐÃ CẬP NHẬT RULE MỚI) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: Chọn tài liệu "TỐI GIẢN NHƯNG ĐÚNG TRỌNG TÂM".

1. GIỎ PHÁP LÝ - QUẢN LÝ (TRÁCH NHIỆM / ĐIỀU KIỆN / HỒ SƠ / KIỂM TRA):
   - Dấu hiệu: "Trách nhiệm người đứng đầu", "Điều kiện an toàn", "Hồ sơ gồm gì", "Thủ tục", "Kiểm tra an toàn", "Thẩm duyệt", "Nghiệm thu".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Luật PCCC và CNCH], [Nghị định 105], [Thông tư 36].

2. GIỎ CÔNG TÁC CHỮA CHÁY (LỰC LƯỢNG):
   - Dấu hiệu: "Việc chữa cháy", "Nhiệm vụ chữa cháy", "Tổ chức chữa cháy", "Đội PCCC cơ sở".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Thông tư 37] (và [Thông tư 48] nếu hỏi trang phục).

3. GIỎ KỸ THUẬT (TRANG BỊ / HỆ THỐNG):
   - Dấu hiệu: "Cần trang bị gì?", "Lắp hệ thống nào?", "Bình chữa cháy", "Báo cháy", "Khoảng cách".
   - HÀNH ĐỘNG: CHỈ CHỌN [QCVN 10] (và [QCVN 06] nếu cần).

4. GIỎ HUY ĐỘNG (QUÂN ĐỘI / PHỐI HỢP):
   - Dấu hiệu: "Quân đội", "Chi viện", "Phối hợp", "Đội 3".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN file [CV HD CÔNG TÁC CC&CNCH PHỐI HỢP QUÂN ĐỘI...].

5. GIỎ XỬ PHẠT (LỖI / TIỀN / THẨM QUYỀN):
   - Dấu hiệu: "Lỗi", "Phạt bao nhiêu", "Xử lý", "Bị sao".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 106] (Tiền) VÀ [Nghị định 189] (Thẩm quyền).
   - CẤM CHỌN: Luật, NĐ 105, TT 36 (trừ khi hỏi kèm hồ sơ).

OUTPUT: Chỉ trả về danh sách tên file có trong kho, ngăn cách bằng dấu phẩy.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE HIỆN CÓ: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    
    # Router dùng Key 1 (hoặc key đầu tiên sống) và model nhẹ để phản hồi nhanh
    for key in API_KEYS_LIST:
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text.strip()
        except: continue
    return ""

# --- 4. BỘ NÃO CHUYÊN GIA (EXPERT - TÍCH HỢP TOÀN BỘ RULE) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Đại úy Phạm Tùng Linh - Chuyên gia Pháp chế PCCC PC07 Phú Thọ.

🛑 NGUYÊN TẮC VÀNG:
1. TUYỆT ĐỐI KHÔNG trả lời chung chung.
2. MỌI con số, nhận định ĐỀU PHẢI CÓ TRÍCH DẪN: "...(Căn cứ: Điểm..., Khoản..., Điều..., Văn bản...)".
3. Nếu thiếu dữ liệu (Diện tích, Tầng, Khối tích) -> HỎI NGƯỢC LẠI NGƯỜI DÙNG.

🔴 RULE 1: SUY LUẬN VỀ TRÁCH NHIỆM / ĐIỀU KIỆN / HỒ SƠ / KIỂM TRA:
   - Căn cứ: Tổng hợp từ Luật PCCC và CNCH (Quy định chung) -> Nghị định 105 (Chi tiết điều kiện) -> Thông tư 36 (Biểu mẫu, hồ sơ cụ thể).
   - Trả lời phải nêu rõ: Đối tượng này cần điều kiện gì (theo NĐ 105) và Hồ sơ cần mẫu nào (theo TT 36).

🟢 RULE 2: SUY LUẬN VỀ CÔNG TÁC CHỮA CHÁY:
   - Căn cứ: Thông tư 37.
   - Trả lời về: Nhiệm vụ, quyền hạn, tổ chức đội hình, phương án chữa cháy.

🔴 RULE 3: SUY LUẬN XỬ PHẠT (NĐ 106 + 189) - LOGIC CHẶT CHẼ:
   BẮT BUỘC TRÌNH BÀY THEO FORM SAU:
   1. Hành vi và mức tiền phạt:
      - Mức phạt Cá nhân: X đồng (Căn cứ NĐ 106).
      - Mức phạt Tổ chức: 2 * X đồng.
   2. Phạt bổ sung & KPHQ: [Có/Không] -> Chi tiết.
   3. Xét thẩm quyền (QUAN TRỌNG: CHỈ XÉT THEO MỨC CÁ NHÂN X):
      *Chỉ xét danh sách: Chiến sĩ CA, Đội trưởng, Trưởng CA Xã, Trưởng Phòng PC07, Giám đốc CA Tỉnh, Chủ tịch Tỉnh.*
      - Xét [Chức danh A]: 
        + Thẩm quyền tiền: ... (So sánh với X).
        + Thẩm quyền Bổ sung/KPHQ: ...
        => Kết luận: Đủ thẩm quyền hay không.
      - Xét [Chức danh B]: ...
   4. Đề xuất: Trình người có chức vụ thấp nhất đủ điều kiện.

🟢 RULE 4: SUY LUẬN THẨM QUYỀN QUẢN LÝ (NĐ 105 / NĐ 50):
   - B1: Kiểm tra dữ liệu.
   - B2: Xác định công năng chính (Quy tắc 70%).
   - B3: Đối chiếu Phụ lục (I, II, III...).
   - B4: Kết luận (Phụ lục II -> PC07; Chỉ Phụ lục I -> Xã).

🔵 RULE 5: SUY LUẬN KỸ THUẬT (TRANG BỊ):
   - Chỉ căn cứ QCVN 10.

🟣 RULE 6: SUY LUẬN HUY ĐỘNG QUÂN ĐỘI:
   - Căn cứ: CV HD CÔNG TÁC CC&CNCH PHỐI HỢP QUÂN ĐỘI (Dự thảo).
"""

def call_gemini_expert_exhaustive(prompt, context):
    # DANH SÁCH MODEL MỤC TIÊU (Ưu tiên bản mạnh nhất)
    TARGET_MODELS = [
        "gemini-2.5-flash",       # Ưu tiên 1
        "gemini-2.0-flash",       # Ưu tiên 2
        "gemini-2.0-flash-exp",   # Ưu tiên 3
        "gemini-1.5-pro",         # Ưu tiên 4
        "gemini-1.5-flash"        # Ưu tiên 5
    ]
    
    if not context: 
        full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: 
        full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"

    last_error = ""
    
    # CHIẾN THUẬT FAILOVER:
    # Vòng ngoài: Duyệt Model.
    # Vòng trong: Duyệt Key (Từ Key 1 -> Key n).
    
    for model_name in TARGET_MODELS:
        for index, key in enumerate(API_KEYS_LIST):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(model_name)
                
                # Timeout 60s
                response = model.generate_content(full_prompt, request_options={'timeout': 60})
                
                # Nếu chạy được -> Trả về ngay
                return response.text, model_name, index + 1
                
            except Exception as e:
                last_error = str(e)
                continue 
    
    return f"⚠️ Hệ thống quá tải (Đã thử hết Key & Model). Lỗi cuối: {last_error}", "None", 0

# --- 5. NẠP DỮ LIỆU (QUÉT TOÀN BỘ TỪ KHÓA) ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_database_final():
    if not GCP_JSON or not DRIVE_FOLDER_ID: return {}, ["⚠️ Chưa cấu hình Drive"]
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        db = {} 
        logs = []
        processed = set()
        
        # KEYWORDS CHO TOÀN BỘ CÁC GIỎ
        keywords = [
            "189", "106", "105", "50", # Phạt & Quản lý
            "36", "37", "48",          # Pháp lý & Lực lượng & Chữa cháy
            "luat", "huy dong",        # Luật & Huy động
            "quan doi", "du thao", "phoi hop", # QUÂN ĐỘI
            "qcvn", "10:2025", "06",   # Kỹ thuật
            "10"
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

# --- 6. GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><p style="font-size: 26px; margin:0">TRỢ LÝ PCCC (FINAL LOGIC)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang khởi động...'):
    database, logs = load_database_final()

if not database: st.error(f"❌ Lỗi dữ liệu: {logs[0]}"); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ CẤU HÌNH")
    st.success(f"🔑 Đã nạp: **{len(API_KEYS_LIST)} API Key**")
    st.info("💡 Cơ chế: Failover (Dự phòng).")
    
    st.divider()
    st.header("KHO DỮ LIỆU")
    with st.expander("Chi tiết file"):
        for l in logs: st.text(l)

# Chat
if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👤" if m["role"] == "user" else "🚒"): 
        st.markdown(m["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    with st.chat_message("assistant", avatar="🚒"):
        router_box = st.empty()
        
        # BƯỚC 1: ROUTER
        router_box.markdown("🧠 *Đang phân tích...*")
        all_files = list(database.keys())
        selected_files_str = smart_router(prompt, all_files)
        
        # BƯỚC 2: TRÍCH XUẤT (BACKUP LOGIC)
        relevant_context = ""
        used_files = []
        if selected_files_str:
            for fname in all_files:
                if fname in selected_files_str:
                    relevant_context += f"--- VĂN BẢN: {fname} ---\n{database[fname]}\n"
                    used_files.append(fname)
        
        # BACKUP LOGIC (Phòng hờ Router AI sai)
        if not relevant_context:
            for fname, content in database.items():
                is_penalty = ("phạt" in prompt or "lỗi" in prompt or "xử lý" in prompt)
                is_military = ("quân đội" in prompt or "chi viện" in prompt or "phối hợp" in prompt)
                is_tech = ("trang bị" in prompt or "lắp" in prompt or "hệ thống" in prompt)
                is_manage = ("trách nhiệm" in prompt or "hồ sơ" in prompt or "điều kiện" in prompt or "kiểm tra" in prompt)
                is_force = ("lực lượng" in prompt or "chữa cháy" in prompt or "nhiệm vụ" in prompt)

                # Logic Quân đội
                if is_military and any(x in fname for x in ["quan doi", "du thao", "phoi hop"]):
                     relevant_context += content; used_files.append(fname)
                # Logic Xử phạt: Chỉ lấy 106, 189
                elif is_penalty and any(x in fname for x in ["106", "189"]):
                     relevant_context += content; used_files.append(fname)
                # Logic Kỹ thuật: Chỉ QC 10, 06
                elif is_tech and any(x in fname for x in ["10", "qc", "06"]) and not is_penalty: 
                    relevant_context += content; used_files.append(fname)
                # Logic Pháp lý/Quản lý (MỚI): Luật, 105, 36
                elif is_manage and any(x in fname for x in ["luat", "105", "36"]):
                    relevant_context += content; used_files.append(fname)
                # Logic Chữa cháy (MỚI): TT 37
                elif is_force and "37" in fname:
                    relevant_context += content; used_files.append(fname)

        if used_files:
            st.markdown(f'<div class="router-box">📚 <b>AI Tham mưu đã chọn:</b><br>{", ".join(used_files)}</div>', unsafe_allow_html=True)
            router_box.empty()
        else: router_box.empty()
            
        # BƯỚC 3: TRẢ LỜI
        response_text, used_model, used_key_idx = call_gemini_expert_exhaustive(prompt, relevant_context)
        
        st.markdown(response_text)
        
        if used_model != "None":
            st.markdown(f"""
            <div class="success-box">
            ✅ Kết nối thành công!<br>
            - Model: <b>{used_model}</b><br>
            - API Key: <b>Số {used_key_idx}</b> (Failover)
            </div>
            """, unsafe_allow_html=True)
        
        st.session_state.messages.append({"role": "assistant", "content": response_text})
