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

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC (Gemini 2.5)", page_icon="🚒", layout="wide")
st.markdown("""
<style>
    .header-banner {
        background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%);
        padding: 1rem; color: white; text-align: center; 
        border-radius: 0 0 10px 10px; margin-top: -50px;
    }
    .stChatInput {border-radius: 20px;}
</style>
""", unsafe_allow_html=True)

# --- 1. LẤY KEY TỪ SECRETS ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_str = st.secrets["GEMINI_API_KEYS"]
    else: keys_str = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    
    FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: 
    st.error("⚠️ Lỗi: Chưa nạp Key hoặc file JSON vào Secrets!"); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- 2. HÀM GỌI GOOGLE "DIRECT API" (DÙNG MODEL 2.5 MỚI NHẤT) ---
def call_gemini_direct(prompt, system_instruction=""):
    api_key = get_random_key()
    
    # DANH SÁCH "SIÊU XE" CỦA ĐẠI ÚY (Ưu tiên 2.5 Flash -> 2.0 Flash)
    models_to_try = [
        "gemini-2.5-flash", 
        "gemini-2.0-flash", 
        "gemini-flash-latest"
    ]
    
    for model in models_to_try:
        # URL gọi thẳng vào Google (Bypass thư viện)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
        }
        
        # Thêm chỉ thị hệ thống (Giúp AI nhập vai Đại úy PCCC tốt hơn)
        if system_instruction:
             data["system_instruction"] = {"parts": [{"text": system_instruction}]}

        try:
            # Gửi request (timeout 40s cho model mới xử lý sâu hơn)
            response = requests.post(url, headers=headers, json=data, timeout=40)
            
            if response.status_code == 200:
                result = response.json()
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    return "⚠️ AI trả lời nhưng định dạng không đúng."
            elif response.status_code == 404:
                # Nếu model này không có -> Thử cái tiếp theo trong list
                continue
            elif response.status_code == 429:
                 time.sleep(2) # Quá tải thì chờ 2s rồi thử lại
                 continue
            else:
                return f"❌ Lỗi Google ({response.status_code}): {response.text}"
                
        except Exception as e:
            continue # Lỗi mạng thì thử model khác
            
    return "⚠️ Đã thử tất cả các Model (Gemini 2.5, 2.0) nhưng đều thất bại. Vui lòng kiểm tra lại Key."

# --- 3. ĐỌC DỮ LIỆU DRIVE (GIỮ NGUYÊN) ---
@st.cache_resource(ttl=3600)
def load_data():
    try:
        creds = service_account.Credentials.from_service_account_info(GCP_JSON)
        service = build('drive', 'v3', credentials=creds)
        files = service.files().list(q=f"'{FOLDER_ID}' in parents and trashed=false", pageSize=50, fields="files(id, name)").execute().get('files', [])
        
        groups = {"phap_luat": "", "xu_phat": "", "quy_chuan": "", "chua_chay": "", "khac": ""}
        debug_list = []

        for file in files:
            try:
                content = ""
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO(); downloader = MediaIoBaseDownload(fh, request)
                done = False; 
                while done is False: status, done = downloader.next_chunk()
                fh.seek(0)
                
                if file['name'].endswith(".docx"):
                    doc = Document(fh)
                    content = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
                elif file['name'].endswith(".pdf"):
                    reader = PdfReader(fh)
                    # Lấy 40 trang đầu (Model 2.5 đọc rất nhanh)
                    content = "\n".join([p.extract_text() for p in reader.pages[:40] if p.extract_text()])

                if content:
                    text = f"\n=== TÀI LIỆU: {file['name']} ===\n{content}\n"
                    name = file['name'].lower()
                    
                    if any(x in name for x in ["phat", "106", "189", "vi pham"]): groups["xu_phat"] += text
                    elif any(x in name for x in ["luat", "nghi dinh", "thong tu", "136", "50", "105"]): groups["phap_luat"] += text
                    elif any(x in name for x in ["quy chuan", "tieu chuan", "06", "qc10"]): groups["quy_chuan"] += text
                    elif any(x in name for x in ["chua chay", "cnch", "phuong an"]): groups["chua_chay"] += text
                    else: groups["khac"] += text
                    
                    debug_list.append(file['name'])
            except: continue
        return groups, debug_list
    except: return None, []

# --- 4. GIAO DIỆN CHAT ---
st.markdown('<div class="header-banner"><h3>TRỢ LÝ PCCC (MODEL GEMINI 2.5)</h3></div>', unsafe_allow_html=True)

with st.spinner("Đang nạp dữ liệu từ Drive..."):
    groups, file_list = load_data()

if not groups: 
    st.error("⚠️ Không đọc được dữ liệu Drive. Kiểm tra lại Key JSON Service Account.")
    # Vẫn cho chạy chat để test Model
    groups = {"phap_luat": "", "xu_phat": "", "quy_chuan": "", "chua_chay": "", "khac": ""}

if "msgs" not in st.session_state: st.session_state.msgs = []
for m in st.session_state.msgs: st.chat_message(m["role"]).write(m["content"])

if q := st.chat_input("Đại úy cần hỗ trợ gì?"):
    st.session_state.msgs.append({"role": "user", "content": q})
    st.chat_message("user").write(q)
    
    # 1. Logic chọn dữ liệu (Thông minh)
    p = q.lower()
    ctx = ""
    src = "Xã giao"
    
    # Chỉ khi KHÔNG phải chào hỏi mới đi lấy dữ liệu
    if not any(x in p for x in ["chào", "hello", "hi ", "là ai", "giới thiệu"]):
        src_list = []
        if any(x in p for x in ["phạt", "tiền", "lỗi"]): 
            ctx += groups["xu_phat"] + groups["phap_luat"]; src_list.append("Xử phạt")
        elif any(x in p for x in ["mét", "cao", "rộng", "bậc", "thang", "cửa", "lối"]):
            ctx += groups["quy_chuan"]; src_list.append("Kỹ thuật")
        elif any(x in p for x in ["hồ sơ", "thủ tục"]):
            ctx += groups["phap_luat"]; src_list.append("Thủ tục")
        elif any(x in p for x in ["chữa cháy", "xe", "bơm", "đội hình"]):
            ctx += groups["chua_chay"]; src_list.append("Chữa cháy")
        
        # Fallback
        if not ctx: ctx = groups["phap_luat"]; src_list = ["Cơ bản"]
        src = "+".join(src_list)

    # 2. Tạo Prompt
    if src == "Xã giao":
        final_prompt = f"Người dùng: {q}. Hãy trả lời ngắn gọn, thân thiện, xưng hô là 'Tôi' và gọi người dùng là 'Đại úy'."
    else:
        final_prompt = f"""
        VAI TRÒ: Trợ lý ảo chuyên ngành PCCC & CNCH.
        DỮ LIỆU THAM KHẢO:
        {ctx}
        
        CÂU HỎI CỦA ĐẠI ÚY: {q}
        
        YÊU CẦU:
        1. Trả lời chính xác dựa trên dữ liệu.
        2. Nếu trích dẫn Luật/Nghị định/QCVN, hãy ghi rõ điều khoản (nếu có trong dữ liệu).
        3. Văn phong chuyên nghiệp, ngắn gọn.
        """

    with st.chat_message("assistant"):
        if src != "Xã giao": st.caption(f"📚 Đang tra cứu: {src}")
        with st.spinner("Gemini 2.5 đang xử lý..."):
            ans = call_gemini_direct(final_prompt, "Bạn là Trợ lý PCCC chuyên nghiệp.")
            st.write(ans)
            st.session_state.msgs.append({"role": "assistant", "content": ans})
