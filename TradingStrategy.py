class TradingStrategy:
    def __init__(self):
        self.position = None  # 현재 포지션 (LONG, SHORT, None)
    
    def check_signal(self, data):
        """
        수집된 RSI, MACD 데이터를 기반으로 매매 신호 체크
        """
        if "RSI" in data and "MACD" in data:
            rsi = data["RSI"].get("rsi", 50)  # 기본값 50
            macd = data["MACD"].get("macd", 0)
            signal = data["MACD"].get("signal", 0)

            # 매매 조건 설정
            if rsi < 30 and macd > signal:
                return "LONG"
            elif rsi > 70 and macd < signal:
                return "SHORT"
        
        return None  # 매매 조건이 충족되지 않음
