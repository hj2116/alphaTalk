If you are reading this. You are a part of us.
Please use a seperate branch when implementing a new feature(s). 

## AlphaTalk AI Investment Analysis API

### 설정 방법

1. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

2. 환경 변수 설정:
`.env` 파일을 프로젝트 루트에 생성하고 다음 내용을 추가:

```env
# MongoDB 연결 URI
MONGO_URI=mongodb://localhost:27017/alphatalk
# CLOVA_API_KEY=your_clova_api_key_here
# DART_API_KEY=your_dart_api_key_here
```

3. 서버 실행:
```bash
python kakao.py
```

### 주요 변경사항

- **데이터베이스 연동**: 메모리 캐시에서 MongoDB로 변경
- **분석 결과 영구 저장**: 분석 결과가 데이터베이스에 저장되어 서버 재시작 후에도 유지
- **개별 분석 조회**: 퀀트, 펀더멘털, 뉴스 분석을 개별적으로 조회 가능

### API 엔드포인트

#### 분석 관련
- `POST /analyze/{ticker}` - 주식 종목 분석 시작 (관심 종목 추가 없이)
- `POST /detail/{ticker}` - 상세 분석 결과 조회
- `POST /quant/{ticker}` - 퀀트 분석 결과 조회
- `POST /fundamental/{ticker}` - 펀더멘털 분석 결과 조회  
- `POST /news/{ticker}` - 뉴스 분석 결과 조회

#### 사용자별 관심 종목 관리
- `POST /add/` - 관심 종목 추가 및 분석 시작 
- `POST /my-tickers` - 사용자의 관심 종목 목록 조회
- `POST /remove/{ticker}` - 관심 종목에서 제거
- `POST /user-info` - 사용자 계정 정보 조회

#### 관리 기능
- `POST /admin/cleanup` - 오래된 분석 결과 정리
- `GET /admin/stats` - 시스템 통계 조회 (관리자용)
- `GET /health` - 서버 상태 및 DB 연결 확인

### 사용자별 관심 종목 관리 기능
- **다중 종목 지원**: 한 사용자가 여러 개의 관심 종목을 추가할 수 있습니다
- **개인화**: 각 사용자의 관심 종목이 독립적으로 관리됩니다

#### 사용 예시
`006800 추가` → 미래에셋 주식을 관심 종목에 추가
### 데이터베이스 구조

```javascript
// users 컬렉션 - 효율적인 배열 구조
{
  user_id: "kakao_user_123",
  tickers: ["AAPL", "TSLA", "NVDA"],
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T12:30:00Z"
}

// analyses 컬렉션 - 분석 결과 저장
{
  ticker: "AAPL",
  timestamp: "2024-01-01T12:00:00Z",
  quant_analysis: "...",
  fundamental_analysis: "...",
  news_analysis: "...",
  final_recommendation: "..."
}
```
