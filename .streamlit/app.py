import streamlit as st
import requests
import json

st.set_page_config(page_title="Trạm Cấp Cứu Key", page_icon="🚑")
st.title("🚑 TRẠM CẤP CỨU KEY")

# --- HIỂN THỊ TRẠNG THÁI SECRETS ---
st.subheader("1. Kiểm tra file Secrets")
try:
    if "GEMINI_API_KEYS" in st.secrets:
        raw = st.secrets["GEMINI_API_KEYS"]
        st.success(f"✅ Đã đọc được file Secrets. Nội dung đang có {len(raw)} ký tự.")
        # Lấy key đầu tiên để test
        first_key = [k.strip() for k in raw.split(",") if k.strip()][0]
        st.info(f"Key đầu tiên hệ thống đang dùng: {first_key[:5]}...{first_key[-5:]}")
    else:
        st.error("❌ Không tìm thấy biến 'GEMINI_API_KEYS' trong Secrets!")
        first_key = ""
except Exception as e:
    st.error(f"❌ Lỗi đọc Secrets: {str(e)}")
    first_key = ""

# --- NHẬP KEY THỦ CÔNG ĐỂ TEST ---
st.subheader("2. Test Key trực tiếp (Bỏ qua Secrets)")
st.caption("Nếu Secrets bị lỗi, hãy dán Key vào đây để kiểm tra xem Key có sống không.")
manual_key = st.text_input("Dán 1 Key của anh vào đây:", value=first_key, type="password")

if st.button("🚀 BẮT ĐẦU TEST KẾT NỐI"):
    if not manual_key:
        st.warning("Vui lòng nhập Key!")
        st.stop()
        
    # URL gọi thẳng vào Google (Gemini 1.5 Flash)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={manual_key}"
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{"parts": [{"text": "Xin chào, hãy trả lời 'OK' nếu bạn nhận được tin này."}]}]
    }
    
    with st.spinner("Đang gửi tín hiệu lên vệ tinh Google..."):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            
            st.write("---")
            st.write(f"📡 Mã phản hồi: `{response.status_code}`")
            
            if response.status_code == 200:
                st.balloons()
                st.success("✅ THÀNH CÔNG RỰC RỠ! Key này hoạt động TỐT.")
                st.json(response.json())
                st.info("👉 Kết luận: Key của anh KHÔNG HỎNG. Vấn đề nằm ở file Secrets hoặc Code cũ.")
            else:
                st.error("❌ THẤT BẠI! Google từ chối Key này.")
                st.write("🔴 Chi tiết lỗi Google báo về:")
                st.json(response.json()) # Quan trọng: Xem nó báo lỗi gì (Key sai, Hết tiền, hay chưa bật API)
                
        except Exception as e:
            st.error(f"Lỗi mạng: {str(e)}")
