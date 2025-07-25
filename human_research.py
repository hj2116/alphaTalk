import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import parse_qs, urlparse
import pandas as pd

# User-Agent 설정
headers_pc = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/114.0.0.0 Safari/537.36"
}
headers_mobile = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
}

def fetch_posts(stock_code, max_page=250):
    data = []
    for page in range(1, max_page + 1):
        url = f"https://finance.naver.com/item/board.naver?code={stock_code}&page={page}"
        resp = requests.get(url, headers=headers_pc)
        soup = BeautifulSoup(resp.text, "html.parser")
        post_links = soup.select("td.title a")

        for post_link in post_links:
            title = post_link.text.strip()
            relative_href = post_link["href"]
            qs = parse_qs(urlparse(relative_href).query)
            nid = qs.get("nid", [None])[0]
            if not nid:
                continue

            iframe_src = f"https://m.stock.naver.com/pc/domestic/stock/{stock_code}/discussion/{nid}"
            try:
                resp2 = requests.get(iframe_src, headers=headers_mobile)
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                script_tag = soup2.find("script", id="__NEXT_DATA__")
                if not script_tag:
                    continue
                data_json = json.loads(script_tag.string)
                content_html = data_json["props"]["pageProps"]["dehydratedState"]["queries"][1]["state"]["data"]["result"]["contentHtml"]
                content_soup = BeautifulSoup(content_html, "html.parser")
                text = content_soup.get_text(separator="\n").strip()
                data.append({"제목": title, "본문": text})
            except:
                continue
    return data

import csv
import requests
from bs4 import BeautifulSoup
import sys
import os

# 한국어 뉴스 감성 분석을 위한 프롬프트
KOREAN_SENTIMENT_PROMPT = """
당신은 전문 금융 분석가입니다. 주어진 한국어 뉴스 기사의 감성을 분석하여 주식 투자에 미치는 영향을 판단해주세요.

분석 기준:
- 긍정적 (1.0): 주가 상승에 도움이 되는 내용
- 중립적 (0.0): 주가에 큰 영향을 주지 않는 내용  
- 부정적 (-1.0): 주가 하락에 영향을 주는 내용

응답 형식: 반드시 숫자 점수만 출력해주세요 (예: 0.7, -0.3, 0.0)
"""

def fetch_news(stock_code, max_pages=10):
    all_news = []
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page={page}&sm=title_entity_id.basic&clusterId="
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.naver.com/"
        }
        resp = requests.get(url, headers=headers)
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table.type5 tr")
        for row in rows:
            a_tag = row.select_one("td.title a")
            if a_tag:
                title = a_tag.get_text(strip=True)
                link = a_tag["href"]
                press = row.select_one("td.info")
                press_text = press.get_text(strip=True) if press else ""
                date = row.select_one("td.date")
                date_text = date.get_text(strip=True) if date else ""

                full_link = "https://finance.naver.com" + link
                all_news.append({
                    "날짜": date_text,
                    "언론사": press_text,
                    "제목": title,
                    "링크": full_link
                })
    return all_news

def fetch_article_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.naver.com"
    }
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")

    # 리다이렉트 처리
    redirect_script = soup.select_one("script")
    if redirect_script and "top.location.href" in redirect_script.get_text():
        try:
            redirect_url = redirect_script.get_text().split("top.location.href='")[1].split("'")[0]
            resp = requests.get(redirect_url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return "리다이렉트 실패"

    content_div = soup.select_one("#dic_area")
    if content_div:
        return content_div.get_text(separator="\n").strip()
    else:
        return "None"

def compute_sentiment_score(text):
    """Clova Chat API를 사용한 한국어 뉴스 감성 분석"""
    if not text or text.strip() == "":
        return 0.0
    
    # 텍스트가 너무 길면 처음 1000자만 사용
    if len(text) > 1000:
        text = text[:1000] + "..."
    
    # Rate limit 방지를 위한 시간 지연
    import time
    time.sleep(0.5)  # 0.5초 대기
    
    try:
        # backend 모듈을 함수 내부에서 import하여 순환 참조 방지
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from backend import makeRequest, makeMessage
        
        messages = [
            makeMessage("system", KOREAN_SENTIMENT_PROMPT),
            makeMessage("user", f"다음 뉴스 기사를 분석해주세요:\n\n{text}")
        ]
        
        response = makeRequest(messages)
        
        if response and response.get("result"):
            content = response["result"]["message"]["content"].strip()
            # 숫자만 추출
            import re
            score_match = re.search(r'-?\d+\.?\d*', content)
            if score_match:
                score = float(score_match.group())
                # -1.0 ~ 1.0 범위로 제한
                score = max(-1.0, min(1.0, score))
                return round(score, 4)
        
        return 0.0  # 기본값
        
    except Exception as e:
        print(f"감성 분석 오류: {e}")
        return 0.0

def save_news_with_sentiment(stock_code, max_pages=10, filename=None):
    if filename is None:
        filename = f"naver_news_{stock_code}.csv"
    
    news_list = fetch_news(stock_code, max_pages)
    for news in news_list:
        content = fetch_article_content(news["링크"])
        news["본문"] = content if content else "본문 없음"
        news["감성점수"] = compute_sentiment_score(content) if content else 0.0
        news.pop("언론사", None)
        news.pop("링크", None)

    fieldnames = ["날짜", "제목", "본문", "감성점수"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in news_list:
            writer.writerow(item)

    print(f"{filename}")

import requests
from datetime import datetime, timedelta
import pandas as pd
from newspaper import Article
from transformers import BertTokenizer, BertForSequenceClassification
import torch
import re

# FinBERT 모델 초기화
def load_finbert_model():
    model_name = "yiyanghkust/finbert-tone"
    tokenizer = BertTokenizer.from_pretrained(model_name)
    model = BertForSequenceClassification.from_pretrained(model_name)
    return tokenizer, model

# 텍스트 정제 함수
def clean_text(text):
    if not text:
        return ""
    text = text.lower()  # 소문자화
    text = re.sub(r'\s+', ' ', text)  # 다중 공백 제거
    text = re.sub(r'\n+', ' ', text)  # 줄바꿈 제거
    text = re.sub(r'[^a-zA-Z0-9.,!?\'\"%$()-]', ' ', text)  # 특수문자 제거
    text = text.strip()
    return text

# 감성 점수 계산 함수
def compute_sentiment_finbert(text, tokenizer, model):
    try:
        text = clean_text(text)
        tokens = tokenizer.encode(text, truncation=True, padding='max_length', max_length=512, return_tensors='pt')
        with torch.no_grad():
            output = model(tokens)
        logits = output.logits
        probs = torch.softmax(logits, dim=1).numpy()[0]
        sentiment_score = probs[2] - probs[0]
        return round(float(sentiment_score), 4)
    except Exception:
        return None

# 뉴스 수집 및 본문 크롤링 함수
def fetch_news_with_full_body_and_sentiment(ticker, days=3, max_results=100, api_key="5a9d9ae903084a349d94fdff1fb3da6a"):
    url = "https://newsapi.org/v2/everything"
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    from_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_articles = []
    page = 1

    while True:
        params = {
            "q": ticker,
            "from": from_date_str,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
            "page": page,
            "apiKey": api_key
        }

        response = requests.get(url, params=params)
        data = response.json()

        if data.get("status") != "ok":
            print(f"Error: {data.get('message')}")
            break

        articles = data.get("articles", [])
        if not articles:
            break

        all_articles.extend(articles)

        if len(all_articles) >= max_results or len(articles) < 100:
            break

        page += 1

    # 본문 크롤링 및 감성 점수 적용
    tokenizer, model = load_finbert_model()

    for article in all_articles:
        url = article.get("url")
        full_text = ""
        if url:
            try:
                news_article = Article(url)
                news_article.download()
                news_article.parse()
                full_text = news_article.text
            except Exception:
                full_text = article.get("description") or ""
        else:
            full_text = article.get("description") or ""

        article["full_body"] = full_text
        article["sentiment_score"] = compute_sentiment_finbert(full_text, tokenizer, model)

    newsapi = pd.DataFrame(all_articles)
    newsapi = newsapi[["publishedAt", "title", "full_body", "sentiment_score"]]
    newsapi["publishedAt"] = pd.to_datetime(newsapi["publishedAt"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    newsapi.rename(columns={
        "publishedAt": "Date",
        "title": "Title",
        "full_body": "Body",
        "sentiment_score": "SentimentScore"
    }, inplace=True)

    newsapi = newsapi.head(max_results)

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    filename = f"newsapi_{ticker}.csv"
    newsapi.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"{filename} 총 {len(newsapi)}건")

    return newsapi

import asyncio
import nest_asyncio
import asyncpraw
from datetime import datetime, timedelta
import pandas as pd

nest_asyncio.apply()

reddit_api = asyncpraw.Reddit(
    client_id="4KYCTTNnmyNxyQwDS_fy6g",
    client_secret="CvxFEpg_IDU_uYxjJsrQWjOR2eXpnA",
    user_agent="stock_posts by /u/Leather_Arugula7011"
)

async def fetch_reddit_posts_async(ticker, subreddits=["stocks", "wallstreetbets", "investing"], days=3, limit=100):
    results = []
    now = datetime.utcnow()
    threshold_date = (now - timedelta(days=days)).date()
    time_threshold = datetime.combine(threshold_date, datetime.min.time())

    for subreddit_name in subreddits:
        subreddit = await reddit_api.subreddit(subreddit_name)
        async for submission in subreddit.search(ticker, sort="new", limit=limit):
            post_date = datetime.utcfromtimestamp(submission.created_utc)
            if post_date < time_threshold:
                continue

            results.append({
                "Subreddit": subreddit_name,
                "Date": post_date.strftime("%Y-%m-%d %H:%M:%S"),
                "Title": submission.title,
                "Body": submission.selftext[:500],
                "Link": f"https://www.reddit.com{submission.permalink}"
            })

    reddit_df = pd.DataFrame(results)
    filename = f"reddit_{ticker}.csv"
    reddit_df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"'{filename}' 총 {len(reddit_df)}건 ")

if __name__ == "__main__":
    stock_code = input("종목 코드를 입력하세요: ").strip()
    posts = fetch_posts(stock_code, max_page=50)
    df = pd.DataFrame(posts)
    output_file = f"naver_discussion_{stock_code}.csv"
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"CSV 파일로 저장 완료: {output_file}")

