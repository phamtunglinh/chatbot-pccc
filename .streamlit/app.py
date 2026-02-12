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
st.set_page_config(page_title="Trợ lý PCCC (Optimized)", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1rem; color: white; text-align: center; margin-top: -50px; border-radius: 0 0 15px 15px;}</style>""", unsafe_allow_html=True)

# --- 2. KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_string = st.secrets["GEMINI_API_KEYS"]
    else: keys_string = st.secrets["GEMINI_API_KEY"]
    API_KEYS_LIST = [k.strip() for k in keys_string.split(",") if k.strip()]
    DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("⚠️ Lỗi cấu hình Secrets."); st.stop()

def get_random_key(): return random.choice(API_KEYS_LIST)

# --- 3. BỘ NÃO TINH GỌN (STRUCTURED PROMPT) ---
# Viết dạng cấu trúc rõ ràng, bỏ văn xuôi thừa thãi
ALGORITHMS_INSTRUCTION = """
VAI TRÒ: Chuyên gia Pháp chế PCCC Phạm Tùng Linh.

DỮ LIỆU ĐƯỢC CẤP (Ưu tiên theo thứ tự):
1. THẨM QUYỀN: Nghị định 189/2025.
2. MỨC PHẠT: Nghị định 106/2025.
3. QUẢN LÝ: Nghị định 105/2025.
4. KỸ THUẬT: QCVN 10, QCVN 06.

🎯 NHIỆM VỤ: Trả lời câu hỏi dựa trên quy trình sau:

=== CASE 1: HỎI VỀ XỬ PHẠT (Lỗi, Tiền, Ai ký?) ===
- BƯỚC 1 (Mapping): Dịch ngôn ngữ đời thường sang luật (NĐ 106).
  + "Không có" -> Tìm "Không lập", "Không trang bị".
  + "Thiếu" -> Tìm "Không đầy đủ".
- BƯỚC 2 (Tra cứu Tiền): Tìm hành vi trong NĐ 106 -> Lấy mức phạt Cá nhân/Tổ chức.
- BƯỚC 3 (Tra cứu Quyền - QUAN TRỌNG): 
  + So sánh mức phạt tối đa với quyền hạn trong NĐ 189.
  + Logic: Trưởng CA Xã < Trưởng CA Huyện < Trưởng PC07 < Giám đốc CA Tỉnh.
  + Chọn người có thẩm quyền thấp nhất nhưng ĐỦ mức tiền phạt.
- BƯỚC 4 (Output): Trả lời theo mẫu:
  1. Hành vi vi phạm: ...
  2. Mức phạt tiền: ... (Căn cứ NĐ 106).
  3. Thẩm quyền xử phạt: ... (Căn cứ NĐ 189).

=== CASE 2: HỎI VỀ QUẢN LÝ (Ai quản lý cơ sở này?) ===
- BƯỚC 1: Xác định Công năng chính (Quy tắc 70% diện tích).
- BƯỚC 2: Kiểm tra Phụ lục II (NĐ 105).
  + Có tên trong Phụ lục II -> PC07 quản lý.
  + Không có trong II (chỉ có I) -> Công an Huyện/Xã.

=== CASE 3: HỎI VỀ KỸ THUẬT ===
- Tra cứu Bảng biểu trong QCVN 10 -> Trả lời ngắn gọn.

⚠️ YÊU CẦU BẮT BUỘC:
- Tuyệt đối không trả lời chung chung. Phải có trích dẫn (Điều, Khoản).
- Nếu dữ liệu có NĐ 189, KHÔNG ĐƯỢC nói là không biết ai có quyền xử phạt.
"""

# --- 4. HÀM GỌI AI (CƠ CHẾ SMART RETRY) ---
def call_gemini_logic(prompt, context):
    # Cơ chế giảm tải thông minh: Nếu lỗi, tự động cắt ngắn bớt phần ít quan trọng
    sizes = [400000, 200000, 100000] 
    models = ["gemini-1.5-flash", "gemini-2.0-flash"]
    
    for size in sizes:
        current_ctx = context[:size]
        full_prompt = f"DỮ LIỆU PHÁP LÝ:\n{current_ctx}\n\nCÂU HỎI: {prompt}"
        
        for _ in range(2):
            api_key = get_random_key()
            for model in models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": full_prompt}]}],
                        "system_instruction": {"parts": [{"text": ALGORITHMS_INSTRUCTION}]},
                        "safetySettings": [{"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"}]
                    }
                    response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
                    if response.status_code == 200:
                        return response.json()['candidates'][0]['content']['parts'][0]['text']
                except: continue
    return "⚠️ Hệ thống đang quá tải. Vui lòng thử lại."

# --- 5. ĐỌC DỮ LIỆU (ƯU TIÊN TUYỆT ĐỐI) ---
@st.cache_data(ttl=7200, show_spinner=False) 
def load_data_optimized():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        
        buckets = {"phap_ly": [], "xu_phat": [], "quy_chuan": [], "khac": []}
        log_ok = []
        processed_ids = set()

        # 1. SĂN TÌM "VIP" (Nạp 189 và 106 trước tiên)
        queries = ["name contains '189'", "name contains '106'", "name contains '105'", "name contains '10'"]
        files = []
        for q in queries:
            try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false and {q}", fields="files(id, name)").execute().get('files', []))
            except: pass
            
        # 2. LẤY CÁC FILE CÒN LẠI (Giới hạn 200 file mới nhất để nhẹ máy)
        try: files.extend(service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false", pageSize=200, fields="files(id, name)").execute().get('files', []))
        except: pass

        for file in files:
            if file['id'] in processed_ids: continue
            processed_ids.add(file['id'])
            fname = file['name'].lower()
            
            # Lọc rác (144, 136)
            if "144" in fname and "106" not in fname and "189" not in fname: continue
            if "136" in fname and "105" not in fname: continue
            
            try:
                # Chỉ lấy text thô để nhẹ bộ nhớ (Bỏ qua định dạng phức tạp)
                content = ""
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, service.files().get_media(fileId=file['id']))
                done = False
                while done is False: _, done = downloader.next_chunk()
                fh.seek(0)
                
                if fname.endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs])
                    # Gom bảng biểu thành text đơn giản
                    for t in doc.tables:
                        for r in t.rows: content += " | ".join([c.text.strip() for c in r.cells]) + "\n"
                
                if content:
                    item = f"[{file['name']}]:\n{content}\n---\n"
                    if any(x in fname for x in ["106", "189", "xu phat"]): 
                        buckets["xu_phat"].append(item)
                        log_ok.append(f"⚖️ {file['name']}")
                    elif any(x in fname for x in ["105", "nghi dinh"]):
                        buckets["phap_ly"].append(item)
                        log_ok.append(f"🔹 {file['name']}")
                    elif "qc" in fname or "10:2025" in fname:
                        buckets["quy_chuan"].append(item)
                        log_ok.append(f"🛠️ {file['name']}")
                    else:
                        buckets["khac"].append(item)
            except: continue
            
        return buckets, log_ok
    except: return None, []

# --- GIAO DIỆN CHÍNH ---
st.markdown("""<div class="header-banner"><div style="font-size: 40px;">🛡️</div><p style="font-size: 24px; font-weight: bold; margin:0">TRỢ LÝ PCCC (FINAL)</p></div>""", unsafe_allow_html=True)

with st.spinner('🚀 Đang kích hoạt hệ thống...'):
    data, logs = load_data_optimized()

if not data: st.error("❌ Lỗi dữ liệu."); st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("TRẠNG THÁI")
    if any("189" in l for l in logs): st.success("✅ Đã nạp NĐ 189")
    else: st.error("❌ Thiếu NĐ 189")
    with st.expander("File đã nạp"): 
        for l in logs: st.text(l)

# --- CHAT ---
if "messages" not in st.session_state: st.session_state.messages = []
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🚒"): st.markdown(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar="👤").write(prompt)
    
    p = prompt.lower()
    ctx = []
    
    # CHIẾN THUẬT GHÉP DỮ LIỆU THÔNG MINH
    if any(x in p for x in ["phạt", "tiền", "thẩm quyền", "ai ký", "lỗi", "hồ sơ"]):
        # Đưa 189 lên ĐẦU TIÊN
        ctx.extend([x for x in data["xu_phat"] if "189" in x])
        ctx.extend([x for x in data["xu_phat"] if "106" in x])
        ctx.extend(data["phap_ly"]) # Để hiểu khái niệm
    elif "quản lý" in p or "karaoke" in p:
        ctx.extend(data["phap_ly"])
    else:
        ctx.extend(data["phap_ly"] + data["quy_chuan"])
        
    final_ctx = "\n".join(ctx)

    with st.chat_message("assistant", avatar="🚒"):
        msg = st.empty()
        msg.markdown("⚡ *Đang xử lý...*")
        reply = call_gemini_logic(prompt, final_ctx)
        msg.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
