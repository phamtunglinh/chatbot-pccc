import streamlit as st
import google.generativeai as genai
import random
import time

# --- CẤU HÌNH ---
st.set_page_config(page_title="Hệ thống PCCC", page_icon="🚒")

# --- HIỂN THỊ PHIÊN BẢN (ĐỂ BẮT BỆNH) ---
try:
    lib_version = genai.__version__
except:
    lib_version = "Quá cũ (Không xác định)"

if lib_version < "0.7.0":
    st.error(f"⚠️ CẢNH BÁO ĐỎ: Phiên bản thư viện hiện tại là `{lib_version}` (Quá cũ).")
    st.info("👉 Giải pháp: Anh hãy vào 'requirements.txt', thêm một dòng trống ở cuối file rồi bấm Save + Reboot để ép hệ thống cài lại.")
else:
    st.success(f"✅ Hệ thống đã cập nhật! Phiên bản thư viện: `{lib_version}`")

# --- KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys.split(",") if k.strip()]
except: st.error("Chưa có API Key"); st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- HÀM TỰ ĐỘNG TÌM MODEL SỐNG (BẤT CHẤP LỖI 404) ---
def ask_gemini_universal(prompt):
    # Danh sách các tên gọi model từ mới đến cũ
    candidates = [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-1.0-pro", 
        "gemini-pro"
    ]
    
    debug_log = []
    
    # Thử từng cái một
    for model_name in candidates:
        try:
            genai.configure(api_key=get_random_key())
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text, model_name # Trả về kết quả và tên model thành công
        except Exception as e:
            debug_log.append(f"{model_name}: {str(e)}")
            continue # Thử cái tiếp theo
            
    # Nếu thử hết mà vẫn lỗi
    error_details = "\n".join(debug_log)
    return f"❌ Lỗi toàn bộ: Không model nào hoạt động.\nChi tiết:\n{error_details}", "None"

# --- GIAO DIỆN CHAT ---
st.title("🚒 Trợ lý PCCC (Chế độ Chẩn đoán)")

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Gõ 'chào' để kiểm tra..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang thử kết nối với tất cả các Model..."):
            ans, success_model = ask_gemini_universal(prompt)
            
            if "❌" in ans:
                st.error(ans)
            else:
                st.write(ans)
                st.caption(f"🚀 Đã kết nối thành công với: **{success_model}**")
                st.session_state.messages.append({"role": "assistant", "content": ans})
