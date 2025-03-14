import time
import random
from datetime import datetime, timedelta
from loguru import logger
from selenium.webdriver.common.by import By
from web_selenium.browser_stealth import BrowserStealth, set_cross_and_leverage_50

class RiskManager:
    """
    매매 중 휴식/리스크 관리 전반:
    - 팝업 닫기
    - 매매 중단(휴식) 로직 관리
      (1) (헷지 해제 후) 양 포지션=0이 되는 순간 -> 10~15분 랜덤 휴식
      (2) 무포 상태에서 '50진입→청산' 3회 반복 후, 헷지 진입 시 -> 10~15분 휴식
      (3) 매매 중단 없이 90분 경과 -> 무포 시 10~15분 휴식
      (4) 15:00 이전, 목표거래량(시드별) 120% 달성 & 무포 -> 당일 15:00까지 중단, 15:00~16:00 사이 랜덤 재개
    - 세션 만료 체크 & 재로그인
    """

    def __init__(self, driver=None, position_tracker=None, user_seed=0.0):
        self.driver = driver
        self.position_tracker = position_tracker
        self.trade_history = []
        self.browser_stealth = BrowserStealth()

        self.pause_end_time = None
        self.last_rest_time = datetime.now()

        self.user_seed = user_seed
        self._daily_base_volume = self._get_base_target_by_seed(user_seed)
        self.daily_volume_target = self._daily_base_volume * 1.2

        self.hedge_detected = False

        # 헷지 상태에서 숏 전량 청산 여부
        self.short_closed_after_hedge = False
        # 헷지 상태에서 롱 전량 청산 여부
        self.long_closed_after_hedge = False

        self.entry_close_count = 0

    # ----------------------------------------------------
    # (시드별 목표 거래량)
    # ----------------------------------------------------
    def _get_base_target_by_seed(self, seed: float) -> float:
        return seed * 1_000
    
    # ----------------------------------------------------
    # 팝업 닫기
    # ----------------------------------------------------
    def close_popups(self):
        popup_selectors = [
            "span.ant-modal-close-x",
            "button.ant-modal-close",
            "div.close-btn>span",
            '//button[@class="ant-btn ant-btn-primary ant-btn-lg"]//span[text()="확인"]',
            '//div[contains(@class,"GuidePopupModal_Button__0VIdm") and text()="확인"]'
        ]

        guide_popup_close_selectors = [
            '//div[@class="GuidePopupModal_closeIcon__7Kjd0"]/*',
            '//div[@class="GuidePopupModal_Button__0VIdm" and (text()="다음" or text()="완료" or text()="확인" or text()="닫기")]'
        ]

        max_attempts = 3
        
        for attempt in range(1, max_attempts + 1):
            popups_closed_this_round = False

            # (1) 일반 팝업 닫기
            for sel in popup_selectors:
                try:
                    if sel.startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, sel)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, sel)

                    for elem in elements:
                        if elem.is_displayed():
                            elem.click()
                            # time.sleep(0.1)
                            popups_closed_this_round = True
                            logger.trace(f"[RiskManager] 팝업 닫기 성공 (selector={sel}).")

                except Exception as e:
                    logger.trace(f"[RiskManager] 팝업 닫기 실패(무시): {e}")

            # (2) GuidePopupModal 닫기
            for gpsel in guide_popup_close_selectors:
                try:
                    gp_elems = self.driver.find_elements(By.XPATH, gpsel)
                    for gp in gp_elems:
                        if gp.is_displayed():
                            gp.click()
                            # time.sleep(0.1)
                            popups_closed_this_round = True
                            logger.trace(f"[RiskManager] GuidePopupModal 닫기 버튼 클릭 (selector={gpsel}).")
                except Exception as e:
                    logger.trace(f"[RiskManager] GuidePopupModal 닫기 실패(무시)")

        # (3) ────────── 주문 완료 알림(Notification) 팝업 닫기 ──────────
            try:
                notification_close_btns = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.ant-notification-notice-close"  # or 'span.ant-notification-notice-close-x'
                )
                for btn in notification_close_btns:
                    if btn.is_displayed():
                        btn.click()
                        # time.sleep(0.1)
                        popups_closed_this_round = True
                        logger.trace("[RiskManager] 주문 완료 알림(notification) 팝업 닫기.")
            except Exception as e:
                logger.trace(f"[RiskManager] 주문 완료 알림 팝업 닫기 실패(무시)")

            if popups_closed_this_round:
                pass
                # time.sleep(1)
            else:
                logger.trace("[RiskManager] 더 이상 닫을 팝업 없음 -> 종료")
                break

    # ----------------------------------------------------
    # 누적 거래량 업데이트
    # ----------------------------------------------------
    def update_trading_volume(self, trade_amount: float):
        if not self.position_tracker:
            return
        self.position_tracker.add_trade_volume(trade_amount)
        current_volume = self.position_tracker.get_accumulated_volume()
        logger.info(f"[RiskManager] 누적 거래량: {current_volume:.2f} / {self.daily_volume_target:.2f}")

    # ----------------------------------------------------
    # 포지션 여러 번 재조회하여 최종 상태 파악
    # ----------------------------------------------------
    def _get_stable_positions(self, tries=3, delay=0.1):
        final_positions = []
        if not self.position_tracker:
            return final_positions

        for i in range(tries):
            pos = self.position_tracker.get_open_positions()
            final_positions = pos
            if i < tries - 1:
                time.sleep(delay)
        return final_positions

    def _force_close_leftovers(self):
        """
        leftover(롱/숏) 전량 청산.
        """
        if not self.position_tracker:
            logger.warning("[RiskManager] _force_close_leftovers() -> position_tracker가 없습니다.")
            return
        logger.info("[RiskManager] leftover 전량 청산 시도.")
        self.position_tracker.close_all_positions()
        time.sleep(0.1)

    # ----------------------------------------------------
    # 매매 기록 + 휴식 조건 체크
    # ----------------------------------------------------
    def record_trade(self, trade_type: str, last_entry_price: float = None, close_price: float = None):
        self.trade_history.append(trade_type)
        logger.info(f"[RiskManager] 매매 기록: {trade_type}")

        positions = self._get_stable_positions(tries=2, delay=1.0)
        long_size = 0
        short_size = 0
        for pos in positions:
            side = pos.get("positionSide", "")
            size = pos.get("size", 0.0)
            if side.upper() == "LONG":
                long_size = size
            elif side.upper() == "SHORT":
                short_size = size

        # (1) 헷지 해제 후 무포 => leftover 전량 청산 => 휴식
        if self.hedge_detected:
            if trade_type == "SHORT_ALL_CLOSED":
                self.short_closed_after_hedge = True
            if trade_type == "LONG_ALL_CLOSED":
                self.long_closed_after_hedge = True

            # 이제 롱·숏 실제 수량도 0인지 체크
            if self.short_closed_after_hedge and self.long_closed_after_hedge and long_size == 0 and short_size == 0:
                logger.info("=== (헷지 해제) 무포 => leftover 여부 최종 확인 후 휴식 ===")
                self._force_close_leftovers()
                
                # leftover 청산 후 다시 확인
                positions2 = self._get_stable_positions(tries=2, delay=1.0)
                final_long, final_short = 0, 0
                for pos2 in positions2:
                    s2 = pos2.get("positionSide", "")
                    sz2 = pos2.get("size", 0.0)
                    if s2.upper() == "LONG":
                        final_long = sz2
                    elif s2.upper() == "SHORT":
                        final_short = sz2

                if final_long == 0 and final_short == 0:
                    logger.info("=== (헷지 해제) 남은 포지션 = 0 => 10~15분 휴식 진입 ===")
                    self.random_sleep()
                    # 헷지 상태 해제
                    self.hedge_detected = False
                    # 플래그들 초기화
                    self.short_closed_after_hedge = False
                    self.long_closed_after_hedge = False
                else:
                    logger.warning(
                        f"[RiskManager] leftover 청산 실패. 최종 롱={final_long}, 숏={final_short} => 휴식 스킵"
                    )
                return  # 여기서 return으로 빠져나가 매매중단

        # (2) 무포 상태에서 50→청산 3회 카운트
        if long_size == 0 and short_size == 0:
            if trade_type in ["LONG50_CLOSED", "SHORT50_CLOSED"]:
                self.entry_close_count += 1
                logger.info(f"[RiskManager] 50→청산 누적 횟수: {self.entry_close_count}")

        # 헷지 진입 시점
        if trade_type in ["HEDGE_LONG", "HEDGE_SHORT"]:
            self.hedge_detected = True
            if self.entry_close_count >= 3 and hasattr(self, "last_closed_entry_price") and self.last_closed_entry_price > 0 and close_price is not None:
                diff_ratio = abs(close_price - self.last_closed_entry_price) / self.last_closed_entry_price
                if diff_ratio < 0.0005:  # 0.05%
                    logger.info("=== 무포 50→청산 3회 후, ±0.05% 미만가격에서 헷징 => 휴식 ===")
                    self.random_sleep()
                    self.entry_close_count = 0
                    return

        # (3) 90분 무휴식 => 무포 시 휴식
        now = datetime.now()
        if (now - self.last_rest_time) >= timedelta(minutes=90):
            if long_size == 0 and short_size == 0:
                logger.info("=== 90분 무휴식 & 무포 => 10~15분 휴식 ===")
                self.random_sleep()
                return
            else:
                logger.info("[RiskManager] 90분 경과했지만 포지션 보유중 => 휴식 스킵.")

        # (4) 목표거래량 120% 달성 & 15시 이전 & 무포 => 15~16시 랜덤 휴식
        self.check_volume_goal_and_sleep()

    def check_volume_goal_and_sleep(self):
        """
        15:00 이전에 누적 거래량 >= 목표치(120%) + 무포 => 15~16시 랜덤 휴식
        """
        if not self.position_tracker:
            return

        now = datetime.now()
        if now.hour >= 15:
            return

        current_vol = self.position_tracker.get_accumulated_volume()
        if current_vol < self.daily_volume_target:
            return

        positions = self.position_tracker.get_open_positions()
        if len(positions) == 0:
            logger.info("[RiskManager] 목표거래량 초과 & 15시 이전 & 무포 => 15~16시 랜덤 휴식")
            self.pause_until_random_15to16()

    # ----------------------------------------------------
    # 휴식/재개 로직
    # ----------------------------------------------------
    def is_paused(self) -> bool:
        if self.pause_end_time is None:
            return False
        now = datetime.now()
        if now >= self.pause_end_time:
            self.pause_end_time = None
            return False
        return True

    def random_sleep(self):
        """
        10~15분 동안 매매 일시 정지
        """
        if self.position_tracker:
            # leftover 포지션 전량 청산
            positions = self.position_tracker.get_open_positions()
            long_amt = 0.0
            short_amt = 0.0

            for p in positions:
                side = p.get("positionSide", "")
                size = p.get("size", 0.0)
                if side.upper() == "LONG":
                    long_amt += size
                elif side.upper() == "SHORT":
                    short_amt += size

            if long_amt > 0 or short_amt > 0:
                logger.info("[RiskManager] 휴식 돌입 전 leftover 포지션 발견 => 전량 청산 시도.")
                self.position_tracker.close_all_positions()

        sleep_seconds = random.randint(600, 900)  # 10~15분
        self.pause_end_time = datetime.now() + timedelta(seconds=sleep_seconds)
        self.last_rest_time = datetime.now()
        logger.info(
            f"=== 휴식 시작: {sleep_seconds // 60}분 후({self.pause_end_time.strftime('%H:%M:%S')}) 매매 재개 예정 ==="
        )

    def pause_until_random_15to16(self):
        """
        15:00 ~ 16:00 사이 무작위 시각까지 휴식
        """
        if self.position_tracker:
            positions = self.position_tracker.get_open_positions()
            long_amt = sum([p.get("size",0.0) for p in positions if p.get("positionSide")=="LONG"])
            short_amt = sum([p.get("size",0.0) for p in positions if p.get("positionSide")=="SHORT"])
            if long_amt > 0 or short_amt > 0:
                logger.info("[RiskManager] 휴식 돌입 전 leftover 포지션 발견 => 전량 청산 시도.")
                self.position_tracker.close_all_positions()

        now = datetime.now()
        random_minute = random.randint(0, 59)
        random_second = random.randint(0, 59)
        target_time = datetime(now.year, now.month, now.day, 15, random_minute, random_second)

        if target_time < now:
            target_time = datetime(now.year, now.month, now.day, 16, random_minute, random_second)
            if target_time < now:
                return self.random_sleep()

        if target_time.hour > 16:
            target_time = datetime(now.year, now.month, now.day, 16, 0, 0)

        self.pause_end_time = target_time
        self.last_rest_time = datetime.now()
        wait_min = int((target_time - now).total_seconds() // 60)
        logger.info(
            f"=== 목표 거래량 120% 달성 => {target_time.strftime('%H:%M:%S')}까지 휴식 (약 {wait_min}분) ==="
        )

    # ----------------------------------------------------
    # 세션 만료 -> 재로그인
    # ----------------------------------------------------
    def check_session_and_relogin(self):
        if not self.driver:
            return
        current_url = self.driver.current_url
        if "login" in current_url.lower():
            logger.warning("[RiskManager] 세션 만료 감지 => 재로그인 시도")
            self.browser_stealth.login_mexc(self.driver)
            time.sleep(1)
            set_cross_and_leverage_50(self.driver)
