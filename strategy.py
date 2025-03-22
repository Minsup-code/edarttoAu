import math
import time
from loguru import logger
from config.config import PRICE_THRESHOLD, MIN_TRADE_AMOUNT

class TradingStrategy:
    """
    매매전략(EMA(1,3,7), ±0.05% 변동성, 헷징) 구현.
    'order_executor'로 실제 주문을 보내는 구조.

    이 버전에서는 MEXC 웹페이지의 DOM에 표시되는 EMA1, EMA3, EMA7 값을 직접 파싱하여
    self.ema1, self.ema2, self.ema3에 매 틱마다 반영한다.
    """

    def __init__(self, symbol="BTC_USDT", position_tracker=None, risk_manager=None):
        # 이전 틱에서의 ema1, ema2, ema3 (교차 방향 체크용)
        self.prev_ema1 = None
        self.prev_ema2 = None
        self.prev_ema3 = None

        # 현재 보유 포지션 크기(기록용)
        self.long_size = 0
        self.short_size = 0

        # 포지션 진입가 
        self.long_entry_price = 0.0
        self.short_entry_price = 0.0

        # 변동성 기준 (±0.05%)
        self.price_threshold = PRICE_THRESHOLD

        # 실제 주문 실행자(OrderExecutor)
        self.order_executor = None

        # 부가 참조
        self.user_seed = 0.0
        self.symbol = symbol
        self.position_tracker = position_tracker
        self.risk_manager = risk_manager

        # 매매 단위 (base_unit)
        self.base_unit = 1

        # “시세 역할”로 사용할 변수. (EMA1을 매 틱마다 넣음)
        self.current_price = 0.0

        # 이 클래스 내부에서 사용할 EMA 값들 (DOM 파싱으로 업데이트)
        self.ema1 = None  # EMA1
        self.ema2 = None  # EMA3
        self.ema3 = None  # EMA7

        # 마지막으로 "성공적으로" 진입한 포지션 방향 (롱/숏 번갈아 방지용)
        self.last_trade_action = None

        # 부분청산 중복 방지 플래그
        self.block_long2_clear = False
        self.block_short2_clear = False

        self.last_golden_cross_price = None
        self.last_dead_cross_price = None

    def set_order_executor(self, executor):
        self.order_executor = executor

    def set_user_seed(self, seed: float):
        self.user_seed = seed

    # ------------------------------------------------------
    # 매매비중1 계산 + 최소거래단위 반영 (floor)
    # ------------------------------------------------------
    def update_base_unit(self):
        """
        무포지션 상태에서 user_seed 와 현재의 시세(= self.ema1)을 이용해 base_unit 재계산.
        매매비중1 = (user_seed * 0.2) / ema1
        이후, 심볼별 MIN_TRADE_AMOUNT 반영해 '내림(floor)' 처리.
        """
        if self.user_seed <= 0 or (self.ema1 is None) or (self.ema1 <= 0):
            return

        raw_base = (self.user_seed * 0.2) / self.ema1
        min_step = MIN_TRADE_AMOUNT.get(self.symbol, 0.0001)

        floored_value = math.floor(raw_base / min_step) * min_step

        if floored_value <= 0:
            logger.warning("[Strategy] base_unit 계산값이 0 이하입니다. (seed가 너무 작거나 price가 너무 높을 수 있음)")
            return

        self.base_unit = floored_value
        logger.trace(f"[Strategy] base_unit 갱신 => {self.base_unit} (min_step={min_step})")

    # ------------------------------------------------------
    # 매 틱마다 호출되는 함수
    # ------------------------------------------------------
    def on_new_price(self, ema1: float, ema2: float, ema3: float):
        """
        외부(쓰레드)에서 전달된 EMA1, EMA2, EMA3를 받아 전략을 수행
        """
        # (1) EMA 값 갱신
        self.prev_ema1 = self.ema1
        self.prev_ema2 = self.ema2
        self.prev_ema3 = self.ema3

        self.ema1 = ema1
        self.ema2 = ema2
        self.ema3 = ema3

        if self.ema1 is None or self.ema2 is None or self.ema3 is None:
            logger.trace("[Strategy] EMA 값 None -> 매매 스킵.")
            return

        # (2) 로깅 (Trace 레벨로 간단히)
        logger.trace(
            f"[Strategy] on_new_price => 현재가 EMA1={self.ema1:.4f}, EMA2={self.ema2}, EMA3={self.ema3}"
        )

        # (3) 휴식 여부
        if self.risk_manager and self.risk_manager.is_paused():
            logger.trace("[Strategy] 현재 휴식 중 => 매매 스킵.")
            return

        # (4) 무포 상태라면 base_unit 재계산
        if self.long_size == 0 and self.short_size == 0:
            self.update_base_unit()

        # (5) 전략 실행
        self._check_strategy()

    def _is_golden_cross(self) -> bool:
        """
        직전 틱에서 ema1 < ema2 이고, 이번 틱에서 ema1 > ema2 이면 골든 크로스
        """
        if self.prev_ema1 is None or self.prev_ema2 is None:
            return False
        if self.ema1 is None or self.ema2 is None:
            return False

        return (self.prev_ema1 <= self.prev_ema2) and (self.ema1 >= self.ema2)

    def _is_dead_cross(self) -> bool:
        """
        직전 틱에서 ema1 > ema2 이고, 이번 틱에서 ema1 < ema2 이면 데드 크로스
        """
        if self.prev_ema1 is None or self.prev_ema2 is None:
            return False
        if self.ema1 is None or self.ema2 is None:
            return False

        return (self.prev_ema1 >= self.prev_ema2) and (self.ema1 <= self.ema2)

    # ------------------------------------------------------
    # 매매 판단 로직 (EMA1=현재가로 사용)
    # ------------------------------------------------------
    def _check_strategy(self):
        """
        - 무포 상태:
          (E2>E3 + 골든) => 롱50
          (E2<E3 + 데드) => 숏50

        - 롱50 보유:
          1) 현재가 >= 진입가+0.05% & 데드 => 롱청산
          2) 현재가 <  진입가+0.05% & 데드 => 숏50(헷지)

        - 숏50 보유:
          1) 현재가 <= 진입가-0.05% & 골든 => 숏청산
          2) 현재가 >  진입가-0.05% & 골든 => 롱50(헷지)

        - 헷징 상태(롱>0 & 숏>0):
          골든 => 숏 2청산
          데드 => 롱 2청산

        ※ 여기서 "E2"는 self.ema2 (DOM 상 EMA3), "E3"는 self.ema3 (DOM 상 EMA7)를 의미.
        """
        current_price = self.ema1

        if self.long_size == 0 and self.short_size == 0:
            # E2>E3 + 골든 => 롱50
            if (self.ema2 > self.ema3) and self._is_golden_cross():
                # 직전에 발생한 골든크로스 가격과 현재 가격 비교
                if self.last_golden_cross_price == current_price:
                    logger.info("[Strategy] (무시) 동일 가격에서 골든크로스 연속 발생 => 이번엔 스킵.")
                    return
                self.last_golden_cross_price = current_price
                logger.info("[Strategy] 무포, E2>E3+골든 => 롱50")
                self._open_long_50()
                return
            # E2<E3 + 데드 => 숏50
            if (self.ema2 < self.ema3) and self._is_dead_cross():
                # 직전에 발생한 데드크로스 가격과 현재 가격 비교
                if self.last_dead_cross_price == current_price:
                    logger.info("[Strategy] (무시) 동일 가격에서 데드크로스 연속 발생 => 이번엔 스킵.")
                    return
                self.last_dead_cross_price = current_price
                logger.info("[Strategy] 무포, E2<E3+데드 => 숏50")
                self._open_short_50()
                return

        # (2) 롱50만 보유:
        elif self.long_size == 50 and self.short_size == 0:
            if self.long_entry_price > 0:
                up_diff = (current_price - self.long_entry_price) / self.long_entry_price
            else:
                up_diff = 0.0

            # +0.05% & 데드 => 롱청산
            if up_diff >= self.price_threshold and self._is_dead_cross():
                logger.info("[Strategy] (롱50) +0.05% & 데드 => 롱청산")
                self._close_long_50()
                return

            # <0.05% & 데드 => 숏50(헷지)
            if up_diff < self.price_threshold and self._is_dead_cross():
                logger.info("[Strategy] (롱50) <0.05% & 데드 => 숏50 헷지")
                self._open_short_50()
                return

        # (3) 숏50만 보유:
        elif self.long_size == 0 and self.short_size == 50:
            if self.short_entry_price > 0:
                down_diff = (current_price - self.short_entry_price) / self.short_entry_price
            else:
                down_diff = 0.0

            # -0.05% & 골든 => 숏청산
            if down_diff <= -self.price_threshold and self._is_golden_cross():
                logger.info("[Strategy] (숏50) -0.05% & 골든 => 숏청산")
                self._close_short_50()
                return

            # >-0.05% & 골든 => 롱50(헷지)
            if down_diff > -self.price_threshold and self._is_golden_cross():
                logger.info("[Strategy] (숏50) >-0.05% & 골든 => 롱50 헷지")
                self._open_long_50()
                return

        # (4) 헷징 상태(롱>0 & 숏>0)
        else:
            # 골든 => 숏 2청산
            if self._is_golden_cross():
                # 직전에 발생한 골든크로스 가격과 현재 가격 비교
                if self.last_golden_cross_price == current_price:
                    logger.info("[Strategy] (헷징) 동일 가격에서 골든크로스 연속 발생 => 이번엔 스킵.")
                    return
                self.last_golden_cross_price = current_price
                self.block_long2_clear = False  # 롱2 청산 다시 허용
                logger.info(f"[Strategy] (헷징) 골든 => 숏 2청산 (현재 숏={self.short_size})")
                self._close_short_2()

            # 데드 => 롱 2청산
            elif self._is_dead_cross():
                # 직전에 발생한 데드크로스 가격과 현재 가격 비교
                if self.last_dead_cross_price == current_price:
                    logger.info("[Strategy] (헷징) 동일 가격에서 데드크로스 연속 발생 => 이번엔 스킵.")
                    return
                self.last_dead_cross_price = current_price
                self.block_short2_clear = False  # 숏2 청산 다시 허용
                logger.info(f"[Strategy] (헷징) 데드 => 롱 2청산 (현재 롱={self.long_size})")
                self._close_long_2()
                
    # -------------------------------------
    # 포지션 열기 (롱/숏 50)
    # -------------------------------------
    def _open_long_50(self):
        if not self.order_executor:
            return
        qty = self.base_unit * 50

        max_tries = 3
        for attempt in range(max_tries):
            success = self.order_executor.place_market_order("LONG", qty)
            time.sleep(0.3)
            self._sync_with_dom()

            # long_size가 50 이상이 됐다면 진입 성공(전량 체결 가정)
            if success and self.long_size >= 50:
                # 체결 가격(실제 현재가)을 ema1 기준으로 기록
                real_price = self.ema1

                # 누적 거래금액 기록
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(real_price * qty)

                # 진입가 갱신
                self.long_entry_price = real_price

                # RiskManager 매매 기록
                if self.risk_manager:
                    if self.short_size > 0:
                        self.risk_manager.record_trade("HEDGE_LONG", last_entry_price=self.long_entry_price, close_price=real_price)
                    else:
                        self.risk_manager.record_trade("LONG50", last_entry_price=self.long_entry_price, close_price=real_price)

                self.last_trade_action = "OPEN_LONG_50"
                logger.info("[Strategy] 롱50 진입 성공.")
                return
            else:
                logger.warning(f"[Strategy] 롱50 주문 실패/부분체결 etc (시도 {attempt+1}/{max_tries}). 재시도.")

        logger.error("[Strategy] 롱50 주문이 최대 재시도 후에도 실패 or leftover 불충분.")

    def _open_short_50(self):
        if not self.order_executor:
            return
        qty = self.base_unit * 50

        max_tries = 3
        for attempt in range(max_tries):
            success = self.order_executor.place_market_order("SHORT", qty)
            time.sleep(0.3)
            self._sync_with_dom()

            if success and self.short_size >= 50:
                real_price = self.ema1

                # 누적 거래금액 기록
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(real_price * qty)

                # 진입가 갱신
                self.short_entry_price = real_price

                # RiskManager 매매 기록
                if self.risk_manager:
                    if self.long_size > 0:
                        self.risk_manager.record_trade("HEDGE_SHORT", last_entry_price=self.short_entry_price, close_price=real_price)
                    else:
                        self.risk_manager.record_trade("SHORT50", last_entry_price=self.short_entry_price, close_price=real_price)

                self.last_trade_action = "OPEN_SHORT_50"
                logger.info("[Strategy] 숏50 진입 성공.")
                return
            else:
                logger.warning(f"[Strategy] 숏50 주문 실패/부분체결 etc (시도 {attempt+1}/{max_tries}). 재시도.")

        logger.error("[Strategy] 숏50 주문이 최대 재시도 후에도 실패 or leftover 불충분.")

    # -------------------------------------
    # 전량 청산(롱/숏)
    # -------------------------------------
    def _close_long_50(self):
        """
        롱50만 보유 상태에서 전부 청산할 때 사용.
        """
        if self.long_size < 50 or not self.order_executor:
            return

        qty = self.base_unit * 50
        max_tries = 3
        for attempt in range(max_tries):
            success = self.order_executor.close_position("LONG", qty)
            time.sleep(0.3)
            self._sync_with_dom()

            # 롱 사이즈가 0이 됐다면 청산 성공
            if success and self.long_size == 0:
                # 청산 체결가
                close_price = self.ema1
                entry_p = self.long_entry_price

                # 누적 거래금액 & 실현손익
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(close_price * qty)
                    realized_pnl = (close_price - entry_p) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                # RiskManager 매매 기록
                if self.risk_manager:
                    self.risk_manager.record_trade("LONG50_CLOSED", last_entry_price=entry_p, close_price=close_price)

                # 진입가 리셋
                self.long_entry_price = 0.0

                logger.info("[Strategy] 롱50 청산 완료.")
                return
            else:
                logger.warning(f"[Strategy] 롱50 청산 leftover 남음 or 실패. 재시도 {attempt+1}/{max_tries}..")

        logger.error("[Strategy] 롱50 청산 재시도 후 leftover가 남아있을 수 있습니다.")

    def _close_short_50(self):
        """
        숏50만 보유 상태에서 전부 청산할 때 사용.
        """
        if self.short_size < 50 or not self.order_executor:
            return

        qty = self.base_unit * 50
        max_tries = 3
        for attempt in range(max_tries):
            success = self.order_executor.close_position("SHORT", qty)
            time.sleep(0.3)
            self._sync_with_dom()

            if success and self.short_size == 0:
                close_price = self.ema1
                entry_p = self.short_entry_price

                # 누적 거래금액 & 실현손익
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(close_price * qty)
                    realized_pnl = (entry_p - close_price) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                # RiskManager 매매 기록
                if self.risk_manager:
                    self.risk_manager.record_trade("SHORT50_CLOSED", last_entry_price=entry_p, close_price=close_price)

                self.short_entry_price = 0.0

                logger.info("[Strategy] 숏50 청산 완료.")
                return
            else:
                logger.warning(f"[Strategy] 숏50 청산 leftover 남음 or 실패. 재시도 {attempt+1}/{max_tries}..")

        logger.error("[Strategy] 숏50 청산 재시도 후 leftover가 남아있을 수 있습니다.")

    # ----------------------------------------------------
    # 헷지 상태에서 '2'씩 부분청산 (골든/데드 시)
    # ----------------------------------------------------
    def _close_long_2(self):
        """
        헷징 상태에서 '데드 크로스' 발생 시, 롱 포지션을 2만큼 부분청산한다.
        한 번에 2만 청산(=0.2코인 if base_unit=0.1).
        leftover가 남아 있어도 추가로 더 청산하진 않음.
        (버튼 클릭 등 주문 실패 시에만 최대 3번 재시도)
        """
        # (1) 롱2 청산 차단 상태 확인
        if self.block_long2_clear:
            logger.info("[Strategy] (부분청산) 롱2 차단 상태 => 이번엔 스킵")
            return

        # (2) 직전 액션이 "CLOSE_LONG_2" 였으면 스킵 => "롱2 → 또 롱2" 방지
        if self.last_trade_action == "CLOSE_LONG_2":
            logger.info("[Strategy] 직전에도 LONG2 부분청산 => 이번엔 스킵")
            return

        # (3) 롱 사이즈가 2 미만이면 청산할 필요 없음
        if self.long_size < 2 or not self.order_executor:
            logger.info("[Strategy] (부분청산) 롱 사이즈가 2 미만 => 청산 스킵.")
            return

        close_qty = self.base_unit * 2
        original_long = self.long_size

        max_attempts = 3
        for attempt in range(max_attempts):
            success = self.order_executor.close_position("LONG", close_qty)
            if success:
                logger.info(f"[Strategy] (부분청산) 롱 2 청산 시도 성공. (attempt={attempt+1}/{max_attempts})")
                break
            else:
                logger.warning(f"[Strategy] (부분청산) 롱 2 청산 실패, 재시도 {attempt+1}/{max_attempts}..")
            time.sleep(0.3)

        # 주문 시도 후 DOM 동기화
        time.sleep(0.3)
        self._sync_with_dom()

        # 실제로 청산된 양
        closed_amount = original_long - self.long_size
        logger.trace(f"[Strategy] (부분청산) 롱 실제 {closed_amount}만큼 청산됨. leftover={self.long_size}")

        if closed_amount > 0:
            close_price = self.ema1
            entry_p = self.long_entry_price

            # 누적 거래금액 & 실현손익
            if self.position_tracker:
                notional = close_price * (closed_amount * self.base_unit)
                self.position_tracker.add_trade_volume(notional)
                realized_pnl = (close_price - entry_p) * (closed_amount * self.base_unit)
                self.position_tracker.add_realized_pnl(realized_pnl)

            # 롱 포지션 사이즈가 0 이하가 됐다면 진입가 리셋
            if self.long_size <= 0:
                self.long_size = 0
                self.long_entry_price = 0.0
                if self.risk_manager:
                    self.risk_manager.record_trade("LONG_ALL_CLOSED", last_entry_price=entry_p, close_price=close_price)
            else:
                # 부분만 청산된 경우
                if self.risk_manager:
                    self.risk_manager.record_trade("LONG_PARTIAL_CLOSED", last_entry_price=entry_p, close_price=close_price)

            self.last_trade_action = "CLOSE_LONG_2"
            self.block_long2_clear = True  # 롱2 청산 재차단


    def _close_short_2(self):
        if self.block_short2_clear:
            logger.info("[Strategy] (부분청산) 숏2 차단 상태 => 이번엔 스킵")
            return

        if self.last_trade_action == "CLOSE_SHORT_2":
            logger.info("[Strategy] 직전에도 SHORT2 부분청산 => 이번엔 스킵")
            return

        if self.short_size < 2 or not self.order_executor:
            logger.info("[Strategy] (부분청산) 숏 사이즈가 2 미만 => 청산 스킵.")
            return

        close_qty = self.base_unit * 2
        original_short = self.short_size

        max_attempts = 3
        for attempt in range(max_attempts):
            success = self.order_executor.close_position("SHORT", close_qty)
            if success:
                logger.info(f"[Strategy] (부분청산) 숏 2 청산 시도 성공. (attempt={attempt+1}/{max_attempts})")
                break
            else:
                logger.warning(f"[Strategy] (부분청산) 숏 2 청산 실패, 재시도 {attempt+1}/{max_attempts}..")
            time.sleep(0.3)

        time.sleep(0.3)
        self._sync_with_dom()

        closed_amount = original_short - self.short_size
        logger.trace(f"[Strategy] (부분청산) 숏 실제 {closed_amount}만큼 청산됨. leftover={self.short_size}")

        if closed_amount > 0:
            close_price = self.ema1
            entry_p = self.short_entry_price

            # 누적 거래금액 & 실현손익
            if self.position_tracker:
                notional = close_price * (closed_amount * self.base_unit)
                self.position_tracker.add_trade_volume(notional)
                realized_pnl = (entry_p - close_price) * (closed_amount * self.base_unit)
                self.position_tracker.add_realized_pnl(realized_pnl)

            # 숏 포지션 사이즈가 0 이하가 됐다면 진입가 리셋
            if self.short_size <= 0:
                self.short_size = 0
                self.short_entry_price = 0.0
                if self.risk_manager:
                    self.risk_manager.record_trade("SHORT_ALL_CLOSED", last_entry_price=entry_p, close_price=close_price)
            else:
                if self.risk_manager:
                    self.risk_manager.record_trade("SHORT_PARTIAL_CLOSED", last_entry_price=entry_p, close_price=close_price)

            self.last_trade_action = "CLOSE_SHORT_2"
            self.block_short2_clear = True  # 숏2 청산 재차단

            
    # ---------------------------------------------
    # DOM 실제 포지션과 동기화
    # ---------------------------------------------
    def _sync_with_dom(self):
        """
        PositionTracker.get_open_positions()에서 현재 남은 롱/숏 수량을 읽어,
        strategy 내부 변수(self.long_size, self.short_size)도 일치시킨다.
        """
        if not self.position_tracker:
            return

        positions = self.position_tracker.get_open_positions()
        real_long = 0.0
        real_short = 0.0

        for pos in positions:
            side = pos.get("positionSide", "")
            size = pos.get("size", 0.0)
            if side.upper() == "LONG":
                real_long += size
            elif side.upper() == "SHORT":
                real_short += size

        # base_unit 기준으로 환산해서 정수 처리
        if self.base_unit > 0:
            self.long_size = int(round(real_long / self.base_unit))
            self.short_size = int(round(real_short / self.base_unit))
        else:
            # base_unit=0 등 예외상황일 경우 0으로 처리
            self.long_size = 0
            self.short_size = 0

        logger.trace(
            f"[Strategy] _sync_with_dom => 실제 롱={real_long:.4f}, 숏={real_short:.4f}, "
            f"전략 내부는 (long_size={self.long_size}, short_size={self.short_size})."
        )
