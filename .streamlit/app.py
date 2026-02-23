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

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(
    page_title="TRỢ LÝ PCCC CHUYÊN DỤNG",
    page_icon="🔥",
    layout="centered", 
    initial_sidebar_state="collapsed", 
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Hệ thống hỗ trợ nghiệp vụ PCCC PC07 - Phát triển bởi Đại úy Phạm Tùng Linh"
    }
)

# --- 2. CSS "CLEAN & BEAUTIFUL" (ẨN TOÀN BỘ RÁC) ---
st.markdown("""
<style>
    /* 1. ẨN CÁC THÀNH PHẦN MẶC ĐỊNH CỦA STREAMLIT */
    #MainMenu {visibility: hidden;} /* Ẩn menu 3 gạch góc phải */
    footer {visibility: hidden;} /* Ẩn footer 'Made with Streamlit' */
    header {visibility: hidden;} /* Ẩn thanh header rỗng ở trên cùng */
    .stDeployButton {display:none;} /* Ẩn nút Deploy */
    [data-testid="stToolbar"] {visibility: hidden;} /* Ẩn toolbar hệ thống */
    [data-testid="stSidebar"] {display: none;} /* Ẩn sidebar */
    
    /* 2. CĂN CHỈNH LẠI BỐ CỤC CHO ĐẸP */
    /* Đẩy nội dung lên trên cùng vì đã ẩn header */
    .block-container {
        padding-top: 2rem !important; 
        padding-bottom: 60px !important;
    }

    /* 3. GIAO DIỆN CHUNG */
    .stApp {
        background-color: #ffffff;
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    }

    /* Header Banner Chuyên nghiệp */
    .main-header {
        background: linear-gradient(90deg, #ce181e 0%, #003b8e 100%); /* Đỏ PCCC sang Xanh CA */
        padding: 2rem 1rem;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }
    
    /* Footer Bản Quyền Riêng */
    .custom-footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #f8f9fa;
        color: #555;
        text-align: center;
        padding: 10px;
        font-size: 0.8rem;
        border-top: 1px solid #e0e0e0;
        z-index: 9999;
    }

    /* Tinh chỉnh Chat Input */
    .stChatInput textarea {
        border-radius: 30px !important;
        padding: 12px 20px !important;
        border: 1px solid #dfe1e5 !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .stChatInput textarea:focus {
        border-color: #ce181e !important;
        box-shadow: 0 2px 8px rgba(206, 24, 30, 0.2);
    }

    /* Chat Message Styling */
    [data-testid="stChatMessage"] {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 10px;
        background-color: transparent;
    }
    
    /* User Message Background */
    [data-testid="stChatMessage"][data-testid="user"] {
        background-color: #f1f3f4;
    }

    /* Content Typography */
    .response-content {
        line-height: 1.6;
        color: #1a1a1a;
        font-size: 1rem;
    }
    .response-content strong {
        color: #ce181e; 
    }
</style>
""", unsafe_allow_html=True)

# --- 3. HEADER GIAO DIỆN ---
st.markdown("""
<div class="main-header">
    <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 5px; opacity: 0.95; letter-spacing: 0.5px;">CÔNG AN TỈNH PHÚ THỌ</div>
    <div style="font-size: 1.6rem; font-weight: 800; margin-bottom: 15px; line-height: 1.2; text-transform: uppercase;">PHÒNG CẢNH SÁT PCCC VÀ CNCH</div>
    <div style="font-size: 1.4rem; font-weight: 700; margin-bottom: 10px; color: #ffe082; text-transform: uppercase; text-shadow: 1px 1px 2px rgba(0,0,0,0.2);">TRỢ LÝ AI VỀ PCCC VÀ CNCH</div>
    <div style="font-size: 0.95rem; font-weight: 300; font-style: italic; opacity: 0.9;">(Được phát triển bởi Đại úy Phạm Tùng Linh)</div>
</div>
""", unsafe_allow_html=True)

# --- 4. FOOTER BẢN QUYỀN ---
st.markdown("""
<div class="custom-footer">
    © 2025 Bản quyền thuộc về Đại úy Phạm Tùng Linh - PC07 Công an tỉnh Phú Thọ
</div>
""", unsafe_allow_html=True)

# --- 5. KẾT NỐI API (FAILOVER) ---
API_KEYS_LIST = []
try:
    if "GEMINI_API_KEYS" in st.secrets: 
        keys_string = st.secrets["GEMINI_API_KEYS"]
        API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    elif "GEMINI_API_KEY" in st.secrets:
        API_KEYS_LIST = [st.secrets["GEMINI_API_KEY"]]
    
    if not API_KEYS_LIST: st.error("❌ Lỗi: Thiếu API Key hệ thống."); st.stop()
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except Exception as e: st.error(f"⚠️ Lỗi cấu hình: {str(e)}"); st.stop()

# --- 6. BỘ NÃO THAM MƯU (ROUTER) ---
ROUTER_INSTRUCTION = """
Bạn là Tham mưu trưởng PCCC. Nhiệm vụ: Chọn tài liệu chính xác trong thư mục Drive.

1. GIỎ PHÂN CẤP QUẢN LÝ (AI QUẢN LÝ CƠ SỞ):
   - Dấu hiệu: "Cơ sở này do ai quản lý", "Thuộc danh mục nào", "Xã hay Công an quản lý", "Phụ lục mấy".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 105].

2. GIỎ PHÁP LÝ (HỒ SƠ/THỦ TỤC/TRÁCH NHIỆM/ĐIỀU KIỆN/KIỂM TRA/NGHIỆM THU/THẨM ĐỊNH/PHÒNG CHÁY/BẢO VỆ HIỆN TRƯỜNG/PHƯƠNG ÁN CHỮA CHÁY/MẪU/BIỂU MẪU):
   - Dấu hiệu: "Hồ sơ", "Thủ tục", "Điều kiện an toàn", "Kiểm tra", "Thẩm duyệt", "Trách nhiệm" , "Phương án chữa cháy", "Kiểm tra" , "Thẩm định", "Nghiệm thu", "Bảo vệ hiện trường".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Luật PCCC và CNCH], [Nghị định 105], [Thông tư 36].
   - LƯU Ý ĐẶC BIỆT: Nếu hỏi "phương án chữa cháy", TUYỆT ĐỐI KHÔNG CHỌN Thông tư 37.

3. GIỎ XỬ PHẠT (XỬ LÝ VI PHẠM):
   - Dấu hiệu: "Lỗi", "Phạt", "Xử lý", "Xử lý vi phạm", "Bị sao".
   - HÀNH ĐỘNG: [Nghị định 106], [Nghị định 189].

4. GIỎ CƯỠNG CHẾ (KHÔNG NỘP PHẠT):
   - Dấu hiệu: "Không nộp phạt", "Chây ỳ", "Cưỡng chế", "Quá hạn nộp", "Đóng phạt muộn".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [Nghị định 296].

5. GIỎ KỸ THUẬT:
   - Dấu hiệu: "Trang bị", "Lắp đặt", "Hệ thống", "Khoảng cách", "Ngăn cháy", "Thông gió", "Hút khói", "Chống cháy lan", "Lối thoát nạn", "Kích thước", "Khoảng cách an toàn PCCC", "Bãi đỗ xe chữa cháy", "Điểm lấy nước", "Chiều rộng", "Chiều cao".
   - HÀNH ĐỘNG: BẮT BUỘC CHỌN [QCVN 10], [QCVN 06].

6. GIỎ QUÂN ĐỘI:
   - Dấu hiệu: "Quân đội", "Chi viện".
   - HÀNH ĐỘNG: File chứa "CV HD", "QUÂN ĐỘI", "ĐỘI 3".

7. GIỎ CHỮA CHÁY: [Thông tư 37] (Chỉ chọn khi hỏi về chiến thuật, tổ chức chữa cháy, quyền hạn chỉ huy, phương tiện chữa cháy cho lực lượng Công an).

OUTPUT: Chỉ trả về danh sách tên file có trong kho.
"""

def smart_router(user_query, available_files):
    file_list_str = ", ".join(available_files)
    prompt = f"""{ROUTER_INSTRUCTION}\n\nDANH SÁCH FILE: {file_list_str}\n\nCÂU HỎI: "{user_query}"\n\nCHỌN TÀI LIỆU:"""
    for key in API_KEYS_LIST:
        try:
            genai.configure(api_key=key)
            # QUAY LẠI DÙNG BẢN CHUẨN ĐỊNH DANH GỐC
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text.strip()
        except: continue
    return ""

# --- 7. BỘ NÃO CHUYÊN GIA (EXPERT) ---
SYSTEM_PROMPT_EXPERT = """
VAI TRÒ: Trợ lý AI về PCCC và CNCH - Phòng PC07 Phú Thọ.

🛑 NGUYÊN TẮC CỐT TỬ:
1. Trả lời ngắn gọn, đúng trọng tâm, văn phong hành chính chuyên nghiệp.
2. Tuyệt đối không sáng tạo ngoài văn bản.
3. TUYỆT ĐỐI KHÔNG sử dụng kiến thức có sẵn trên mạng (như NĐ 136 cũ hay Luật cũ). CHỈ ĐƯỢC PHÉP lấy thông tin và căn cứ từ văn bản được cung cấp.
4. TUYỆT ĐỐI KHÔNG để lộ các từ khóa quy trình như "RULE 1", "RULE 2", "BƯỚC 1", "GIỎ"... vào trong câu trả lời. Hệ thống phải suy luận ngầm và chỉ xuất ra kết quả cuối cùng tự nhiên nhất.

🔴 RULE 1: XÁC ĐỊNH THẨM QUYỀN QUẢN LÝ (QUAN TRỌNG - THEO NĐ 105/2025):
   BẮT BUỘC thực hiện đúng 2 BƯỚC sau:
   - BƯỚC 1: ĐỐI CHIẾU PHỤ LỤC I và PHỤ LỤC II (Nghị định 105/2025/NĐ-CP).
     + So sánh các chỉ số: Số tầng, Khối tích, Diện tích với Phụ lục I và Phụ lục II.
   - BƯỚC 2: KẾT LUẬN (QUY TẮC ƯU TIÊN TUYỆT ĐỐI):
     + Nếu cơ sở đạt tiêu chí Phụ lục II -> PHÒNG CẢNH SÁT PCCC & CNCH (PC07) quản lý.
     + Lưu ý đặc biệt: Dù diện tích nhỏ (thuộc Phụ lục I) nhưng Số tầng cao (thuộc Phụ lục II) -> Vẫn là PC07 quản lý.
     + Chỉ khi nào KHÔNG đạt Phụ lục II mà CHỈ đạt Phụ lục I -> Mới do UBND CẤP XÃ quản lý.

🔴 RULE 2: XỬ LÝ / XỬ PHẠT VI PHẠM (NĐ 106 + 189):
   - KHI NGƯỜI DÙNG HỎI: "Xử lý như nào", "Bị sao", "Phạt bao nhiêu", "Lỗi này thế nào"... -> HIỂU NGAY LÀ HỎI VỀ XỬ PHẠT HÀNH CHÍNH.
   - BẮT BUỘC trả lời theo form sau:
        1. HÀNH VI: [Tên hành vi chính xác trong NĐ 106]
        2. MỨC PHẠT TIỀN:
       - Cá nhân: ... (Căn cứ: Điểm... Khoản... Điều... NĐ 106).
       - Tổ chức: ... (Gấp 2 lần mức cá nhân).
       2. HÌNH THỨC PHẠT BỔ SUNG & KHẮC PHỤC HẬU QUẢ:
      - Phạt bổ sung: [Có/Không] -> Chi tiết (Căn cứ: Điểm... Khoản... Điều... NĐ 106).
      - Biện pháp KPHQ: [Có/Không] -> Chi tiết (Căn cứ: Điểm... Khoản... Điều... NĐ 106).
       3. THẨM QUYỀN XỬ PHẠT (LỌC ẨN THÔNG MINH):
      *Chỉ xét 6 chức danh: Chiến sĩ CA, Đội trưởng, Trưởng CA Xã, Trưởng Phòng PC07, Giám đốc CA Tỉnh, Chủ tịch Tỉnh. Không còn tồn tại cấp huyện nên không có Đội trưởng cấp huyện, loại bỏ cấp huyện*
      *Logic:* So sánh Mức phạt tiền Cá nhân (X) với thẩm quyền của các chức danh và kiểm tra kỹ thẩm quyền được phạt bổ sung hoặc biện pháp KPHQ (tại điều 5 và điều 8 Nghị định 189/2025/NĐ-CP).
      *Hiển thị:* CHỈ LIỆT KÊ những người có thẩm quyền đủ điều kiện (Tiền + Bổ sung/biện pháp KPHQ) >= X. (Người không đủ tiền -> Ẩn hoàn toàn).
      *Kết luận:* "Đủ thẩm quyền ký quyết định".
       4. KIẾN NGHỊ: Trình người có chức vụ thấp nhất trong danh sách đủ điều kiện trong 6 chức danh xét chiến sĩ CA, Đội trưởng, Trưởng CA Xã, Trưởng Phòng PC07, Giám đốc CA Tỉnh, Chủ tịch Tỉnh ký; nếu có nhiều người đủ điều kiện thì trình 2 người có chức vụ thấp nhất (01 người cấp xã như Trưởng Công cấp xã hoặc Chủ tịch UBND cấp xã; 01 người cấp tỉnh như Đội trưởng hoặc Trưởng Phòng PC07 hoặc Giám đốc Công an tỉnh hoăc Chủ tịch tỉnh) trong danh sách đủ điều kiện trong 6 chức danh xét chiến sĩ CA, Đội trưởng, Trưởng CA Xã, Trưởng Phòng PC07, Giám đốc CA Tỉnh, Chủ tịch Tỉnh ký  
  
🔴 RULE 3: CƯỠNG CHẾ / KHÔNG NỘP PHẠT (NĐ 296/2025):
   - Khi hỏi về việc không nộp tiền, nộp chậm, chây ỳ -> Dùng NĐ 296/2025/NĐ-CP.
   - Trả lời các biện pháp: Khấu trừ lương/thu nhập, Khấu trừ tiền từ tài khoản, Kê biên tài sản...

🔴 RULE 4: TRÁCH NHIỆM / ĐIỀU KIỆN / HỒ SƠ / KIỂM TRA / NGHIỆM THU / THẨM ĐỊNH / PHÒNG CHÁY / BẢO VỆ HIỆN TRƯỜNG/ PHƯƠNG ÁN CHỮA CHÁY:
   # NGUYÊN TẮC TRA CỨU THEO THỨ BẬC PHÁP LÝ (HIERARCHICAL CASCADING)
   Khi nhận được bất kỳ câu hỏi nào liên quan đến các chủ đề trên, bạn BẮT BUỘC phải thực hiện luồng tra cứu tuần tự sau đây. Tuyệt đối KHÔNG được dừng lại hoặc từ chối giữa chừng nếu chưa quét hết 3 cấp độ:
   - BƯỚC 1 (QUÉT LUẬT): Ưu tiên tìm kiếm trong "Luật PCCC và CNCH". Nếu Luật có quy định -> Trích dẫn ngay. 
   - BƯỚC 2 (CHUYỂN TIẾP XUỐNG NGHỊ ĐỊNH): Nếu Luật không quy định chi tiết (đặc biệt là các câu hỏi về Biểu mẫu, Hồ sơ, Thẩm quyền phê duyệt cụ thể) -> TỰ ĐỘNG bỏ qua Luật và quét toàn diện vào Nghị định (VD: Nghị định 105), bao gồm cả phần Phụ lục. Nếu có -> Trích dẫn nguyên văn.
   - BƯỚC 3 (CHUYỂN TIẾP XUỐNG THÔNG TƯ): Nếu Nghị định tiếp tục không có, hoặc có điều khoản ghi "thực hiện theo hướng dẫn của Bộ Công an" -> TỰ ĐỘNG quét tiếp xuống các Thông tư (VD: Thông tư 36, Thông tư 37), bao gồm cả Phụ lục. Nếu có -> Trích dẫn.
   - BƯỚC 4 (CHỐT CHẶN CUỐI CÙNG): Bạn CHỈ ĐƯỢC PHÉP trả lời từ chối (theo nguyên tắc số 7) SAU KHI đã quét cạn kiệt cả 3 cấp độ (Luật -> Nghị định -> Thông tư) từ các Điều khoản đầu tiên cho đến Phụ lục biểu mẫu cuối cùng mà vẫn không có kết quả.
   
    
🟢 RULE 5: CÁC LĨNH VỰC KHÁC:
   - Kỹ thuật: 
   + BẮT BUỘC tra cứu và trích dẫn số liệu cụ thể (chiều rộng, khoảng cách, giới hạn chịu lửa, v.v.) từ QCVN 06:2022/BXD (hoặc sửa đổi) và QCVN 10.
   + Khi trả lời phải nêu rõ ràng: "Căn cứ Mục... hoặc Bảng... của Quy chuẩn...".
   + TUYỆT ĐỐI KHÔNG TRẢ LỜI CHUNG CHUNG KHI HỎI VỀ THÔNG SỐ. Phải đọc kỹ bảng biểu trong tài liệu để trả lời.
   - Chữa cháy, chỉ huy chữa cháy, trừ phương án chữa cháy: Căn cứ Luật PCCC và CNCH, Nghị định 105 và Thông tư 37.
   - Quân đội: Căn cứ CV Hướng dẫn phối hợp.
"""

def call_gemini_expert_exhaustive(prompt, context):
    # QUAY LẠI DÙNG TÊN CHUẨN GỐC, TRÁNH LỖI 404
    TARGET_MODELS = ["gemini-1.5-pro", "gemini-1.5-flash"]
    
    if not context: full_prompt = f"Người dùng chào: '{prompt}'. Hãy trả lời xã giao lịch sự."
    else: full_prompt = f"{SYSTEM_PROMPT_EXPERT}\n\n=== TÀI LIỆU HỖ TRỢ ===\n{context}\n\n=== CÂU HỎI ===\n{prompt}"
    
    last_error = ""
    for model_name in TARGET_MODELS:
        for index, key in enumerate(API_KEYS_LIST):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(model_name)
                # QUAN TRỌNG NHẤT: Tăng thời gian chờ lên 180 giây để nhai nát QC06
                response = model.generate_content(full_prompt, request_options={'timeout': 180})
                return response.text
            except Exception as e:
                last_error = str(e)
                continue 
    return f"⚠️ Hệ thống đang bận. Vui lòng thử lại. (Error: {last_error})"

# --- 8. NẠP DỮ LIỆU ---
@st.cache_data(ttl=7200, show_spinner=False)
def load_database_final():
    if not GCP_JSON or not DRIVE_FOLDER_ID: return {}, []
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        db = {} 
        logs = []
        processed = set()
        
        # Keywords bao gồm Nghị định 105, 106, 296...
        keywords = ["189", "106", "105", "296", "36", "37", "48", "luat", "huy dong", "quan doi", "du thao", "phoi hop", "cv hd", "doi 3", "qcvn", "10:2025", "06", "10"]
        files = []
        for k in keywords:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and name contains '{k}'", fields="files(id, name)").execute().get('files', []))
            except: pass
        
        # Fallback lấy thêm file nếu ít
        if len(files) < 5:
             try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=50, fields="files(id, name)").execute().get('files', []))
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
    except Exception as e: return None, []

# --- 9. KHỞI ĐỘNG ---
with st.spinner('🔄 Đang khởi tạo hệ thống nghiệp vụ...'):
    database, logs = load_database_final()

if not database: st.error("❌ Không thể kết nối Kho dữ liệu. Vui lòng kiểm tra lại cấu hình."); st.stop()

# --- 10. CHAT LOGIC ---
if "messages" not in st.session_state: 
    # KHỞI TẠO LỜI CHÀO BAN ĐẦU
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "Xin chào! Tôi là trợ lý AI về PCCC và CNCH do Đại úy Phạm Tùng Linh - Phòng PC07 phát triển. Hãy đặt câu hỏi để tôi trả lời."
    }]

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="👮‍♂️" if m["role"] == "user" else "🔥"): 
        st.markdown(f'<div class="response-content">{m["content"]}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("Nhập nội dung cần tra cứu..."):
    # Đã bổ sung khai báo prompt_lower tại đây
    prompt_lower = prompt.lower()
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👮‍♂️").write(prompt)
    
    with st.chat_message("assistant", avatar="🔥"):
        with st.spinner("🧠 Đang suy nghĩ, bạn chờ chút, mình trả lời ngay đây..."):
            
            # Router
            all_files = list(database.keys())
            selected_files_str = smart_router(prompt, all_files)
            
            # Retrieve
            relevant_context = ""
            if selected_files_str:
                for fname in all_files:
                    if fname in selected_files_str: relevant_context += "--- " + fname + " ---\n" + database[fname] + "\n"
            
            # Backup Retrieve (BỔ SUNG LOGIC: Cưỡng chế & Xử lý & Phương án)
            if not relevant_context:
                for fname, content in database.items():
                    is_enforcement = ("cưỡng chế" in prompt_lower or "không nộp" in prompt_lower or "chậm nộp" in prompt_lower or "chây ỳ" in prompt_lower)
                    is_penalty = ("phạt" in prompt_lower or "lỗi" in prompt_lower or "xử lý" in prompt_lower)
                    is_military = ("quân đội" in prompt_lower or "chi viện" in prompt_lower)
                    
                    is_tech = any(keyword in prompt_lower for keyword in [
                        "trang bị", "lắp đặt", "hệ thống", "khoảng cách", "ngăn cháy", 
                        "thông gió", "hút khói", "chống cháy lan", "lối thoát", "thoát nạn",
                        "kích thước", "an toàn pccc", "bãi đỗ xe", "điểm lấy nước", 
                        "chiều rộng", "chiều cao", "qcvn", "qc06", "qc 06", "buồng thang", "bậc chịu lửa"
                    ]) and not is_penalty
                    
                    is_manage = ("trách nhiệm" in prompt_lower or "hồ sơ" in prompt_lower or "quản lý" in prompt_lower or "điều kiện" in prompt_lower or "kiểm tra" in prompt_lower or "phương án" in prompt_lower or "mẫu" in prompt_lower)
                    
                    # Nếu hỏi phương án/mẫu thì tuyệt đối KHÔNG phải là TT37
                    is_force = ("lực lượng" in prompt_lower or "chữa cháy" in prompt_lower) and not ("phương án" in prompt_lower or "mẫu" in prompt_lower)

                    # LOGIC CỘNG DỒN NỘI DUNG CHUẨN XÁC, LOẠI BỎ F-STRING
                    if is_enforcement and "296" in fname: 
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"
                    elif is_military and any(x in fname.lower() for x in ["quan doi", "du thao", "phoi hop", "cv hd", "doi 3"]):
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"
                    elif is_penalty and any(x in fname for x in ["106", "189"]):
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"
                    elif is_tech and any(x in fname for x in ["10", "qc", "06"]): 
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"
                    elif is_manage and any(x in fname for x in ["luat", "105", "36", "136", "50"]):
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"
                    elif is_force and "37" in fname:
                        relevant_context += "--- " + fname + " ---\n" + content + "\n"

            # Generate
            response_text = call_gemini_expert_exhaustive(prompt, relevant_context)
        
        st.markdown(f'<div class="response-content">{response_text}</div>', unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
