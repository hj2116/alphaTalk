import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
from dotenv import load_dotenv
import os
import re

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
    
    def get_naver_finance_data(self, code):
        """
        네이버 금융에서 종목코드(code)에 해당하는 기업의
        1) 연간 및 분기 재무제표
        2) 동일업종 비교 지표
        를 불러오는 함수
        """
        try:
            URL = f"https://finance.naver.com/item/main.nhn?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(URL, headers=headers)
            
            if r.status_code != 200:
                return None, None, None, {"error": f"HTTP {r.status_code}"}
            
            tables = pd.read_html(r.text)
            
            annual_data, quarter_data, industry_df = None, None, None
            
            try:
                for i in range(3, min(7, len(tables))):
                    try:
                        finance_df = tables[i]
                        if len(finance_df.columns) >= 3 and '최근 연간 실적' in str(finance_df.columns):
                            finance_df.set_index(finance_df.columns[0], inplace=True)
                            finance_df.index.rename('주요재무정보', inplace=True)
                            
                            if finance_df.columns.nlevels > 1:
                                finance_df.columns = finance_df.columns.droplevel(-1)
                            
                            annual_data = finance_df.xs('최근 연간 실적', axis=1) if '최근 연간 실적' in finance_df.columns else None
                            quarter_data = finance_df.xs('최근 분기 실적', axis=1) if '최근 분기 실적' in finance_df.columns else None
                            break
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"재무제표 데이터를 불러오는 중 오류 발생: {e}")
            
            try:
                for i in range(4, min(8, len(tables))):
                    try:
                        industry_df = tables[i]
                        if len(industry_df.columns) >= 2 and any('업종' in str(col) for col in industry_df.columns):
                            industry_df.set_index(industry_df.columns[0], inplace=True)
                            break
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"동일업종 비교 데이터를 불러오는 중 오류 발생: {e}")
            
            return annual_data, quarter_data, industry_df, {"success": True}
            
        except Exception as e:
            return None, None, None, {"error": str(e)}
    
    def get_korean_fundamental_data(self, corp_code):
        """한국 기업의 DART 공시 데이터를 가져옵니다."""
        try:
            if not self.dart_api_key:
                return {"error": "DART API key not found"}
            
            url = "https://opendart.fss.or.kr/api/list.json"
            params = {
                'crtfc_key': self.dart_api_key,
                'corp_code': corp_code,
                'bgn_de': (datetime.now() - timedelta(days=365)).strftime('%Y%m%d'),
                'pblntf_ty': 'A',  
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
            cik_url = f"https://data.sec.gov/submissions/CIK{ticker}.json"
            response = requests.get(cik_url, headers=self.sec_headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"SEC API error: {response.status_code}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def extract_korean_code(self, ticker):
        """티커에서 한국 종목코드 추출"""
        if '.KS' in ticker or '.KQ' in ticker:
            return ticker.replace('.KS', '').replace('.KQ', '')
        elif ticker.isdigit() and len(ticker) == 6:
            return ticker
        else:
            return None
    
    def analyze_naver_financial_ratios(self, ticker):
        """네이버 금융 데이터를 활용한 재무비율 분석"""
        try:
            code = self.extract_korean_code(ticker)
            
            if not code:
                return self.calculate_financial_ratios_yfinance(ticker)
            
            annual_data, quarter_data, industry_df, status = self.get_naver_finance_data(code)
            
            if "error" in status:
                return {"error": f"네이버 데이터 수집 실패: {status['error']}"}
            
            if annual_data is None:
                return {"error": "재무데이터를 찾을 수 없습니다"}
            
            financial_metrics = {}
            
            revenue_keys = ['매출액', '수익(매출액)', '매출']
            for key in revenue_keys:
                if key in annual_data.index:
                    financial_metrics['revenue'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    break
            
            operating_income_keys = ['영업이익', '영업손익']
            for key in operating_income_keys:
                if key in annual_data.index:
                    financial_metrics['operating_income'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    break
            
            net_income_keys = ['당기순이익', '순이익', '당기순손익']
            for key in net_income_keys:
                if key in annual_data.index:
                    financial_metrics['net_income'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    break
            
            if 'ROE' in annual_data.index:
                financial_metrics['roe'] = self.parse_percentage(annual_data.loc['ROE'].iloc[0])
            if 'ROA' in annual_data.index:
                financial_metrics['roa'] = self.parse_percentage(annual_data.loc['ROA'].iloc[0])
            
            if '부채비율' in annual_data.index:
                financial_metrics['debt_ratio'] = self.parse_percentage(annual_data.loc['부채비율'].iloc[0])
            
            if '유동비율' in annual_data.index:
                financial_metrics['current_ratio'] = self.parse_percentage(annual_data.loc['유동비율'].iloc[0])
            
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                financial_metrics['pe_ratio'] = info.get('trailingPE', 0)
                financial_metrics['pb_ratio'] = info.get('priceToBook', 0)
                financial_metrics['market_cap'] = info.get('marketCap', 0)
            except:
                pass
            industry_comparison = {}
            if industry_df is not None:
                try:
                    for idx in industry_df.index:
                        if len(industry_df.columns) >= 2:
                            industry_comparison[idx] = {
                                'company': industry_df.iloc[industry_df.index.get_loc(idx), 0],
                                'industry_avg': industry_df.iloc[industry_df.index.get_loc(idx), 1] if len(industry_df.columns) > 1 else 'N/A'
                            }
                except Exception as e:
                    print(f"업종 비교 데이터 처리 오류: {e}")
            
            return {
                "source": "naver_finance",
                "financial_metrics": financial_metrics,
                "industry_comparison": industry_comparison,
                "quarter_data_available": quarter_data is not None,
                "annual_data_available": annual_data is not None
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def parse_financial_value(self, value):
        """재무 수치 파싱 (네이버 금융은 이미 억원 단위)"""
        try:
            if pd.isna(value) or value == '' or value == '-':
                return 0
            
            if isinstance(value, (int, float)):
                return int(value * 100000000)  
            
            value_str = str(value).replace(',', '').replace(' ', '')
            
            if '조' in value_str:
                number = float(re.findall(r'[\d.]+', value_str)[0])
                return int(number * 1000000000000)  
            elif '억' in value_str:
                number = float(re.findall(r'[\d.]+', value_str)[0])
                return int(number * 100000000)  
            else:
                numbers = re.findall(r'[\d.]+', value_str)
                if numbers:
                    return int(float(numbers[0]) * 100000000)  
                else:
                    return 0
                
        except Exception as e:
            return 0
    
    def parse_percentage(self, value):
        """퍼센트 값 파싱"""
        try:
            if pd.isna(value) or value == '' or value == '-':
                return 0
            
            value_str = str(value).replace('%', '').replace(' ', '')
            numbers = re.findall(r'[-+]?[\d.]+', value_str)
            return float(numbers[0]) if numbers else 0
            
        except Exception as e:
            return 0
    
    def calculate_financial_ratios_yfinance(self, ticker):
        """yfinance를 활용한 재무비율 계산 (해외 종목용)"""
        try:
            stock = yf.Ticker(ticker)
            
            financials = stock.financials
            balance_sheet = stock.balance_sheet
            cashflow = stock.cashflow
            info = stock.info
            
            if financials.empty or balance_sheet.empty:
                return {"error": "Financial data not available"}
            
            latest_year = financials.columns[0]
            
            revenue = financials.loc['Total Revenue', latest_year] if 'Total Revenue' in financials.index else 0
            net_income = financials.loc['Net Income', latest_year] if 'Net Income' in financials.index else 0
            total_assets = balance_sheet.loc['Total Assets', latest_year] if 'Total Assets' in balance_sheet.index else 0
            shareholders_equity = balance_sheet.loc['Stockholders Equity', latest_year] if 'Stockholders Equity' in balance_sheet.index else 0
            
            roa = (net_income / total_assets * 100) if total_assets != 0 else 0
            roe = (net_income / shareholders_equity * 100) if shareholders_equity != 0 else 0
            
            gross_profit = financials.loc['Gross Profit', latest_year] if 'Gross Profit' in financials.index else 0
            gross_margin = (gross_profit / revenue * 100) if revenue != 0 else 0
            
            if len(balance_sheet.columns) > 1:
                prev_assets = balance_sheet.loc['Total Assets', balance_sheet.columns[1]]
                asset_growth = ((total_assets - prev_assets) / prev_assets * 100) if prev_assets != 0 else 0
            else:
                asset_growth = 0
            
            return {
                "source": "yfinance",
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
    
    def calculate_financial_ratios(self, ticker):
        """통합 재무비율 계산 (네이버 + yfinance)"""
        result = self.analyze_naver_financial_ratios(ticker)
        
        if "error" in result:
            print(f"네이버 데이터 실패, yfinance로 전환: {result['error']}")
            return self.calculate_financial_ratios_yfinance(ticker)
        
        return result
    
    def analyze_earnings_surprise(self, ticker):
        """어닝 서프라이즈 분석"""
        try:
            stock = yf.Ticker(ticker)

            quarterly_financials = stock.quarterly_financials
            
            if quarterly_financials.empty:
                return {"error": "Quarterly data not available"}
            
            eps_data = []
            for i, quarter in enumerate(quarterly_financials.columns[:4]):
                if 'Net Income' in quarterly_financials.index:
                    net_income = quarterly_financials.loc['Net Income', quarter]
                    eps_data.append({
                        "quarter": quarter.strftime('%Y-Q%q') if hasattr(quarter, 'strftime') else str(quarter),
                        "net_income": net_income,
                        "quarter_index": i
                    })
            
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
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            debt_to_equity = info.get('debtToEquity', 0)
            
            sector = info.get('sector', '')
            

            interest_sensitive_sectors = [
                'Real Estate', 'Utilities', 'Financial Services', 
                'Consumer Discretionary', 'Technology'
            ]
            
            is_interest_sensitive = sector in interest_sensitive_sectors
            
            interest_impact_score = 5  
            
            if debt_to_equity > 50:
                interest_impact_score += 2  
            if is_interest_sensitive:
                interest_impact_score += 2  
            if info.get('beta', 1) > 1.2:
                interest_impact_score += 1  
                
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
        try:
            stock = yf.Ticker(ticker)
            
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
        print(f"=== {ticker} 펀더멘털 분석 시작 ===")
        
        financial_ratios = self.calculate_financial_ratios(ticker)
        earnings_analysis = self.analyze_earnings_surprise(ticker)
        interest_analysis = self.analyze_interest_rate_impact(ticker)
        earnings_calendar = self.get_earnings_calendar(ticker)
        
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
        ticker = analysis_data.get('ticker', 'N/A')
        
        ratios = analysis_data.get('financial_ratios', {})
        earnings = analysis_data.get('earnings_analysis', {})
        interest = analysis_data.get('interest_rate_analysis', {})
        calendar = analysis_data.get('earnings_calendar', {})
        
        data_source = ratios.get('source', 'unknown')
        is_naver_data = data_source == 'naver_finance'
        
        report = f"""
=== {ticker} 종합 펀더멘털 분석 보고서 ===
데이터 출처: {'네이버 금융' if is_naver_data else 'Yahoo Finance'}

## 1. 핵심 재무지표"""
        
        if is_naver_data:
            metrics = ratios.get('financial_metrics', {})
            report += f"""
- 매출액: {self.format_currency(metrics.get('revenue', 0))}
- 영업이익: {self.format_currency(metrics.get('operating_income', 0))}
- 당기순이익: {self.format_currency(metrics.get('net_income', 0))}
- 시가총액: {self.format_currency(metrics.get('market_cap', 0))}

## 2. 수익성 지표
- ROA (총자산이익률): {metrics.get('roa', 'N/A')}%
- ROE (자기자본이익률): {metrics.get('roe', 'N/A')}%
- 부채비율: {metrics.get('debt_ratio', 'N/A')}%
- 유동비율: {metrics.get('current_ratio', 'N/A')}%

## 3. 밸류에이션
- PER (주가수익비율): {metrics.get('pe_ratio', 'N/A')}
- PBR (주가순자산비율): {metrics.get('pb_ratio', 'N/A')}"""
            
            # 업종 비교 데이터
            industry_comp = ratios.get('industry_comparison', {})
            if industry_comp:
                report += f"""

## 4. 동일업종 비교"""
                for metric, data in industry_comp.items():
                    if isinstance(data, dict):
                        report += f"""
- {metric}: 회사 {data.get('company', 'N/A')} vs 업종평균 {data.get('industry_avg', 'N/A')}"""
        else:
            # yfinance 데이터 포맷 (기존 방식)
            report += f"""
- 매출액: {self.format_currency(ratios.get('revenue', 0))}
- 순이익: {self.format_currency(ratios.get('net_income', 0))}
- 총자산: {self.format_currency(ratios.get('total_assets', 0))}
- 자기자본: {self.format_currency(ratios.get('shareholders_equity', 0))}

## 2. 수익성 지표
- ROA (총자산이익률): {ratios.get('roa', 'N/A')}%
- ROE (자기자본이익률): {ratios.get('roe', 'N/A')}%
- Gross Margin (매출총이익률): {ratios.get('gross_margin', 'N/A')}%
- Asset Growth (자산성장률): {ratios.get('asset_growth', 'N/A')}%

## 3. 밸류에이션
- 시가총액: {self.format_currency(ratios.get('market_cap', 0))}
- PER (주가수익비율): {ratios.get('pe_ratio', 'N/A')}
- PBR (주가순자산비율): {ratios.get('pb_ratio', 'N/A')}"""
        
        # 공통 섹션들
        report += f"""

## {'5' if is_naver_data and ratios.get('industry_comparison') else '4'}. 실적 모멘텀 분석
- Fundamental Momentum: {earnings.get('momentum_description', 'N/A')}
- 최근 분기 실적 추이: {"개선" if earnings.get('fundamental_momentum', False) else "둔화"}

## {'6' if is_naver_data and ratios.get('industry_comparison') else '5'}. 금리 민감도 분석
- 부채비율: {interest.get('debt_to_equity', 'N/A')}%
- 섹터: {interest.get('sector', 'N/A')}
- {interest.get('analysis', 'N/A')}

## {'7' if is_naver_data and ratios.get('industry_comparison') else '6'}. 실적발표 일정
- 다음 실적발표일: {calendar.get('next_earnings_date', 'N/A')}

## {'8' if is_naver_data and ratios.get('industry_comparison') else '7'}. 종합 평가
"""
        
        # 종합 점수 계산 (네이버 데이터 고려)
        score = 0
        factors = []
        
        if is_naver_data:
            metrics = ratios.get('financial_metrics', {})
            roe_val = metrics.get('roe', 0)
        else:
            roe_val = ratios.get('roe', 0)
        
        if roe_val > 15:
            score += 2
            factors.append("높은 ROE")
        elif roe_val > 10:
            score += 1
            factors.append("양호한 ROE")
            
        if earnings.get('fundamental_momentum', False):
            score += 2
            factors.append("실적 개선 추세")
            
        if not is_naver_data and ratios.get('asset_growth', 0) > 5:
            score += 1
            factors.append("자산 성장")
            
        if interest.get('interest_impact_score', 5) < 6:
            score += 1
            factors.append("낮은 금리 민감도")
        
        # 네이버 데이터 추가 점수
        if is_naver_data:
            metrics = ratios.get('financial_metrics', {})
            if metrics.get('current_ratio', 0) > 150:  # 유동비율 150% 이상
                score += 1
                factors.append("양호한 유동성")
            if metrics.get('debt_ratio', 100) < 30:  # 부채비율 30% 미만
                score += 1
                factors.append("낮은 부채비율")
        
        if score >= 5:
            grade = "매우 우수"
        elif score >= 3:
            grade = "우수" 
        elif score >= 2:
            grade = "보통"
        else:
            grade = "주의 필요"
            
        max_score = 8 if is_naver_data else 6
        report += f"""
펀더멘털 종합 점수: {score}/{max_score} ({grade})
주요 강점: {', '.join(factors) if factors else '특별한 강점 없음'}

※ 이 분석은 {'네이버 금융 및 공개된' if is_naver_data else '공개된'} 재무 데이터를 바탕으로 한 것이며, 투자 결정 시 추가적인 분석이 필요합니다.
        """
        
        return report
    
    def format_currency(self, value):
        """통화 포맷팅 (억원, 조원 단위)"""
        if not value or value == 0:
            return "N/A"
        
        if value >= 1000000000000:  # 1조원 이상
            return f"{value/1000000000000:.1f}조원"
        elif value >= 100000000:  # 1억원 이상
            return f"{value/100000000:.1f}억원"
        elif value >= 1000000:  # 100만원 이상
            return f"{value/1000000:.1f}백만원"
        else:
            return f"{value:,.0f}원"


# 사용 예시 함수
def analyze_fundamental(ticker):
    analyzer = FundamentalAnalyzer()
    analysis_result = analyzer.comprehensive_fundamental_analysis(ticker)
    report = analyzer.format_fundamental_report(analysis_result)
    return report


if __name__ == "__main__":

    test_ticker = "005930.KS"  
    result = analyze_fundamental(test_ticker)
    print(result) 