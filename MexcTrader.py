import pyautogui
import time

class MexcTrader:
    def __init__(self):
        self.order_delay = 0.3  # 매매 버튼 클릭 후 딜레이 (초)
    
    def click_button(self, image_path, confidence=0.8):
        """
        지정된 이미지 버튼을 찾아 클릭하는 함수
        """
        button = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
        if button:
            pyautogui.click(button)
            time.sleep(self.order_delay)
            return True
        return False

    def place_order(self, order_type):
        """
        LONG 또는 SHORT 주문 실행
        """
        if order_type == "LONG":
            print("✅ 롱 진입 중...")
            if not self.click_button("long_button.png"):  # 롱 버튼 이미지
                print("❌ 롱 주문 실패 (버튼을 찾을 수 없음)")
        
        elif order_type == "SHORT":
            print("✅ 숏 진입 중...")
            if not self.click_button("short_button.png"):  # 숏 버튼 이미지
                print("❌ 숏 주문 실패 (버튼을 찾을 수 없음)")
    
    def close_position(self):
        """
        현재 포지션 청산
        """
        print("🚀 포지션 청산 중...")
        if not self.click_button("close_button.png"):  # 청산 버튼 이미지
            print("❌ 포지션 청산 실패 (버튼을 찾을 수 없음)")
