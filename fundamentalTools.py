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
        를 불러오는 함수 (개선된 버전)
        """
        try:
            URL = f"https://finance.naver.com/item/main.nhn?code={code}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(URL, headers=headers)
            
            if r.status_code != 200:
                return None, None, None, {"error": f"HTTP {r.status_code}"}
            
            tables = pd.read_html(r.text)
            print(f"📊 총 {len(tables)}개 테이블 발견")
            
            annual_data, quarter_data, industry_df = None, None, None
            
            # 재무제표 데이터 추출 (보통 4번째 테이블)
            try:
                for table_idx in [4, 5, 3]:  # 여러 인덱스 시도
                    try:
                        finance_df = tables[table_idx]
                        
                        # 재무제표인지 확인
                        if '최근 연간 실적' in str(finance_df.columns) or '최근 분기 실적' in str(finance_df.columns):
                            finance_df.set_index(finance_df.columns[0], inplace=True)
                            finance_df.index.rename('주요재무정보', inplace=True)
                            
                            # Multi-level 컬럼 처리
                            if finance_df.columns.nlevels > 1:
                                finance_df.columns = finance_df.columns.droplevel(-1)
                            
                            # 연간 실적 추출
                            if '최근 연간 실적' in finance_df.columns:
                                annual_data = finance_df.xs('최근 연간 실적', axis=1)
                                print("✅ 연간 실적 데이터 추출 성공")
                            
                            # 분기 실적 추출
                            if '최근 분기 실적' in finance_df.columns:
                                quarter_data = finance_df.xs('최근 분기 실적', axis=1)
                                print("✅ 분기 실적 데이터 추출 성공")
                            
                            break
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                print(f"재무제표 데이터를 불러오는 중 오류 발생: {e}")
            
            # 동일업종 비교 데이터 추출 (보통 5번째 또는 6번째 테이블)
            try:
                for table_idx in [5, 6, 7]:
                    try:
                        test_df = tables[table_idx]
                        
                        # 업종 비교 테이블 확인 (종목명이 있고 여러 회사 비교)
                        if ('종목명' in test_df.columns or 
                            len(test_df.columns) > 3 and 
                            any('*' in str(col) for col in test_df.columns)):  # 종목코드 패턴
                            
                            industry_df = test_df.copy()
                            industry_df.set_index(industry_df.columns[0], inplace=True)
                            print("✅ 동일업종 비교 데이터 추출 성공")
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
        """네이버 금융 데이터를 활용한 재무비율 분석 (개선된 파싱)"""
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
            
            print(f"📊 파싱 시작 - 총 {len(annual_data.index)}개 지표 확인")
            
            # 매출액 추출
            revenue_keys = ['매출액', '수익(매출액)', '매출']
            for key in revenue_keys:
                if key in annual_data.index:
                    financial_metrics['revenue'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    print(f"✅ 매출액 추출: {self.format_currency(financial_metrics['revenue'])}")
                    break
            
            # 영업이익 추출
            operating_income_keys = ['영업이익', '영업손익']
            for key in operating_income_keys:
                if key in annual_data.index:
                    financial_metrics['operating_income'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    print(f"✅ 영업이익 추출: {self.format_currency(financial_metrics['operating_income'])}")
                    break
            
            # 순이익 추출
            net_income_keys = ['당기순이익', '순이익', '당기순손익']
            for key in net_income_keys:
                if key in annual_data.index:
                    financial_metrics['net_income'] = self.parse_financial_value(annual_data.loc[key].iloc[0])
                    print(f"✅ 순이익 추출: {self.format_currency(financial_metrics['net_income'])}")
                    break
            
            # ROE 추출 (개선된 필드명 매칭)
            roe_keys = ['ROE(지배주주)', 'ROE', 'ROE(%)', '자기자본이익률']
            for key in roe_keys:
                if key in annual_data.index:
                    roe_value = annual_data.loc[key].iloc[0]
                    if pd.notna(roe_value) and str(roe_value).strip() != '':
                        financial_metrics['roe'] = self.parse_percentage(roe_value)
                        print(f"✅ ROE 추출: {financial_metrics['roe']}% (from {key})")
                        break
            
            # ROA 계산 (순이익과 총자산이 있으면)
            if 'net_income' in financial_metrics:
                # 간접 계산 시도
                if '총자산' in annual_data.index:
                    total_assets = self.parse_financial_value(annual_data.loc['총자산'].iloc[0])
                    if total_assets > 0:
                        financial_metrics['roa'] = round((financial_metrics['net_income'] / total_assets) * 100, 2)
                        print(f"✅ ROA 계산: {financial_metrics['roa']}%")
            
            # PER 추출 (개선된 필드명 매칭)
            per_keys = ['PER(배)', 'PER', 'PER(%)', '주가수익비율']
            for key in per_keys:
                if key in annual_data.index:
                    per_value = annual_data.loc[key].iloc[0]
                    if pd.notna(per_value) and str(per_value).strip() != '':
                        # PER은 배수이므로 그대로 사용
                        financial_metrics['pe_ratio'] = float(str(per_value).replace('배', '').replace('%', '').strip())
                        print(f"✅ PER 추출: {financial_metrics['pe_ratio']}배 (from {key})")
                        break
            
            # PBR 추출 (개선된 필드명 매칭)
            pbr_keys = ['PBR(배)', 'PBR', 'PBR(%)', '주가순자산비율']
            for key in pbr_keys:
                if key in annual_data.index:
                    pbr_value = annual_data.loc[key].iloc[0]
                    if pd.notna(pbr_value) and str(pbr_value).strip() != '':
                        # PBR은 배수이므로 그대로 사용
                        financial_metrics['pb_ratio'] = float(str(pbr_value).replace('배', '').replace('%', '').strip())
                        print(f"✅ PBR 추출: {financial_metrics['pb_ratio']}배 (from {key})")
                        break
            
            # 부채비율 추출
            debt_keys = ['부채비율', '부채비율(%)']
            for key in debt_keys:
                if key in annual_data.index:
                    debt_value = annual_data.loc[key].iloc[0]
                    if pd.notna(debt_value) and str(debt_value).strip() != '':
                        financial_metrics['debt_ratio'] = self.parse_percentage(debt_value)
                        print(f"✅ 부채비율 추출: {financial_metrics['debt_ratio']}%")
                        break
            
            # 유동비율/당좌비율 추출
            liquidity_keys = ['유동비율', '당좌비율', '유동성비율']
            for key in liquidity_keys:
                if key in annual_data.index:
                    liquidity_value = annual_data.loc[key].iloc[0]
                    if pd.notna(liquidity_value) and str(liquidity_value).strip() != '':
                        financial_metrics['current_ratio'] = self.parse_percentage(liquidity_value)
                        print(f"✅ 유동비율 추출: {financial_metrics['current_ratio']}%")
                        break
            
            # yfinance에서 시가총액 보완 시도
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if 'marketCap' in info and info['marketCap']:
                    financial_metrics['market_cap'] = info['marketCap']
                    print(f"✅ 시가총액 보완 (yfinance): {self.format_currency(financial_metrics['market_cap'])}")
            except:
                pass
            
            # 업종 비교 데이터 처리
            industry_comparison = {}
            if industry_df is not None:
                try:
                    print(f"📊 업종 비교 데이터 처리: {industry_df.shape}")
                    # 업종 비교에서 추가 메트릭 추출
                    if 'ROE(%)' in industry_df.index and len(industry_df.columns) > 0:
                        company_roe = industry_df.loc['ROE(%)', industry_df.columns[0]]
                        industry_comparison['ROE'] = {
                            'company': str(company_roe),
                            'industry_avg': 'N/A'  # 업종 평균 계산 필요 시 추가
                        }
                    
                    if 'PER(%)' in industry_df.index and len(industry_df.columns) > 0:
                        company_per = industry_df.loc['PER(%)', industry_df.columns[0]]
                        industry_comparison['PER'] = {
                            'company': str(company_per),
                            'industry_avg': 'N/A'
                        }
                        
                except Exception as e:
                    print(f"업종 비교 데이터 처리 오류: {e}")
            
            print(f"🎯 최종 추출된 메트릭 수: {len(financial_metrics)}개")
            for key, value in financial_metrics.items():
                print(f"  - {key}: {value}")
            
            return {
                "source": "naver_finance",
                "financial_metrics": financial_metrics,
                "industry_comparison": industry_comparison,
                "quarter_data_available": quarter_data is not None,
                "annual_data_available": annual_data is not None,
                "data_richness": len(financial_metrics)
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
        """Enhanced multi-source financial ratios calculation with comprehensive fallbacks"""
        print(f"🔄 Starting multi-source fundamental analysis for {ticker}")
        
        # Initialize result structure
        result = {
            "source": "multi-source",
            "financial_metrics": {},
            "data_sources_used": [],
            "missing_metrics": [],
            "data_quality_score": 0
        }
        
        # Define critical metrics we need
        critical_metrics = [
            'revenue', 'net_income', 'market_cap', 'pe_ratio', 'pb_ratio', 
            'roe', 'roa', 'debt_ratio', 'current_ratio'
        ]
        
        # Step 1: Try Naver Finance for Korean stocks
        is_korean_stock = self.extract_korean_code(ticker) is not None
        naver_data = None
        
        if is_korean_stock:
            print(f"📊 Attempting Naver Finance data for Korean stock: {ticker}")
            naver_result = self.analyze_naver_financial_ratios(ticker)
            
            if "error" not in naver_result:
                naver_data = naver_result
                result["data_sources_used"].append("naver_finance")
                
                # Extract metrics from Naver data
                if "financial_metrics" in naver_data:
                    for metric, value in naver_data["financial_metrics"].items():
                        if value is not None and value != 0 and value != "N/A":
                            result["financial_metrics"][metric] = value
                            
                print(f"✅ Naver Finance: Retrieved {len(result['financial_metrics'])} metrics")
            else:
                print(f"❌ Naver Finance failed: {naver_result.get('error', 'Unknown error')}")
        
        # Step 2: Try yfinance for missing metrics or as primary source for non-Korean stocks
        print(f"📈 Attempting yfinance data for {ticker}")
        yfinance_result = self.calculate_financial_ratios_yfinance(ticker)
        
        if "error" not in yfinance_result:
            result["data_sources_used"].append("yfinance")
            
            # Fill missing metrics from yfinance
            yf_metrics_added = 0
            for metric, value in yfinance_result.items():
                if metric not in ['source'] and (metric not in result["financial_metrics"] or 
                                                result["financial_metrics"].get(metric) in [None, 0, "N/A"]):
                    if value is not None and value != 0 and value != "N/A":
                        result["financial_metrics"][metric] = value
                        yf_metrics_added += 1
                        
            print(f"✅ yfinance: Added {yf_metrics_added} additional metrics")
        else:
            print(f"❌ yfinance failed: {yfinance_result.get('error', 'Unknown error')}")
        
        # Step 3: Try additional fallback sources for critical missing metrics
        missing_critical = [metric for metric in critical_metrics 
                          if metric not in result["financial_metrics"] or 
                          result["financial_metrics"][metric] in [None, 0, "N/A"]]
        
        if missing_critical:
            print(f"⚠️ Missing critical metrics: {missing_critical}")
            
            # Try alternative yfinance info extraction
            fallback_data = self.get_yfinance_alternative_metrics(ticker, missing_critical)
            if fallback_data:
                result["data_sources_used"].append("yfinance_alternative")
                for metric, value in fallback_data.items():
                    if value is not None and value != 0:
                        result["financial_metrics"][metric] = value
                        missing_critical.remove(metric) if metric in missing_critical else None
                        
                print(f"✅ Alternative yfinance: Filled {len(fallback_data)} missing metrics")
        
        # Step 4: DART API fallback for Korean stocks (if still missing data)
        if is_korean_stock and missing_critical and self.dart_api_key:
            print(f"🏢 Attempting DART API for remaining metrics: {missing_critical}")
            dart_data = self.get_dart_fallback_metrics(ticker, missing_critical)
            if dart_data:
                result["data_sources_used"].append("dart_api")
                for metric, value in dart_data.items():
                    if value is not None and value != 0:
                        result["financial_metrics"][metric] = value
                        missing_critical.remove(metric) if metric in missing_critical else None
                        
                print(f"✅ DART API: Filled {len(dart_data)} missing metrics")
        
        # Step 5: Calculate data quality score and final validation
        result["missing_metrics"] = missing_critical
        filled_metrics = len([m for m in critical_metrics if m in result["financial_metrics"] 
                            and result["financial_metrics"][m] not in [None, 0, "N/A"]])
        result["data_quality_score"] = (filled_metrics / len(critical_metrics)) * 100
        
        # Add metadata
        result["analysis_timestamp"] = datetime.now().isoformat()
        result["total_metrics_retrieved"] = len(result["financial_metrics"])
        
        print(f"📈 Analysis complete: {filled_metrics}/{len(critical_metrics)} critical metrics filled")
        print(f"📊 Data quality score: {result['data_quality_score']:.1f}%")
        print(f"🔗 Sources used: {', '.join(result['data_sources_used'])}")
        
        # Return enhanced result or error if no data could be retrieved
        if not result["financial_metrics"] or result["data_quality_score"] < 20:
            return {
                "error": f"Insufficient fundamental data retrieved. Quality score: {result['data_quality_score']:.1f}%",
                "attempted_sources": result["data_sources_used"],
                "missing_metrics": missing_critical
            }
        
        return result

    def get_yfinance_alternative_metrics(self, ticker, missing_metrics):
        """Alternative yfinance data extraction for missing metrics"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            alternative_data = {}
            
            for metric in missing_metrics:
                if metric == 'revenue' and 'totalRevenue' in info:
                    alternative_data['revenue'] = info['totalRevenue']
                elif metric == 'net_income' and 'netIncomeToCommon' in info:
                    alternative_data['net_income'] = info['netIncomeToCommon']
                elif metric == 'market_cap' and 'marketCap' in info:
                    alternative_data['market_cap'] = info['marketCap']
                elif metric == 'pe_ratio':
                    # Try multiple PE ratio fields
                    pe_fields = ['trailingPE', 'forwardPE', 'priceToEarningsTrailing12Months']
                    for field in pe_fields:
                        if field in info and info[field] is not None:
                            alternative_data['pe_ratio'] = info[field]
                            break
                elif metric == 'pb_ratio' and 'priceToBook' in info:
                    alternative_data['pb_ratio'] = info['priceToBook']
                elif metric == 'roe' and 'returnOnEquity' in info:
                    alternative_data['roe'] = info['returnOnEquity'] * 100  # Convert to percentage
                elif metric == 'roa' and 'returnOnAssets' in info:
                    alternative_data['roa'] = info['returnOnAssets'] * 100  # Convert to percentage
                elif metric == 'debt_ratio' and 'debtToEquity' in info:
                    alternative_data['debt_ratio'] = info['debtToEquity']
                elif metric == 'current_ratio' and 'currentRatio' in info:
                    alternative_data['current_ratio'] = info['currentRatio'] * 100  # Convert to percentage
            
            return alternative_data
            
        except Exception as e:
            print(f"❌ Alternative yfinance extraction failed: {e}")
            return {}

    def get_dart_fallback_metrics(self, ticker, missing_metrics):
        """DART API fallback for Korean stocks missing metrics"""
        try:
            if not self.dart_api_key:
                return {}
            
            code = self.extract_korean_code(ticker)
            if not code:
                return {}
            
            # Get corporation code first
            corp_code = self.get_corp_code_from_dart(code)
            if not corp_code:
                return {}
            
            # Get financial statements
            financial_data = self.get_dart_financial_statements(corp_code)
            if not financial_data:
                return {}
            
            # Extract missing metrics from DART data
            dart_metrics = {}
            
            # This is a simplified implementation - in production, you'd need to parse
            # the complex DART financial statement structure
            if 'revenue' in missing_metrics and 'sales' in financial_data:
                dart_metrics['revenue'] = financial_data['sales']
            
            if 'net_income' in missing_metrics and 'net_income' in financial_data:
                dart_metrics['net_income'] = financial_data['net_income']
            
            # Add more DART metric mappings as needed...
            
            return dart_metrics
            
        except Exception as e:
            print(f"❌ DART API fallback failed: {e}")
            return {}

    def get_corp_code_from_dart(self, stock_code):
        """Get corporation code from DART API using stock code"""
        try:
            url = "https://opendart.fss.or.kr/api/corpCode.xml"
            params = {'crtfc_key': self.dart_api_key}
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                # Parse XML response to find corp_code for given stock_code
                # This is simplified - actual implementation would parse XML
                # and map stock codes to corporation codes
                return None  # Placeholder
            return None
            
        except Exception as e:
            print(f"❌ DART corp code lookup failed: {e}")
            return None

    def get_dart_financial_statements(self, corp_code):
        """Get financial statements from DART API"""
        try:
            url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
            params = {
                'crtfc_key': self.dart_api_key,
                'corp_code': corp_code,
                'bsns_year': datetime.now().year - 1,  # Previous year
                'reprt_code': '11011'  # Annual report
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get('list', [])
            return []
            
        except Exception as e:
            print(f"❌ DART financial statements failed: {e}")
            return []
    
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
        
        # Handle both old and new data structures
        if ratios.get('source') == 'multi-source':
            # New multi-source structure
            metrics = ratios.get('financial_metrics', {})
            data_sources = ratios.get('data_sources_used', [])
            data_quality = ratios.get('data_quality_score', 0)
            missing_metrics = ratios.get('missing_metrics', []) 
            
            source_display = ' + '.join([
                'Naver' if 'naver_finance' in data_sources else '',
                'Yahoo Finance' if 'yfinance' in data_sources else '',
                'DART' if 'dart_api' in data_sources else '',
                'Alternative' if 'yfinance_alternative' in data_sources else ''
            ]).strip(' + ')
            
        else:
            # Legacy single-source structure
            if ratios.get('source') == 'naver_finance':
                metrics = ratios.get('financial_metrics', {})
                source_display = 'Naver Finance'
                data_quality = 85  # Assume good quality for legacy
            else:
                metrics = ratios  # Direct metrics in old yfinance structure
                source_display = 'Yahoo Finance'
                data_quality = 75  # Assume decent quality for legacy

        report = f"""
=== {ticker} 종합 펀더멘털 분석 보고서 ===
데이터 출처: {source_display}
데이터 품질: {data_quality:.1f}% ({'매우 우수' if data_quality >= 90 else '우수' if data_quality >= 75 else '보통' if data_quality >= 50 else '주의 필요'})

## 1. 핵심 재무지표"""
        
        # Format financial metrics consistently
        revenue = metrics.get('revenue', 0)
        net_income = metrics.get('net_income', 0)
        total_assets = metrics.get('total_assets', 0)
        shareholders_equity = metrics.get('shareholders_equity', 0)
        market_cap = metrics.get('market_cap', 0)
        
        report += f"""
- 매출액: {self.format_currency(revenue)}
- 순이익: {self.format_currency(net_income)}
- 총자산: {self.format_currency(total_assets)}
- 자기자본: {self.format_currency(shareholders_equity)}"""

        report += f"""

## 2. 수익성 지표
- ROA (총자산이익률): {metrics.get('roa', 'N/A')}%
- ROE (자기자본이익률): {metrics.get('roe', 'N/A')}%
- Gross Margin (매출총이익률): {metrics.get('gross_margin', 'N/A')}%
- Asset Growth (자산성장률): {metrics.get('asset_growth', 'N/A')}%

## 3. 밸류에이션
- 시가총액: {self.format_currency(market_cap)}
- PER (주가수익비율): {metrics.get('pe_ratio', 'N/A')}
- PBR (주가순자산비율): {metrics.get('pb_ratio', 'N/A')}"""

        # Add debt and liquidity ratios for enhanced data
        debt_ratio = metrics.get('debt_ratio', 0)
        current_ratio = metrics.get('current_ratio', 0)
        
        if debt_ratio or current_ratio:
            report += f"""

## 4. 재무 건전성
- 부채비율: {debt_ratio}%
- 유동비율: {current_ratio}%"""
            section_num = 5
        else:
            section_num = 4

        # Earnings momentum analysis
        report += f"""

## {section_num}. 실적 모멘텀 분석
- Fundamental Momentum: {earnings.get('momentum_description', 'N/A')}
- 최근 분기 실적 추이: {"개선" if earnings.get('fundamental_momentum', False) else "둔화"}

## {section_num + 1}. 금리 민감도 분석
- 부채비율: {interest.get('debt_to_equity', 'N/A')}%
- 섹터: {interest.get('sector', 'N/A')}
- {interest.get('analysis', 'N/A')}

## {section_num + 2}. 실적발표 일정
- 다음 실적발표일: {calendar.get('next_earnings_date', 'N/A')}"""

        # Data quality and missing metrics information
        if ratios.get('source') == 'multi-source':
            missing_count = len(missing_metrics) if missing_metrics else 0
            if missing_count > 0:
                report += f"""

## {section_num + 3}. 데이터 품질 정보
- 수집된 핵심 지표: {9 - missing_count}/9개
- 부족한 지표: {', '.join(missing_metrics) if missing_metrics else '없음'}
- 사용된 데이터 소스: {len(data_sources)}개"""

        # Comprehensive scoring
        report += f"""

## {section_num + 4 if ratios.get('source') == 'multi-source' and missing_metrics else section_num + 3}. 종합 평가
"""
        
        # Enhanced scoring with data quality consideration
        score = 0
        factors = []
        
        # ROE scoring
        roe_val = metrics.get('roe', 0) if metrics.get('roe') != 'N/A' else 0
        if roe_val > 15:
            score += 2
            factors.append("높은 ROE")
        elif roe_val > 10:
            score += 1
            factors.append("양호한 ROE")

        # Earnings momentum
        if earnings.get('fundamental_momentum', False):
            score += 2
            factors.append("실적 개선 추세")
            
        # Asset growth
        asset_growth = metrics.get('asset_growth', 0) if metrics.get('asset_growth') != 'N/A' else 0
        if asset_growth > 5:
            score += 1
            factors.append("자산 성장")
        
        # Interest rate sensitivity
        if interest.get('interest_impact_score', 5) < 6:
            score += 1
            factors.append("낮은 금리 민감도")
        
        # Liquidity and debt ratios (if available)
        if current_ratio > 150:
            score += 1
            factors.append("양호한 유동성")
        if debt_ratio < 30 and debt_ratio > 0:
            score += 1
            factors.append("낮은 부채비율")
        
        # Data quality bonus
        if data_quality >= 80:
            score += 1
            factors.append("높은 데이터 품질")

        max_score = 8
        if score >= 6:
            grade = "매우 우수"
        elif score >= 4:
            grade = "우수" 
        elif score >= 2:
            grade = "보통"
        else:
            grade = "주의 필요"
            
        report += f"""
펀더멘털 종합 점수: {score}/{max_score} ({grade})
주요 강점: {', '.join(factors) if factors else '특별한 강점 없음'}

※ 이 분석은 {source_display} 등 다중 데이터 소스를 바탕으로 한 것이며, 투자 결정 시 추가적인 분석이 필요합니다.
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