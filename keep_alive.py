from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

url = "https://chatbot-phamtunglinh.streamlit.app/"

# Cấu hình chạy trình duyệt ẩn (headless)
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

try:
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    # Đợi 15 giây để Streamlit tải xong giao diện và kết nối WebSocket
    time.sleep(15) 
    print("Đã truy cập thành công để giữ app thức!")
finally:
    driver.quit()
