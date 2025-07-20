import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import re
from dotenv import load_dotenv
import os
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import yfinance as yf
import feedparser
from urllib.parse import quote
import time

load_dotenv()

class NewsAnalyzer:
    def __init__(self):
        # FinBERT 모델 로드 (금융 특화 감정 분석)
        try:
            self.finbert_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.finbert_model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            self.sentiment_pipeline = pipeline("sentiment-analysis", 
                                             model=self.finbert_model, 
                                             tokenizer=self.finbert_tokenizer)
            print("FinBERT 모델 로드 완료")
        except Exception as e:
            print(f"FinBERT 모델 로드 실패: {e}")
            self.sentiment_pipeline = None
    
    def scrape_naver_news(self, ticker, company_name, days=7):
        """네이버 뉴스에서 기업 관련 뉴스 스크래핑"""
        try:
            news_data = []
            
            # 검색 키워드 설정
            search_terms = [company_name, ticker.replace('.KS', '')]
            
            for term in search_terms:
                encoded_term = quote(term)
                url = f"https://search.naver.com/search.naver?where=news&sm=tab_jum&query={encoded_term}"
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 뉴스 기사 추출
                news_items = soup.find_all('div', class_='news_area')
                
                for item in news_items[:10]:  # 상위 10개만
                    try:
                        title_elem = item.find('a', class_='news_tit')
                        if title_elem:
                            title = title_elem.get_text().strip()
                            link = title_elem.get('href')
                            
                            # 요약문 추출
                            summary_elem = item.find('div', class_='news_dsc')
                            summary = summary_elem.get_text().strip() if summary_elem else ""
                            
                            # 날짜 추출
                            date_elem = item.find('span', class_='info')
                            date_str = date_elem.get_text().strip() if date_elem else ""
                            
                            news_data.append({
                                'title': title,
                                'summary': summary,
                                'link': link,
                                'date': date_str,
                                'source': 'naver',
                                'search_term': term
                            })
                    except Exception as e:
                        continue
                
                time.sleep(1)  # 요청 간격 조절
            
            return news_data
            
        except Exception as e:
            print(f"네이버 뉴스 스크래핑 오류: {e}")
            return []
    
    def scrape_google_news(self, ticker, company_name, days=7):
        """구글 뉴스에서 기업 관련 뉴스 스크래핑"""
        try:
            news_data = []
            
            # RSS 피드를 통한 구글 뉴스 수집
            search_terms = [company_name, ticker.replace('.KS', '')]
            
            for term in search_terms:
                encoded_term = quote(term)
                rss_url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
                
                try:
                    feed = feedparser.parse(rss_url)
                    
                    for entry in feed.entries[:10]:  # 상위 10개만
                        # 날짜 파싱
                        pub_date = entry.published if hasattr(entry, 'published') else ""
                        
                        news_data.append({
                            'title': entry.title,
                            'summary': entry.summary if hasattr(entry, 'summary') else "",
                            'link': entry.link,
                            'date': pub_date,
                            'source': 'google_news',
                            'search_term': term
                        })
                except Exception as e:
                    print(f"RSS 피드 파싱 오류: {e}")
                    continue
                
                time.sleep(1)
            
            return news_data
            
        except Exception as e:
            print(f"구글 뉴스 스크래핑 오류: {e}")
            return []
    
    def scrape_financial_news(self, ticker):
        """금융 전문 사이트에서 뉴스 수집"""
        try:
            news_data = []
            
            # 여러 금융 뉴스 사이트 URL 패턴
            financial_sites = [
                f"https://finance.naver.com/item/news.nhn?code={ticker.replace('.KS', '')}",
                # 추가 금융 사이트들...
            ]
            
            for site_url in financial_sites:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(site_url, headers=headers)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # 네이버 금융 뉴스 파싱
                    if 'finance.naver.com' in site_url:
                        news_items = soup.find_all('tr')
                        
                        for item in news_items[:15]:
                            try:
                                link_elem = item.find('a')
                                if link_elem and 'title' in link_elem.attrs:
                                    title = link_elem.get('title')
                                    link = "https://finance.naver.com" + link_elem.get('href')
                                    
                                    # 날짜 정보 추출
                                    date_elem = item.find('td', class_='date')
                                    date_str = date_elem.get_text().strip() if date_elem else ""
                                    
                                    news_data.append({
                                        'title': title,
                                        'summary': "",
                                        'link': link,
                                        'date': date_str,
                                        'source': 'naver_finance',
                                        'search_term': ticker
                                    })
                            except Exception as e:
                                continue
                    
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"금융 사이트 스크래핑 오류: {e}")
                    continue
            
            return news_data
            
        except Exception as e:
            print(f"금융 뉴스 수집 오류: {e}")
            return []
    
    def analyze_sentiment_with_finbert(self, text):
        """FinBERT를 사용한 금융 감정 분석"""
        try:
            if not self.sentiment_pipeline:
                return {"label": "NEUTRAL", "score": 0.5}
            
            # 텍스트 길이 제한 (BERT 모델의 토큰 제한)
            if len(text) > 512:
                text = text[:512]
            
            result = self.sentiment_pipeline(text)[0]
            
            # FinBERT 결과를 표준화
            label_mapping = {
                'positive': 'POSITIVE',
                'negative': 'NEGATIVE', 
                'neutral': 'NEUTRAL'
            }
            
            standard_label = label_mapping.get(result['label'].lower(), 'NEUTRAL')
            
            return {
                "label": standard_label,
                "score": result['score']
            }
            
        except Exception as e:
            print(f"감정 분석 오류: {e}")
            return {"label": "NEUTRAL", "score": 0.5}
    
    def process_news_data(self, news_data):
        """뉴스 데이터 전처리 및 감정 분석"""
        try:
            processed_news = []
            
            for news in news_data:
                # 텍스트 정제
                title = news.get('title', '').strip()
                summary = news.get('summary', '').strip()
                
                # 제목과 요약을 합친 텍스트로 감정 분석
                full_text = f"{title}. {summary}".strip()
                
                if len(full_text) > 10:  # 최소 길이 확인
                    sentiment = self.analyze_sentiment_with_finbert(full_text)
                    
                    processed_news.append({
                        'title': title,
                        'summary': summary,
                        'link': news.get('link', ''),
                        'date': news.get('date', ''),
                        'source': news.get('source', ''),
                        'sentiment_label': sentiment['label'],
                        'sentiment_score': sentiment['score'],
                        'full_text': full_text
                    })
            
            return processed_news
            
        except Exception as e:
            print(f"뉴스 데이터 처리 오류: {e}")
            return []
    
    def calculate_overall_sentiment(self, processed_news):
        """전체 뉴스의 종합 감정 점수 계산"""
        try:
            if not processed_news:
                return {
                    "overall_sentiment": "NEUTRAL",
                    "sentiment_score": 0.5,
                    "positive_count": 0,
                    "negative_count": 0,
                    "neutral_count": 0,
                    "total_news": 0
                }
            
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            sentiment_scores = []
            
            for news in processed_news:
                label = news['sentiment_label']
                score = news['sentiment_score']
                
                if label == 'POSITIVE':
                    positive_count += 1
                    sentiment_scores.append(score)
                elif label == 'NEGATIVE':
                    negative_count += 1
                    sentiment_scores.append(-score)  # 부정적 점수
                else:
                    neutral_count += 1
                    sentiment_scores.append(0)
            
            # 전체 감정 점수 계산
            avg_score = np.mean(sentiment_scores) if sentiment_scores else 0
            
            # 전체 감정 레이블 결정
            if avg_score > 0.1:
                overall_sentiment = "POSITIVE"
            elif avg_score < -0.1:
                overall_sentiment = "NEGATIVE"
            else:
                overall_sentiment = "NEUTRAL"
            
            return {
                "overall_sentiment": overall_sentiment,
                "sentiment_score": avg_score,
                "positive_count": positive_count,
                "negative_count": negative_count,
                "neutral_count": neutral_count,
                "total_news": len(processed_news)
            }
            
        except Exception as e:
            print(f"종합 감정 계산 오류: {e}")
            return {
                "overall_sentiment": "NEUTRAL",
                "sentiment_score": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "total_news": 0
            }
    
    def comprehensive_news_analysis(self, ticker, company_name=None):
        """종합적인 뉴스 분석 수행"""
        print(f"=== {ticker} 실시간 뉴스 분석 시작 ===")
        
        # 회사명이 없으면 yfinance에서 가져오기
        if not company_name:
            try:
                stock = yf.Ticker(ticker)
                company_name = stock.info.get('longName', ticker)
            except:
                company_name = ticker
        
        print(f"분석 대상: {company_name} ({ticker})")
        
        all_news = []
        
        # 1. 네이버 뉴스 수집
        print("네이버 뉴스 수집 중...")
        naver_news = self.scrape_naver_news(ticker, company_name)
        all_news.extend(naver_news)
        
        # 2. 구글 뉴스 수집  
        print("구글 뉴스 수집 중...")
        google_news = self.scrape_google_news(ticker, company_name)
        all_news.extend(google_news)
        
        # 3. 금융 전문 뉴스 수집
        print("금융 뉴스 수집 중...")
        financial_news = self.scrape_financial_news(ticker)
        all_news.extend(financial_news)
        
        print(f"총 {len(all_news)}개 뉴스 수집 완료")
        
        # 4. 뉴스 데이터 전처리 및 감정 분석
        print("뉴스 감정 분석 중...")
        processed_news = self.process_news_data(all_news)
        
        # 5. 종합 감정 분석
        sentiment_summary = self.calculate_overall_sentiment(processed_news)
        
        return {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "raw_news": all_news,
            "processed_news": processed_news,
            "sentiment_summary": sentiment_summary
        }
    
    def format_news_report(self, analysis_data):
        """뉴스 분석 결과를 텍스트 보고서로 포맷팅"""
        ticker = analysis_data.get('ticker', 'N/A')
        company_name = analysis_data.get('company_name', 'N/A')
        sentiment = analysis_data.get('sentiment_summary', {})
        processed_news = analysis_data.get('processed_news', [])
        
        report = f"""
=== {company_name} ({ticker}) 실시간 뉴스 분석 보고서 ===

## 뉴스 수집 현황
- 총 뉴스 개수: {sentiment.get('total_news', 0)}개
- 긍정 뉴스: {sentiment.get('positive_count', 0)}개
- 부정 뉴스: {sentiment.get('negative_count', 0)}개  
- 중립 뉴스: {sentiment.get('neutral_count', 0)}개

## 종합 감정 분석 (FinBERT 기반)
- 전체 감정: {sentiment.get('overall_sentiment', 'N/A')}
- 감정 점수: {sentiment.get('sentiment_score', 0):.3f}

## 주요 뉴스 헤드라인 (최근 순)
"""
        
        # 상위 10개 뉴스 헤드라인 추가
        for i, news in enumerate(processed_news[:10], 1):
            sentiment_emoji = {
                'POSITIVE': '📈',
                'NEGATIVE': '📉', 
                'NEUTRAL': '📊'
            }.get(news['sentiment_label'], '📊')
            
            report += f"{i}. {sentiment_emoji} {news['title'][:100]}...\n"
            if news['summary']:
                report += f"   💬 {news['summary'][:150]}...\n"
            report += f"   🔗 {news['source']} | {news['date']}\n\n"
        
        # 투자 관점에서의 해석
        report += f"""
## 투자 관점에서의 해석
"""
        
        if sentiment.get('overall_sentiment') == 'POSITIVE':
            report += "- 📈 전반적으로 긍정적인 뉴스가 우세하여 주가에 호재로 작용할 가능성이 높습니다.\n"
        elif sentiment.get('overall_sentiment') == 'NEGATIVE':
            report += "- 📉 부정적인 뉴스가 많아 주가에 악재로 작용할 가능성을 주의해야 합니다.\n"
        else:
            report += "- 📊 중립적인 뉴스 흐름으로 단기적 주가 영향은 제한적일 것으로 예상됩니다.\n"
        
        report += f"""
※ 이 분석은 실시간 뉴스 데이터와 FinBERT 모델을 기반으로 한 것이며, 
   투자 결정 시 다른 요소들과 함께 종합적으로 고려해야 합니다.
"""
        
        return report


# 사용 예시 함수
def analyze_news(ticker, company_name=None):
    """뉴스 분석 실행 함수"""
    analyzer = NewsAnalyzer()
    
    # 종합 뉴스 분석 수행
    analysis_result = analyzer.comprehensive_news_analysis(ticker, company_name)
    
    # 보고서 포맷팅
    report = analyzer.format_news_report(analysis_result)
    
    return report


if __name__ == "__main__":
    # 테스트
    test_ticker = "005930.KS"  # 삼성전자
    result = analyze_news(test_ticker)
    print(result) 