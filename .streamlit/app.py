import streamlit as st
import google.generativeai as genai
import random
import time

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC", page_icon="🚒")

# --- KẾT NỐI ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys.split(",") if k.strip()]
except: st.error("Lỗi: Chưa cấu hình GEMINI_API_KEYS"); st.stop()

# --- CHỈ DÙNG MODEL CŨ (ĐỂ KHÔNG BỊ LỖI 404) ---
# Chúng ta ép cứng dùng 'gemini-pro' đời đầu
ACTIVE_MODEL = "gemini-pro"

def get_random_key(): return random.choice(API_KEYS)

st.title("🚒 Trợ lý PCCC (Bản ổn định)")
st.caption("Đang chạy chế độ tương thích (Model: gemini-pro)")

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    try:
        # Gọi AI
        current_key = get_random_key()
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel(ACTIVE_MODEL)
        
        with st.chat_message("assistant"):
            with st.spinner("Đang trả lời..."):
                response = model.generate_content(prompt)
                st.write(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
    except Exception as e:
        st.error(f"Lỗi: {str(e)}")
        if "404" in str(e):
            st.warning("Gợi ý: Tài khoản Google của anh chưa được cấp quyền dùng Model này, hoặc thư viện quá cũ.")
