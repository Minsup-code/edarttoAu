# core/strategy.py

from loguru import logger
from config.config import (
    EMA_SHORT, EMA_MID, EMA_LONG, PRICE_THRESHOLD,
    MIN_TRADE_AMOUNT
)
import math

class TradingStrategy:
    """
    매매전략(EMA(1,3,7), ±0.05% 변동성, 헷징) 구현.
    'order_executor'로 실제 주문을 보내는 구조.
    """

    def __init__(self, symbol="BTC_USDT", position_tracker=None, risk_manager=None):
        # EMA
        self.ema1 = None  # EMA(1) 
        self.ema2 = None  # EMA(3)
        self.ema3 = None  # EMA(7)

        # 이전 틱에서의 ema1, ema2, ema3 (교차 방향 체크용)
        self.prev_ema1 = None
        self.prev_ema2 = None
        self.prev_ema3 = None
        self.prev_price = None

        # alpha값 (EMA_SHORT=1, EMA_MID=3, EMA_LONG=7) → 2/(N+1)
        self.alpha_1 = 2 / (EMA_SHORT + 1)  # 2/(1+1) = 1
        self.alpha_3 = 2 / (EMA_MID + 1)   # 2/(3+1) = 0.5
        self.alpha_7 = 2 / (EMA_LONG + 1)  # 2/(7+1) = 0.25

        # 현재 보유 포지션 크기(기록용)
        self.long_size = 0
        self.short_size = 0

        # 포지션 진입가 
        self.long_entry_price = 0.0
        self.short_entry_price = 0.0

        # 변동성 기준
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

        # 최근 시세
        self.current_price = 0.0

    def set_order_executor(self, executor):
        self.order_executor = executor

    def set_user_seed(self, seed: float):
        self.user_seed = seed

    # ------------------------------------------------------
    # 매매비중1 계산 + 최소거래단위 반영 (floor)
    # ------------------------------------------------------
    def update_base_unit(self, current_price: float):
        """
        무포지션 상태에서 현재가로부터 base_unit을 재계산.
        매매비중1 = (user_seed * 0.2) / current_price
        이후, 심볼별 MIN_TRADE_AMOUNT 반영해 '내림(floor)' 처리.
        """
        if self.user_seed <= 0 or current_price <= 0:
            return

        raw_base = (self.user_seed * 0.2) / current_price
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
    def on_new_price(self, price: float, candle_closed: bool=False):
        """
        - price: 현재 시세 (실시간 종가)
        - candle_closed: 1분봉이 막 닫혔다면 True, 아니라면 False
                         (실시간 중간 틱이면 False)
        """
        self.current_price = price

        # (1) EMA 업데이트 (실시간)
        self._update_ema(price, candle_closed)


        # (2) 휴식 여부 체크
        if self.risk_manager and self.risk_manager.is_paused():
            logger.trace("[Strategy] 현재 휴식 중 => 매매 스킵.")
            return

        # (3) 무포지션이면 base_unit 재계산
        if self.long_size == 0 and self.short_size == 0:
            self.update_base_unit(price)

        # (4) 전략 실행
        self._check_strategy(current_price=price)


    def price_in_range(self, current_price, previous_price, threshold=0.0005):
        """
        현재 가격이 이전 가격과 비교하여 일정 범위 내에 있는지 확인
        :param current_price: 현재 가격
        :param previous_price: 이전 가격
        :param threshold: 변동 범위 (기본값 0.0005)
        :return: 가격이 범위 내에 있으면 True, 아니면 False
        """
        return abs(current_price - previous_price) < threshold

    def _update_ema(self, price: float, candle_closed):
        """
        EMA 값을 실시간 가격으로 즉시 업데이트.
        이동 평균 개념을 반영하여 계산.
        """
        # 이전 값 기록 (크로스 비교용)
        self.prev_ema1 = self.ema1
        self.prev_ema2 = self.ema2
        self.prev_ema3 = self.ema3

        # EMA 업데이트 (이전값이 없으면 현재가로 초기화)
        self.ema1 = price if self.ema1 is None else (price * self.alpha_1 + self.ema1 * (1 - self.alpha_1))
        self.ema2 = price if self.ema2 is None else (price * self.alpha_3 + self.ema2 * (1 - self.alpha_3))
        self.ema3 = price if self.ema3 is None else (price * self.alpha_7 + self.ema3 * (1 - self.alpha_7))

        # prev_price 초기화
        if self.prev_price is None:
            self.prev_price = price
            return

        # 가격 변동이 너무 적으면 거래하지 않음
        if self._price_in_range(price, self.prev_price, threshold=0.0001):
            return  # 0.0001 이하의 변동이면 무시

        # 이전 가격 갱신
        self.prev_price = price


    def _price_in_range(self, current_price: float, previous_price: float, threshold: float = 0.0001) -> bool:
        """
        두 가격이 threshold 범위 내에서 변동했는지 확인하는 함수.
        변동이 작으면 True를 반환하여 매매를 방지.
        """
        return abs(current_price - previous_price) < threshold



    def _is_golden_cross(self) -> bool:
        """
        직전 틱에서 ema1 < ema2 이고, 이번 틱에서 ema1 > ema2 이면 골든 크로스
        """
        if self.prev_ema1 is None or self.prev_ema2 is None:
            return False
        return (self.prev_ema1 < self.prev_ema2) and (self.ema1 > self.ema2)

    def _is_dead_cross(self) -> bool:
        """
        직전 틱에서 ema1 > ema2 이고, 이번 틱에서 ema1 < ema2 이면 데드 크로스
        """
        if self.prev_ema1 is None or self.prev_ema2 is None:
            return False
        return (self.prev_ema1 > self.prev_ema2) and (self.ema1 < self.ema2)

    # ------------------------------------------------------
    # 매매 판단 로직
    # ------------------------------------------------------
    def _check_strategy(self, current_price: float):
        """
        - 무포 상태:
          (E2>E3 + 골든) => 롱50
          (E2<E3 + 데드) => 숏50

        - 롱50 보유:
          1) 현재가 >= 진입가+0.05% & 데드 => 롱청산
          2) 현재가 <  진입가+0.05% & 골든 => 숏50(헷지)

        - 숏50 보유:
          1) 현재가 <= 진입가-0.05% & 골든 => 숏청산
          2) 현재가 >  진입가-0.05% & 데드 => 롱50(헷지)

        - 헷징 상태(롱>0 & 숏>0):
          골든 => 숏 부분청산
          데드 => 롱 부분청산

        ※ 연속된 골든/데드 크로스라도 건너뛰지 않도록
          (self.last_closed_side 관련 로직 제거)
        """
        # (1) 무포
        if self.long_size == 0 and self.short_size == 0:
            if (self.ema2 > self.ema3) and self._is_golden_cross():
                logger.info("[Strategy] 무포, E2>E3+골든 => 롱50")
                self._open_long_50()
                return
            if (self.ema2 < self.ema3) and self._is_dead_cross():
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
                self._close_long_50()
                logger.info("[Strategy] (롱50) +0.05% & 데드 => 롱청산")
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
        elif self.long_size > 0 or self.short_size > 0:
            logger.trace(f"[Strategy] 헷지 상태: long_size={self.long_size}, short_size={self.short_size}")

            # 골든 신호 => 숏 부분청산 
            if self._is_golden_cross():
                # 숏 부분청산 or 전량청산
                if self.short_size < 2:
                    logger.info("[Strategy] (헷징) 골든 => 숏 전량청산 (잔량 < 2)")
                    self._close_short_all()
                else:
                    logger.info(f"[Strategy] (헷징) 골든 => 숏 2청산 (현재 숏={self.short_size})")
                    self._close_short(2)

            # 데드 신호 => 롱 부분청산
            elif self._is_dead_cross():
                # 롱 부분청산 or 전량청산
                if self.long_size < 2:
                    logger.info("[Strategy] (헷징) 데드 => 롱 전량청산 (잔량 < 2)")
                    self._close_long_all()
                else:
                    logger.info(f"[Strategy] (헷징) 데드 => 롱 2청산 (현재 롱={self.long_size})")
                    self._close_long(2)

    # -------------------------------------
    # 포지션 열기 (롱/숏 50)
    # -------------------------------------
    def _open_long_50(self):
        if not self.order_executor:
            return
        qty = self.base_unit * 50
        success = self.order_executor.place_market_order("LONG", qty)
        if success:
            self.long_size = 50
            real_price = self.current_price
            if self.position_tracker:
                self.position_tracker.add_trade_volume(real_price * qty)
            self.long_entry_price = real_price

            # RiskManager 매매 기록
            if self.risk_manager:
                if self.short_size > 0:
                    self.risk_manager.record_trade("HEDGE_LONG", last_entry_price=self.long_entry_price, close_price=real_price)
                else:
                    self.risk_manager.record_trade("LONG50", last_entry_price=self.long_entry_price, close_price=real_price)

    def _open_short_50(self):
        if not self.order_executor:
            return
        qty = self.base_unit * 50
        success = self.order_executor.place_market_order("SHORT", qty)
        if success:
            self.short_size = 50
            real_price = self.current_price
            if self.position_tracker:
                self.position_tracker.add_trade_volume(real_price * qty)
            self.short_entry_price = real_price

            if self.risk_manager:
                if self.long_size > 0:
                    self.risk_manager.record_trade("HEDGE_SHORT", last_entry_price=self.short_entry_price, close_price=real_price)
                else:
                    self.risk_manager.record_trade("SHORT50", last_entry_price=self.short_entry_price, close_price=real_price)

    # -------------------------------------
    # 전량/부분 청산
    # -------------------------------------
    def _close_long_all(self):
        if self.long_size > 0 and self.order_executor:
            qty = self.base_unit * self.long_size
            entry_p = self.long_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("LONG", qty)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * qty)
                    realized_pnl = (current_p - entry_p) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.long_size = 0
                self.long_entry_price = 0.0

                if self.risk_manager:
                    self.risk_manager.record_trade("LONG_ALL_CLOSED", last_entry_price=entry_p, close_price=current_p)

    def _close_short_all(self):
        if self.short_size > 0 and self.order_executor:
            qty = self.base_unit * self.short_size
            entry_p = self.short_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("SHORT", qty)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * qty)
                    realized_pnl = (entry_p - current_p) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.short_size = 0
                self.short_entry_price = 0.0

                if self.risk_manager:
                    self.risk_manager.record_trade("SHORT_ALL_CLOSED", last_entry_price=entry_p, close_price=current_p)

    def _close_long_50(self):
        if self.long_size == 50 and self.order_executor:
            qty = self.base_unit * 50
            entry_p = self.long_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("LONG", qty)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * qty)
                    realized_pnl = (current_p - entry_p) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.long_size = 0
                self.long_entry_price = 0.0

                if self.risk_manager:
                    self.risk_manager.record_trade("LONG50_CLOSED", last_entry_price=entry_p, close_price=current_p)

    def _close_short_50(self):
        if self.short_size == 50 and self.order_executor:
            qty = self.base_unit * 50
            entry_p = self.short_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("SHORT", qty)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * qty)
                    realized_pnl = (entry_p - current_p) * qty
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.short_size = 0
                self.short_entry_price = 0.0

                if self.risk_manager:
                    self.risk_manager.record_trade("SHORT50_CLOSED", last_entry_price=entry_p, close_price=current_p)

    def _close_long(self, amt: float):
        if self.long_size > 0 and self.order_executor:
            close_amt = self.base_unit * amt
            entry_p = self.long_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("LONG", close_amt)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * close_amt)
                    realized_pnl = (current_p - entry_p) * close_amt
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.long_size -= amt
                if self.long_size <= 0:
                    self.long_size = 0
                    self.long_entry_price = 0.0
                    if self.risk_manager:
                        self.risk_manager.record_trade("LONG_ALL_CLOSED", last_entry_price=entry_p, close_price=current_p)

    def _close_short(self, amt: float):
        if self.short_size > 0 and self.order_executor:
            close_amt = self.base_unit * amt
            entry_p = self.short_entry_price
            current_p = self.current_price

            success = self.order_executor.close_position("SHORT", close_amt)
            if success:
                if self.position_tracker:
                    self.position_tracker.add_trade_volume(current_p * close_amt)
                    realized_pnl = (entry_p - current_p) * close_amt
                    self.position_tracker.add_realized_pnl(realized_pnl)

                self.short_size -= amt
                if self.short_size <= 0:
                    self.short_size = 0
                    self.short_entry_price = 0.0
                    if self.risk_manager:
                        self.risk_manager.record_trade("SHORT_ALL_CLOSED", last_entry_price=entry_p, close_price=current_p)
