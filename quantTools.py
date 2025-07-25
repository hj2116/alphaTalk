import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

class QuantTools:
    def __init__(self):
        pass

    def getCounterTrendStrategy(self, ticker, kValue, nDays):
        """Counter Trend Strategy 구현 (간단한 볼린저 밴드 기반)"""
        try:
            data = get_daily_candles(ticker, nDays)
            if data.empty:
                return {"error": "No data available"}
            
            # 볼린저 밴드 계산
            data['MA'] = data['Close'].rolling(window=20).mean()
            data['STD'] = data['Close'].rolling(window=20).std()
            data['Upper'] = data['MA'] + (kValue * data['STD'])
            data['Lower'] = data['MA'] - (kValue * data['STD'])
            
            current_price = data['Close'].iloc[-1]
            upper_band = data['Upper'].iloc[-1]
            lower_band = data['Lower'].iloc[-1]
            
            if current_price <= lower_band:
                signal = "BUY"  # 과매도
            elif current_price >= upper_band:
                signal = "SELL"  # 과매수
            else:
                signal = "HOLD"
                
            return {
                "signal": signal,
                "current_price": current_price,
                "upper_band": upper_band,
                "lower_band": lower_band,
                "ma": data['MA'].iloc[-1]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def getTrendFollowingStrategy(self, ticker, shortPeriod, longPeriod):
        """Trend Following Strategy 구현 (이동평균 교차)"""
        try:
            data = get_daily_candles(ticker, max(shortPeriod, longPeriod) + 10)
            if data.empty:
                return {"error": "No data available"}
            
            # 단기/장기 이동평균 계산
            data['MA_Short'] = data['Close'].rolling(window=shortPeriod).mean()
            data['MA_Long'] = data['Close'].rolling(window=longPeriod).mean()
            
            current_short = data['MA_Short'].iloc[-1]
            current_long = data['MA_Long'].iloc[-1]
            prev_short = data['MA_Short'].iloc[-2]
            prev_long = data['MA_Long'].iloc[-2]
            
            # 골든크로스/데드크로스 확인
            if prev_short <= prev_long and current_short > current_long:
                signal = "BUY"  # 골든크로스
            elif prev_short >= prev_long and current_short < current_long:
                signal = "SELL"  # 데드크로스
            elif current_short > current_long:
                signal = "HOLD_BULLISH"  # 상승 추세 유지
            else:
                signal = "HOLD_BEARISH"  # 하락 추세 유지
                
            return {
                "signal": signal,
                "ma_short": current_short,
                "ma_long": current_long,
                "current_price": data['Close'].iloc[-1]
            }
        except Exception as e:
            return {"error": str(e)}
    
def get_daily_candles(ticker, nDays):
    # 한국 주식 코드 (6자리 숫자)인 경우 .KS 접미사 추가
    if re.match(r'^\d{6}$', ticker):
        ticker = f"{ticker}.KS"
    
    data = yf.Ticker(ticker).history(period=f"{nDays}d")
    return data
