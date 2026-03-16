import undetected_chromedriver as uc
import time

url = "https://chatbot-phamtunglinh.streamlit.app/"

options = uc.ChromeOptions()
# KHÔNG dùng headless nữa. Trình duyệt sẽ mở "thật" trên màn hình ảo.
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--window-size=1920,1080') # Giả lập màn hình Full HD

try:
    print("Đang khởi động trình duyệt trên màn hình ảo...")
    driver = uc.Chrome(options=options)
    
    print(f"Đang truy cập: {url}")
    driver.get(url)
    
    # Giả lập thao tác người dùng: Cuộn trang từ từ
    time.sleep(10)
    print("Đang cuộn trang để chứng minh là người thật...")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
    time.sleep(5)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
    
    # Đợi thêm để Streamlit tải xong các kết nối ngầm
    time.sleep(15) 
    print("Đã đánh thức ứng dụng thành công!")

except Exception as e:
    print(f"Lỗi: {e}")

finally:
    if 'driver' in locals():
        driver.quit()
        print("Đã đóng trình duyệt.")
