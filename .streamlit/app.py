import streamlit as st
import requests
import json

st.set_page_config(page_title="Scanner Key", page_icon="🔍")

# --- LẤY KEY ---
try:
    if "GEMINI_API_KEYS" in st.secrets: keys_str = st.secrets["GEMINI_API_KEYS"]
    else: keys_str = st.secrets["GEMINI_API_KEY"]
    # Lấy key đầu tiên để test
    TEST_KEY = [k.strip() for k in keys_str.split(",") if k.strip()][0]
except: st.error("Chưa có Key!"); st.stop()

# --- HÀM QUÉT MODEL ---
def scan_available_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if 'models' in data:
                return data['models'] # Trả về danh sách model
            else:
                return [] # Key đúng nhưng không có model nào
        else:
            return f"Lỗi Key: {response.text}"
    except Exception as e:
        return f"Lỗi mạng: {str(e)}"

# --- GIAO DIỆN ---
st.title("🔍 MÁY QUÉT QUYỀN HẠN KEY")
st.code(f"Đang kiểm tra Key: {TEST_KEY[:5]}...*****")

if st.button("BẮT ĐẦU QUÉT"):
    with st.spinner("Đang hỏi Google..."):
        result = scan_available_models(TEST_KEY)
        
        if isinstance(result, list):
            if len(result) > 0:
                st.success(f"✅ Key này hoạt động tốt! Tìm thấy {len(result)} models.")
                st.write("Danh sách model khả dụng:")
                for m in result:
                    st.text(f"- {m['name']}")
                    # Gợi ý model nên dùng
                    if "gemini-1.5-flash" in m['name']:
                        st.balloons()
                        st.info(f"👉 PHÁT HIỆN: Anh có quyền dùng {m['name']}!")
            else:
                st.error("❌ Key này đúng định dạng nhưng RỖNG QUYỀN. Google không cấp model nào cho Key này.")
                st.warning("Gợi ý: Anh cần bật API 'Generative Language API' trong Google Cloud Console.")
        else:
            st.error(f"❌ Key HỎNG hoặc BỊ KHÓA. Chi tiết:\n{result}")
