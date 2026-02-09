import streamlit as st
import requests
import json
import random
import time

# --- CẤU HÌNH ---
st.set_page_config(page_title="Trợ lý PCCC (Direct API)", page_icon="🚒")

# --- LẤY KEY TỪ SECRETS ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_str = st.secrets["GEMINI_API_KEYS"]
    else: keys_str = st.secrets["GEMINI_API_KEY"]
    API_KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
except:
    st.error("⚠️ Chưa cấu hình Key trong Secrets!")
    st.stop()

def get_random_key(): return random.choice(API_KEYS)

# --- HÀM GỌI GOOGLE TRỰC TIẾP (KHÔNG QUA THƯ VIỆN) ---
def call_gemini_direct(prompt, model="gemini-1.5-flash"):
    api_key = get_random_key()
    # URL gọi trực tiếp vào máy chủ Google (Bypass thư viện lỗi)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            try:
                # Lọc lấy câu trả lời
                return result['candidates'][0]['content']['parts'][0]['text']
            except:
                return "⚠️ AI trả lời nhưng định dạng không đúng."
        else:
            # Nếu lỗi, thử in ra xem Google báo gì
            error_info = response.json()
            error_msg = error_info.get('error', {}).get('message', 'Lỗi không xác định')
            
            # Nếu 404 -> Thử đổi sang model cũ
            if response.status_code == 404 and model == "gemini-1.5-flash":
                return "RETRY_OLD_MODEL"
            
            return f"❌ Lỗi Google ({response.status_code}): {error_msg}"
            
    except Exception as e:
        return f"❌ Lỗi kết nối: {str(e)}"

# --- GIAO DIỆN CHAT ---
st.title("🚒 Trợ lý PCCC (Kết nối Trực tiếp)")
st.caption("✅ Đang chạy chế độ Direct HTTP (Không phụ thuộc thư viện)")

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Gõ 'chào' để kiểm tra..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang kết nối vệ tinh..."):
            # Gọi thử model xịn nhất
            reply = call_gemini_direct(prompt, "gemini-1.5-flash")
            
            # Nếu model xịn vẫn lỗi 404 -> Tự động chuyển sang model cũ
            if reply == "RETRY_OLD_MODEL":
                st.warning("⚠️ Model Flash chưa khả dụng với Key này, đang chuyển sang Gemini Pro...")
                reply = call_gemini_direct(prompt, "gemini-pro")
            
            st.write(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})
