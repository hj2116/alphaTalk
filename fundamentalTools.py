import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

class FundamentalAnalyzer:
    def __init__(self):
        # DART API Key (한국 공시)
        self.dart_api_key = os.getenv("DART_API_KEY")
        
        # SEC API 설정 (미국 공시)
        self.sec_headers = {
            'User-Agent': 'alphaTalk Investment Analysis (your-email@example.com)',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'data.sec.gov'
        }
    
    def get_korean_fundamental_data(self, corp_code):
        """한국 기업의 DART 공시 데이터를 가져옵니다."""
        try:
            if not self.dart_api_key:
                return {"error": "DART API key not found"}
            
            # 최근 사업보고서 조회
            url = "https://opendart.fss.or.kr/api/list.json"
            params = {
                'crtfc_key': self.dart_api_key,
                'corp_code': corp_code,
                'bgn_de': (datetime.now() - timedelta(days=365)).strftime('%Y%m%d'),
                'pblntf_ty': 'A',  # 정기공시
                'page_no': 1,
                'page_count': 10
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"DART API error: {response.status_code}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def get_us_fundamental_data(self, ticker):
        """미국 기업의 SEC 공시 데이터를 가져옵니다."""
        try:
            # SEC CIK 조회
            cik_url = f"https://data.sec.gov/submissions/CIK{ticker}.json"
            response = requests.get(cik_url, headers=self.sec_headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"SEC API error: {response.status_code}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_financial_ratios(self, ticker):
        """재무비율을 계산합니다."""
        try:
            stock = yf.Ticker(ticker)
            
            # 재무제표 데이터 가져오기
            financials = stock.financials
            balance_sheet = stock.balance_sheet
            cashflow = stock.cashflow
            info = stock.info
            
            if financials.empty or balance_sheet.empty:
                return {"error": "Financial data not available"}
            
            # 최신 연도 데이터
            latest_year = financials.columns[0]
            
            # 수익성 지표
            revenue = financials.loc['Total Revenue', latest_year] if 'Total Revenue' in financials.index else 0
            net_income = financials.loc['Net Income', latest_year] if 'Net Income' in financials.index else 0
            total_assets = balance_sheet.loc['Total Assets', latest_year] if 'Total Assets' in balance_sheet.index else 0
            shareholders_equity = balance_sheet.loc['Stockholders Equity', latest_year] if 'Stockholders Equity' in balance_sheet.index else 0
            
            # ROA, ROE 계산
            roa = (net_income / total_assets * 100) if total_assets != 0 else 0
            roe = (net_income / shareholders_equity * 100) if shareholders_equity != 0 else 0
            
            # Gross Margin 계산
            gross_profit = financials.loc['Gross Profit', latest_year] if 'Gross Profit' in financials.index else 0
            gross_margin = (gross_profit / revenue * 100) if revenue != 0 else 0
            
            # Asset Growth 계산 (전년 대비)
            if len(balance_sheet.columns) > 1:
                prev_assets = balance_sheet.loc['Total Assets', balance_sheet.columns[1]]
                asset_growth = ((total_assets - prev_assets) / prev_assets * 100) if prev_assets != 0 else 0
            else:
                asset_growth = 0
            
            return {
                "revenue": revenue,
                "net_income": net_income,
                "total_assets": total_assets,
                "shareholders_equity": shareholders_equity,
                "roa": round(roa, 2),
                "roe": round(roe, 2),
                "gross_margin": round(gross_margin, 2),
                "asset_growth": round(asset_growth, 2),
                "market_cap": info.get('marketCap', 0),
                "pe_ratio": info.get('trailingPE', 0),
                "pb_ratio": info.get('priceToBook', 0)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_earnings_surprise(self, ticker):
        """어닝 서프라이즈 분석"""
        try:
            stock = yf.Ticker(ticker)
            
            # 최근 4분기 실적 데이터
            quarterly_financials = stock.quarterly_financials
            
            if quarterly_financials.empty:
                return {"error": "Quarterly data not available"}
            
            # EPS 추이 분석
            eps_data = []
            for i, quarter in enumerate(quarterly_financials.columns[:4]):
                if 'Net Income' in quarterly_financials.index:
                    net_income = quarterly_financials.loc['Net Income', quarter]
                    eps_data.append({
                        "quarter": quarter.strftime('%Y-Q%q') if hasattr(quarter, 'strftime') else str(quarter),
                        "net_income": net_income,
                        "quarter_index": i
                    })
            
            # 실적 모멘텀 계산 (최근 분기가 이전 분기보다 개선되었는지)
            momentum_positive = False
            if len(eps_data) >= 2:
                recent_income = eps_data[0]['net_income']
                prev_income = eps_data[1]['net_income']
                momentum_positive = recent_income > prev_income
            
            return {
                "eps_data": eps_data,
                "fundamental_momentum": momentum_positive,
                "momentum_description": "최근 실적이 개선되고 있음" if momentum_positive else "최근 실적이 둔화되고 있음"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def analyze_interest_rate_impact(self, ticker):
        """금리 관점에서 주가 분석"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 부채비율 계산
            debt_to_equity = info.get('debtToEquity', 0)
            
            # 금리 민감도 분석
            sector = info.get('sector', '')
            
            # 금리 민감 섹터 판별
            interest_sensitive_sectors = [
                'Real Estate', 'Utilities', 'Financial Services', 
                'Consumer Discretionary', 'Technology'
            ]
            
            is_interest_sensitive = sector in interest_sensitive_sectors
            
            # 금리 영향도 점수 (1-10)
            interest_impact_score = 5  # 기본값
            
            if debt_to_equity > 50:
                interest_impact_score += 2  # 부채 높음
            if is_interest_sensitive:
                interest_impact_score += 2  # 금리 민감 섹터
            if info.get('beta', 1) > 1.2:
                interest_impact_score += 1  # 높은 베타
                
            return {
                "debt_to_equity": debt_to_equity,
                "sector": sector,
                "is_interest_sensitive": is_interest_sensitive,
                "interest_impact_score": min(interest_impact_score, 10),
                "analysis": f"금리 영향도: {min(interest_impact_score, 10)}/10 - " + 
                           ("높은 금리 민감도" if interest_impact_score > 7 else 
                            "중간 금리 민감도" if interest_impact_score > 5 else "낮은 금리 민감도")
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_earnings_calendar(self, ticker):
        """실적발표 일정 분석"""
        try:
            stock = yf.Ticker(ticker)
            
            # 다음 실적발표일 (yfinance에서 제공하는 경우)
            calendar = stock.calendar
            
            if calendar is not None and not calendar.empty:
                next_earnings = calendar.index[0] if len(calendar) > 0 else None
                return {
                    "next_earnings_date": next_earnings.strftime('%Y-%m-%d') if next_earnings else "정보 없음",
                    "calendar_available": True
                }
            else:
                return {
                    "next_earnings_date": "정보 없음",
                    "calendar_available": False
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def comprehensive_fundamental_analysis(self, ticker):
        """종합적인 펀더멘털 분석"""
        print(f"=== {ticker} 펀더멘털 분석 시작 ===")
        
        # 각종 분석 수행
        financial_ratios = self.calculate_financial_ratios(ticker)
        earnings_analysis = self.analyze_earnings_surprise(ticker)
        interest_analysis = self.analyze_interest_rate_impact(ticker)
        earnings_calendar = self.get_earnings_calendar(ticker)
        
        # 결과 종합
        analysis_result = {
            "ticker": ticker,
            "analysis_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "financial_ratios": financial_ratios,
            "earnings_analysis": earnings_analysis,
            "interest_rate_analysis": interest_analysis,
            "earnings_calendar": earnings_calendar
        }
        
        return analysis_result
    
    def format_fundamental_report(self, analysis_data):
        """펀더멘털 분석 결과를 텍스트로 포맷팅"""
        ticker = analysis_data.get('ticker', 'N/A')
        
        # 재무비율 데이터
        ratios = analysis_data.get('financial_ratios', {})
        earnings = analysis_data.get('earnings_analysis', {})
        interest = analysis_data.get('interest_rate_analysis', {})
        calendar = analysis_data.get('earnings_calendar', {})
        
        report = f"""
=== {ticker} 종합 펀더멘털 분석 보고서 ===

## 1. 핵심 재무지표
- 매출액: {ratios.get('revenue', 'N/A'):,} 원
- 순이익: {ratios.get('net_income', 'N/A'):,} 원  
- 총자산: {ratios.get('total_assets', 'N/A'):,} 원
- 자기자본: {ratios.get('shareholders_equity', 'N/A'):,} 원

## 2. 수익성 지표
- ROA (총자산이익률): {ratios.get('roa', 'N/A')}%
- ROE (자기자본이익률): {ratios.get('roe', 'N/A')}%
- Gross Margin (매출총이익률): {ratios.get('gross_margin', 'N/A')}%
- Asset Growth (자산성장률): {ratios.get('asset_growth', 'N/A')}%

## 3. 밸류에이션
- 시가총액: {ratios.get('market_cap', 'N/A'):,} 원
- PER (주가수익비율): {ratios.get('pe_ratio', 'N/A')}
- PBR (주가순자산비율): {ratios.get('pb_ratio', 'N/A')}

## 4. 실적 모멘텀 분석
- Fundamental Momentum: {earnings.get('momentum_description', 'N/A')}
- 최근 분기 실적 추이: {"개선" if earnings.get('fundamental_momentum', False) else "둔화"}

## 5. 금리 민감도 분석
- 부채비율: {interest.get('debt_to_equity', 'N/A')}%
- 섹터: {interest.get('sector', 'N/A')}
- {interest.get('analysis', 'N/A')}

## 6. 실적발표 일정
- 다음 실적발표일: {calendar.get('next_earnings_date', 'N/A')}

## 7. 종합 평가
"""
        
        # 종합 점수 계산
        score = 0
        factors = []
        
        if ratios.get('roe', 0) > 15:
            score += 2
            factors.append("높은 ROE")
        elif ratios.get('roe', 0) > 10:
            score += 1
            factors.append("양호한 ROE")
            
        if earnings.get('fundamental_momentum', False):
            score += 2
            factors.append("실적 개선 추세")
            
        if ratios.get('asset_growth', 0) > 5:
            score += 1
            factors.append("자산 성장")
            
        if interest.get('interest_impact_score', 5) < 6:
            score += 1
            factors.append("낮은 금리 민감도")
        
        if score >= 5:
            grade = "매우 우수"
        elif score >= 3:
            grade = "우수" 
        elif score >= 2:
            grade = "보통"
        else:
            grade = "주의 필요"
            
        report += f"""
펀더멘털 종합 점수: {score}/6 ({grade})
주요 강점: {', '.join(factors) if factors else '특별한 강점 없음'}

※ 이 분석은 공개된 재무 데이터를 바탕으로 한 것이며, 투자 결정 시 추가적인 분석이 필요합니다.
        """
        
        return report


# 사용 예시 함수
def analyze_fundamental(ticker):
    """펀더멘털 분석 실행 함수"""
    analyzer = FundamentalAnalyzer()
    
    # 종합 분석 수행
    analysis_result = analyzer.comprehensive_fundamental_analysis(ticker)
    
    # 보고서 포맷팅
    report = analyzer.format_fundamental_report(analysis_result)
    
    return report


if __name__ == "__main__":
    # 테스트
    test_ticker = "005930.KS"  # 삼성전자
    result = analyze_fundamental(test_ticker)
    print(result) 