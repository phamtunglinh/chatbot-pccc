import streamlit as st
import requests

st.set_page_config(page_title="Check Model", page_icon="📋")
st.title("📋 DANH SÁCH MODEL KHẢ DỤNG")

# Lấy Key từ Secrets
try:
    if "GEMINI_API_KEYS" in st.secrets: keys = st.secrets["GEMINI_API_KEYS"]
    else: keys = st.secrets["GEMINI_API_KEY"]
    MY_KEY = [k.strip() for k in keys.split(",") if k.strip()][0]
    st.success(f"🔑 Đang kiểm tra Key: ...{MY_KEY[-6:]}")
except:
    st.error("Chưa có Key trong Secrets!"); st.stop()

# Nút bấm kiểm tra
if st.button("🚀 XEM DANH SÁCH MODEL CỦA TÔI"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={MY_KEY}"
    
    with st.spinner("Đang lấy dữ liệu từ Google..."):
        try:
            response = requests.get(url)
            data = response.json()
            
            if "models" in data:
                st.balloons()
                st.write("### ✅ KẾT QUẢ: Key của anh dùng được các Model sau:")
                
                valid_models = []
                for m in data["models"]:
                    # Chỉ lấy những model tạo nội dung (generateContent)
                    if "generateContent" in m["supportedGenerationMethods"]:
                        name = m["name"].replace("models/", "")
                        st.code(name)
                        valid_models.append(name)
                
                if not valid_models:
                    st.warning("Key này đúng, nhưng không có model nào hỗ trợ chat (generateContent).")
                else:
                    st.info(f"👉 Hãy copy một cái tên ở trên (ví dụ: {valid_models[0]}) gửi cho tôi!")
            
            else:
                st.error("❌ Lỗi: Không lấy được danh sách.")
                st.json(data)
                
        except Exception as e:
            st.error(f"Lỗi mạng: {e}")
