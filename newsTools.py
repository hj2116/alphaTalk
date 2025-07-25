import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pandas as pd
from newspaper import Article
from transformers import BertTokenizer, BertForSequenceClassification
import torch
from human_research import fetch_news, fetch_article_content, compute_sentiment_score, fetch_news_with_full_body_and_sentiment

class NewsAnalyzer:
    def __init__(self):
        try:
            self.finbert_tokenizer = BertTokenizer.from_pretrained("yiyanghkust/finbert-tone")
            self.finbert_model = BertForSequenceClassification.from_pretrained("yiyanghkust/finbert-tone")
            
            self.kobert_tokenizer = BertTokenizer.from_pretrained("snunlp/KR-FinBERT-SC")
            self.kobert_model = BertForSequenceClassification.from_pretrained("snunlp/KR-FinBERT-SC")
            self.kobert_model.eval()
            
            print("FinBERT + KoBERT 기반 뉴스 분석 시스템 초기화 완료")
        except Exception as e:
            print(f"뉴스 분석 모델 로드 오류: {e}")

            self.use_keyword_fallback = True
            self._init_keyword_system()
    
    def _init_keyword_system(self):
        """백업용 키워드 기반 시스템"""
        self.positive_keywords = [
            '상승', '급등', '강세', '호재', '성장', '증가', '개선', '확대', '투자', '수익',
            '긍정', '기대', '전망', '좋은', '우수', '성과', '실적', '이익', '수주', '계약'
        ]
        self.negative_keywords = [
            '하락', '급락', '약세', '악재', '감소', '축소', '우려', '부정', '위험', '손실',
            '걱정', '불안', '저조', '부진', '적자', '문제', '위기', '타격', '충격', '부담'
        ]
    
    def analyze_sentiment_with_finbert(self, text):
        """FinBERT를 사용한 영문 뉴스 감정 분석"""
        try:
            text = self.clean_text(text)
            tokens = self.finbert_tokenizer.encode(text, truncation=True, padding='max_length', max_length=512, return_tensors='pt')
            with torch.no_grad():
                output = self.finbert_model(tokens)
            logits = output.logits
            probs = torch.softmax(logits, dim=1).numpy()[0]
            sentiment_score = probs[2] - probs[0]  # positive - negative
            return round(float(sentiment_score), 4)
        except Exception as e:
            print(f"FinBERT 분석 오류: {e}")
            return 0.0
    
    def analyze_sentiment_with_clova(self, text):
        """Clova AI를 사용한 뉴스 감정 분석"""
        try:
            return response.json()["sentiment"]
        except Exception as e:
            print(f"Clova AI 분석 오류: {e}")


    def analyze_sentiment_with_kobert(self, text):
        """KoBERT를 사용한 한국어 뉴스 감정 분석"""
        try:
            inputs = self.kobert_tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
            with torch.no_grad():
                outputs = self.kobert_model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1).squeeze()
            score = -1 * probs[0].item() + 0 * probs[1].item() + 1 * probs[2].item()
            return round(score, 4)
        except Exception as e:
            print(f"KoBERT 분석 오류: {e}")
            return 0.0
    
    def analyze_sentiment_with_keywords(self, text):
        """백업용 키워드 기반 감정 분석"""
        if not text:
            return 0.0
        
        text = text.lower()
        positive_count = sum(1 for keyword in self.positive_keywords if keyword in text)
        negative_count = sum(1 for keyword in self.negative_keywords if keyword in text)
        
        total_keywords = positive_count + negative_count
        if total_keywords == 0:
            return 0.0
        
        sentiment_score = (positive_count - negative_count) / total_keywords
        return round(sentiment_score, 4)
    
    def clean_text(self, text):
        """텍스트 정제"""
        if not text:
            return ""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9.,!?\'\"%$()-]', ' ', text)
        text = text.strip()
        return text
    
    def is_korean_ticker(self, ticker):
        """한국 주식 코드 여부 확인 (6자리 숫자)"""
        return bool(re.match(r'^\d{6}$', ticker))
    
    def fetch_korean_news(self, ticker, max_pages=5):
        """한국 주식 뉴스 수집 및 KoBERT 감정 분석"""
        try:
            # human_research의 fetch_news 함수는 stock_code를 매개변수로 받음
            news_list = fetch_news(ticker, max_pages=max_pages)
            analyzed_news = []
            
            for news in news_list[:10]:  # 최대 10개
                try:
                    content = fetch_article_content(news["링크"])
                    if content and content != "None":
                        # 클로바 감정 분석 사용 (human_research의 compute_sentiment_score 함수 사용)
                        sentiment_score = compute_sentiment_score(content)
                        analyzed_news.append({
                            "title": news["제목"],
                            "content": content[:500],  # 요약
                            "date": news["날짜"],
                            "sentiment": sentiment_score
                        })
                except Exception as e:
                    print(f"한국 뉴스 처리 오류: {e}")
                    continue
            
            return analyzed_news
            
        except Exception as e:
            print(f"한국 뉴스 수집 오류: {e}")
            return []
    
    def fetch_english_news(self, ticker, days=3, max_results=20):
        """영문 뉴스 수집 및 FinBERT 감정 분석"""
        try:
            # NewsAPI를 사용한 영문 뉴스 수집
            url = "https://newsapi.org/v2/everything"
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            from_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            params = {
                "q": ticker,
                "from": from_date_str,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "apiKey": "5a9d9ae903084a349d94fdff1fb3da6a"
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            if data.get("status") != "ok":
                print(f"NewsAPI 오류: {data.get('message')}")
                return []
            
            articles = data.get("articles", [])
            analyzed_news = []
            
            for article in articles[:10]:  # 최대 10개
                try:
                    title = article.get("title", "")
                    description = article.get("description", "")
                    url_link = article.get("url", "")
                    published_at = article.get("publishedAt", "")
                    
                    # 본문 크롤링 시도
                    full_text = description  # 기본값
                    try:
                        news_article = Article(url_link)
                        news_article.download()
                        news_article.parse()
                        if news_article.text:
                            full_text = news_article.text[:1000]  # 최대 1000자
                    except:
                        pass
                    
                    sentiment_score = self.analyze_sentiment_with_finbert(full_text)
                    
                    analyzed_news.append({
                        "title": title,
                        "content": full_text[:500],  # 요약
                        "date": published_at[:10] if published_at else "",
                        "sentiment": sentiment_score
                    })
                    
                except Exception as e:
                    print(f"영문 뉴스 처리 오류: {e}")
                    continue
            
            return analyzed_news
            
        except Exception as e:
            print(f"영문 뉴스 수집 오류: {e}")
            return []
    
    def analyze_news(self, ticker):
        """종합 뉴스 분석"""
        try:
            print(f"=== {ticker} 실시간 뉴스 분석 시작 ===")
            
            if self.is_korean_ticker(ticker):
                print(f"분석 대상: 한국 주식 ({ticker})")
                korean_news = self.fetch_korean_news(ticker)
                english_news = []  # 한국 주식은 영문 뉴스 제외
                all_news = korean_news
            else:
                # 영문 티커의 경우 회사명 추출
                company_names = {
                    'AAPL': 'Apple Inc.',
                    'GOOGL': 'Alphabet Inc.',
                    'MSFT': 'Microsoft Corporation',
                    'AMZN': 'Amazon.com Inc.',
                    'TSLA': 'Tesla, Inc.',
                    'NVDA': 'NVIDIA Corporation',
                    'META': 'Meta Platforms Inc.',
                    'NFLX': 'Netflix Inc.'
                }
                company_name = company_names.get(ticker, ticker)
                print(f"분석 대상: {company_name} ({ticker})")
                
                korean_news = []  # 영문 주식은 한국 뉴스 제외
                english_news = self.fetch_english_news(ticker)
                all_news = english_news
            
            print(f"총 {len(all_news)}개 뉴스 수집 완료")
            
            if not all_news:
                return self._generate_no_news_report(ticker)
            
            # 감정 분석 통계
            sentiments = [news['sentiment'] for news in all_news if news['sentiment'] is not None]
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
            positive_count = len([s for s in sentiments if s > 0.1])
            negative_count = len([s for s in sentiments if s < -0.1])
            neutral_count = len(sentiments) - positive_count - negative_count
            
            print("뉴스 감정 분석 중...")
            
            # 주요 뉴스 요약 (감정 점수 상위/하위)
            sorted_news = sorted(all_news, key=lambda x: abs(x['sentiment']), reverse=True)
            top_news = sorted_news[:5]
            
            # 리포트 생성
            report = self._generate_news_report(ticker, all_news, avg_sentiment, positive_count, negative_count, neutral_count, top_news)
            
            return report
            
        except Exception as e:
            print(f"뉴스 분석 오류: {e}")
            return f"""
## 📰 **{ticker} 뉴스 분석**

❌ **분석 오류**: {str(e)}

다시 시도해 주세요.
            """
    
    def _generate_no_news_report(self, ticker):
        """뉴스가 없을 때 리포트"""
        return f"""
## 📰 **{ticker} 뉴스 분석**

📊 **분석 결과**: 최근 관련 뉴스가 발견되지 않았습니다.

💡 **참고사항**: 
- 뉴스 데이터가 일시적으로 수집되지 않을 수 있습니다
- 종목 코드를 다시 확인해 주세요
"""
    
    def _generate_news_report(self, ticker, all_news, avg_sentiment, positive_count, negative_count, neutral_count, top_news):
        """뉴스 분석 리포트 생성"""
        # 감정 해석
        if avg_sentiment > 0.2:
            sentiment_desc = "📈 **매우 긍정적**"
            sentiment_icon = "🟢"
        elif avg_sentiment > 0.05:
            sentiment_desc = "📊 **긍정적**"
            sentiment_icon = "🔵"
        elif avg_sentiment > -0.05:
            sentiment_desc = "⚖️ **중립적**"
            sentiment_icon = "🟡"
        elif avg_sentiment > -0.2:
            sentiment_desc = "📉 **부정적**"
            sentiment_icon = "🟠"
        else:
            sentiment_desc = "⚠️ **매우 부정적**"
            sentiment_icon = "🔴"
        
        # 주요 뉴스 요약
        news_summary = ""
        for i, news in enumerate(top_news[:3], 1):
            sentiment_emoji = "📈" if news['sentiment'] > 0 else "📉" if news['sentiment'] < 0 else "⚖️"
            news_summary += f"""
**{i}. {news['title'][:50]}...**
{sentiment_emoji} 감정점수: {news['sentiment']:+.3f}
📅 {news['date']}
---
"""
        
        model_type = "KoBERT" if self.is_korean_ticker(ticker) else "FinBERT"
        
        report = f"""
## 📰 **{ticker} 뉴스 분석**

### {sentiment_icon} **종합 감정 분석 ({model_type} 기반)**
- **전체 평균**: {avg_sentiment:+.3f} {sentiment_desc}
- **긍정 뉴스**: {positive_count}개 ({positive_count/len(all_news)*100:.1f}%)
- **중립 뉴스**: {neutral_count}개 ({neutral_count/len(all_news)*100:.1f}%)  
- **부정 뉴스**: {negative_count}개 ({negative_count/len(all_news)*100:.1f}%)

### 📋 **주요 뉴스 헤드라인**
{news_summary}

### 💡 **분석 요약**
- **수집 뉴스**: 총 {len(all_news)}건
- **분석 모델**: {model_type} (트랜스포머 기반)
- **시장 심리**: {sentiment_desc}

※ 이 분석은 실시간 뉴스 데이터와 {model_type} 모델을 기반으로 한 것이며, 
투자 의사결정 시 추가적인 정보를 함께 고려하시기 바랍니다.
"""
        return report

# 글로벌 인스턴스 생성
news_analyzer = NewsAnalyzer()

def run_news_analysis(ticker):
    """뉴스 분석 실행 함수 (backend.py와의 호환성)"""
    return news_analyzer.analyze_news(ticker)

def analyze_news(ticker, company_name=None):
    """이전 버전과의 호환성을 위한 함수"""
    return news_analyzer.analyze_news(ticker) 