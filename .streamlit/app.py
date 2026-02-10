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
st.set_page_config(page_title="Trợ lý PCCC (Direct)", page_icon="🚒", layout="wide")
st.markdown("""<style>.header-banner {background: linear-gradient(90deg, #B71C1C 0%, #D32F2F 100%); padding: 1rem; color: white; text-align: center; border-radius: 0 0 10px 10px; margin-top: -50px;}</style>""", unsafe_allow_html=True)

# --- 1. LẤY KEY TỪ SECRETS ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_str = st.secrets["GEMINI_API_KEYS"]
    else: keys_str = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
    FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]
    GCP_JSON = json.loads(st.secrets["GCP_JSON"])
except: st.error("⚠️ Lỗi: Chưa nạp Key mới vào Secrets!"); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- 2. HÀM GỌI GOOGLE "ĐI ĐƯỜNG TẮT" (KHÔNG DÙNG THƯ VIỆN) ---
def call_gemini_direct(prompt, system_instruction=""):
    api_key = get_random_key()
    # Ưu tiên dùng bản Flash (Nhanh, rẻ, token lớn)
    models_to_try = ["gemini-1.5-flash", "gemini-pro"]
    
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        
        # Cấu trúc bản tin gửi đi
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
            ]
        }
        
        # Nếu có hướng dẫn hệ thống (System Instruction) - Chỉ dành cho model 1.5
        if system_instruction and "1.5" in model:
             data["system_instruction"] = {"parts": [{"text": system_instruction}]}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                try:
                    return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    return "⚠️ AI trả lời nhưng định dạng bị lỗi."
            elif response.status_code == 404:
                # Nếu model này không tìm thấy -> Thử model tiếp theo
                continue
            elif response.status_code == 429:
                 time.sleep(1) # Quá tải thì chờ xíu rồi thử lại (hoặc đổi key ở vòng lặp ngoài nếu cần)
                 continue
            else:
                return f"❌ Lỗi Google ({response.status_code}): {response.text}"
                
        except Exception as e:
            return f"❌ Lỗi kết nối: {str(e)}"
            
    return "⚠️ Đã thử tất cả các Model nhưng đều thất bại. Vui lòng kiểm tra lại Key."

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
                    content = "\n".join([p.extract_text() for p in reader.pages[:30] if p.extract_text()]) # Lấy 30 trang đầu thôi

                if content:
                    text = f"\n=== {file['name']} ===\n{content}\n"
                    name = file['name'].lower()
                    
                    if any(x in name for x in ["phat", "106", "189", "vi pham"]): groups["xu_phat"] += text
                    # Sửa thứ tự ưu tiên: Luật lấy trước
                    elif any(x in name for x in ["luat", "nghi dinh", "thong tu", "136", "50", "105"]): groups["phap_luat"] += text
                    elif any(x in name for x in ["quy chuan", "tieu chuan", "06", "qc10"]): groups["quy_chuan"] += text
                    elif any(x in name for x in ["chua chay", "cnch", "phuong an"]): groups["chua_chay"] += text
                    else: groups["khac"] += text
                    
                    debug_list.append(file['name'])
            except: continue
        return groups, debug_list
    except: return None, []

# --- 4. GIAO DIỆN CHAT ---
st.markdown('<div class="header-banner"><h3>TRỢ LÝ PCCC & CNCH (DIRECT)</h3></div>', unsafe_allow_html=True)

with st.spinner("Đang tải dữ liệu..."):
    groups, file_list = load_data()

if not groups: st.error("Lỗi Drive"); st.stop()

if "msgs" not in st.session_state: st.session_state.msgs = []
for m in st.session_state.msgs: st.chat_message(m["role"]).write(m["content"])

if q := st.chat_input("Nhập câu hỏi..."):
    st.session_state.msgs.append({"role": "user", "content": q})
    st.chat_message("user").write(q)
    
    # Logic chọn dữ liệu (Tiết kiệm)
    p = q.lower()
    ctx = ""
    src = "Xã giao"
    
    # Chỉ khi KHÔNG phải chào hỏi mới đi lấy dữ liệu
    if not any(x in p for x in ["chào", "hello", "hi ", "là ai"]):
        src_list = []
        if any(x in p for x in ["phạt", "tiền", "lỗi"]): 
            ctx += groups["xu_phat"] + groups["phap_luat"]; src_list.append("Xử phạt")
        elif any(x in p for x in ["mét", "cao", "rộng", "bậc", "thang", "cửa"]):
            ctx += groups["quy_chuan"]; src_list.append("Kỹ thuật")
        elif any(x in p for x in ["hồ sơ", "thủ tục"]):
            ctx += groups["phap_luat"]; src_list.append("Thủ tục")
        elif any(x in p for x in ["chữa cháy", "xe", "bơm"]):
            ctx += groups["chua_chay"]; src_list.append("Chữa cháy")
        
        # Fallback
        if not ctx: ctx = groups["phap_luat"]; src_list = ["Cơ bản"]
        src = "+".join(src_list)

    # Tạo Prompt
    if src == "Xã giao":
        final_prompt = f"Người dùng: {q}. Hãy trả lời ngắn gọn, thân thiện với vai trò Trợ lý PCCC."
    else:
        final_prompt = f"Dữ liệu tham khảo:\n{ctx}\n\nCâu hỏi: {q}\n\nYêu cầu: Trả lời dựa trên dữ liệu, trích dẫn văn bản."

    with st.chat_message("assistant"):
        if src != "Xã giao": st.caption(f"Đang tra cứu: {src}")
        with st.spinner("Đang kết nối vệ tinh..."):
            ans = call_gemini_direct(final_prompt, "Bạn là chuyên gia PCCC.")
            st.write(ans)
            st.session_state.msgs.append({"role": "assistant", "content": ans})
