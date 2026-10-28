# 금융 통역사

어려운 금융 문서(예·적금 상품설명서, 대출 안내문, 카드 약관)를 붙여넣으면 쉬운 말로 바꿔 주는 학습 도구입니다.
한 줄 통역, 문장별 통역, 용어와 위험 조항 하이라이트, 내 금액으로 계산, 용어장, 퀴즈를 제공합니다.

> 상품 추천·투자 자문·법률 자문이 아닙니다. 예시 문서와 숫자는 모두 시연용 가상 자료입니다.

## 실행법

### 로컬 실행 (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# AI 통역을 쓰려면 키를 환경변수로 넣는다 (파일에 적지 않는다). 없으면 규칙 기반 모드로 동작
$env:CHATKHU_API_KEY = "발급받은 키"

.\run_local.bat          # http://localhost:8501, 이 컴퓨터에서만 열림
```

키는 환경변수 대신 `.streamlit/secrets.toml`에 둘 수도 있습니다(`.streamlit/secrets.toml.example` 참고, git에는 올라가지 않음).
환경변수가 있으면 환경변수를 먼저 씁니다.

### 배포 (예: Streamlit Community Cloud)

1. 저장소를 연결하고 실행 파일을 `app.py`로 지정합니다. 패키지는 `requirements.txt`로 설치됩니다.
2. 서버의 비밀 값 설정(Secrets)에 `CHATKHU_API_KEY`를 넣습니다. 형식은 `.streamlit/secrets.toml.example`과 같습니다.
3. 서버 주소는 배포 환경이 정하도록 `.streamlit/config.toml`에 넣지 않았습니다. localhost 고정은 `run_local.bat`에서만 합니다.
4. 배포나 push 전에 `python -m scripts.check_secrets`로 비밀 값이 없는지 확인합니다.

### 테스트와 점검 도구

| 명령 | 하는 일 | API 호출 |
|---|---|---|
| `python -m pytest` | 전체 테스트. LLM은 가짜로 대신하고, 실제 클라이언트를 만들면 실패하게 막음 | 없음 |
| `python -m eval.run` | 정답 있는 샘플(r1~r5)로 숫자 추출 정확도, 위험 조항 재현율 (규칙 기반) | 없음 |
| `python -m eval.run --ai --yes` | 같은 평가를 AI 통역으로 | 샘플당 1~2번 |
| `python -m scripts.live_check [샘플 id]` | 샘플 1개를 실제로 통역해 토큰, finish_reason, 원문 대조 결과 출력. `data/samples/*.txt` 시험본도 받음 | 1~2번 |
| `python -m scripts.precompute --yes` | 예시 문서 3종(p1~p3)의 AI 결과를 `data/precomputed/`에 미리 저장 | 3~6번 |
| `python -m scripts.check_secrets` | 커밋 대상 파일과 커밋 이력 전체에서 키, 금지 경로 검사 | 없음 |

`--yes`가 없으면 호출할 샘플 수만 알려 주고 끝납니다.

## 구조

```
app.py                 Streamlit 화면만 담당 (로직은 core/)
config.py              상수 한곳 관리: 모델 이름, 토큰·문서 길이 상한, 호출 한도, 키 읽기
core/
  llm.py               LLMProvider 인터페이스와 ChatKHU 게이트웨이(OpenAI 호환) 구현, 토큰 사용량 로그
  prompts.py           prompts/*.txt 읽기, 긴 문서 자르기
  ai_analyze.py        AI 통역: JSON 검증 -> 형식 오류면 1번 재시도 -> 실패면 규칙 기반 대체, 잘린 답 살리기
  analyze.py           규칙 기반 분석과 계산기 입력값 (뜻이 확실한 숫자만 자동 입력)
  verify.py            AI가 인용한 문장·용어·위험 구절을 원문과 대조
  extract.py           원문 숫자 추출과 숫자 대조
  calc.py              적금·예금·대출·카드 계산
  glossary.py, risks.py  용어 사전, 위험 조항 규칙
  highlight.py         원문 하이라이트 HTML
  mdsafe.py            AI 글의 마크다운 기호 이스케이프
  quiz.py              사전 용어로만 퀴즈 출제와 채점
  wordbook.py          세션 용어장
  precomputed.py       예시 문서의 미리 통역한 결과
  limits.py            AI 호출 한도
prompts/               시스템·통역 프롬프트 (텍스트 파일)
data/
  glossary.json, risks.json   검증된 용어 사전과 위험 조항 규칙
  samples/             예시 문서(.json, r1~r5는 평가용 정답 포함)와 긴 문서 시험본(.txt)
  precomputed/         예시 문서 AI 결과 (scripts/precompute.py로 생성)
eval/                  평가 지표와 실행
scripts/               live_check, precompute, check_secrets, split_raw(원본 데이터 분리)
tests/                 pytest (LLM 호출 없음)
```

## 안전장치

### 환각 방지
- AI가 원문을 인용한 칸(문장별 원문, 용어, 위험 구절)은 원문과 글자 단위로 대조합니다. 띄어쓰기 차이만 봐줍니다.
  원문에 없으면 "원문에서 확인 안 됨"으로 표시하고, 하이라이트·용어장·퀴즈에 쓰지 않습니다.
- AI가 뽑은 숫자도 원문의 숫자와 대조합니다. '30만 원'과 300000처럼 표기가 달라도 같은 값으로 봅니다.
  확인 안 된 숫자는 계산기에 넣지 않습니다.
- 퀴즈의 문제, 정답, 오답 보기는 모두 검증된 사전(`data/glossary.json`)에서만 냅니다.
  용어장도 사전 뜻을 먼저 쓰고, 사전에 없는 용어에는 "AI 설명(미검증)"을 붙입니다.
- 응답 형식이 틀리면 1번만 다시 요청하고, 그래도 틀리면 규칙 기반 모드로 바꾸고 화면에 알립니다.
  응답이 출력 상한에서 잘리면 다시 요청하지 않고, 끝까지 받은 항목만 쓰고 "일부 생략"을 알립니다.
  잘려도 숫자가 남도록 프롬프트에서 숫자를 앞쪽에 둡니다.
- AI가 쓴 글은 화면에 넣기 전에 마크다운 기호를 이스케이프합니다 (예: "5.5~9.9%"가 취소선으로 바뀌지 않게).

### 계산은 코드가 담당
- 이자, 세금(15.4%), 월 상환액, 카드 순이익은 `core/calc.py`가 계산합니다. AI에게 계산을 맡기지 않습니다.
- 계산기에는 원문에서 확인된 숫자 중 뜻이 확실한 것만 자동으로 넣습니다.
  대출 한도, 최소 납입액, 카드 전월 실적처럼 뜻이 불확실한 숫자는 "문서에서 찾은 숫자" 버튼으로만 넣게 합니다.
- 칸마다 "문서에서 읽음 / 예시값 / 내가 입력"을 표시합니다.

### 문서 비저장
- 붙여넣은 문서는 파일이나 DB에 저장하지 않습니다. 세션 메모리에만 있고 세션이 끝나면 사라집니다.
  용어장, 퀴즈 점수, 이해도도 세션 안에서만 쌓입니다.
- 토큰 사용 로그(`logs/llm_usage.log`)에는 시각, 모델, 토큰 수, finish_reason만 남기고 문서 본문과 키는 남기지 않습니다.
- **주의:** AI 통역을 쓰면 문서 본문(앞부분 최대 4,000자)이 ChatKHU API 게이트웨이로 전송됩니다.
  예시 문서는 미리 통역한 결과를 보여 주므로 전송하지 않고, 빠른 분석(규칙 기반)도 전송하지 않습니다.

### 사용량 제한
- AI 호출은 세션당 5회, 서버 전체 하루 60회로 제한합니다 (`config.AI_SESSION_LIMIT`, `config.AI_DAILY_LIMIT`).
  실제로 API에 보낸 요청 수를 세며 재시도도 1번으로 셉니다. 넘으면 호출하지 않고 안내합니다.
- 예시 문서(미리 통역한 결과), 같은 문서의 재통역(세션 안 저장된 결과), 빠른 분석은 횟수를 쓰지 않습니다.
- 하루 횟수는 서버 프로세스 메모리에 있어서, 서버를 다시 시작하면 0부터 다시 셉니다.

### 키 관리
- 키는 코드나 저장소에 두지 않고 환경변수 또는 `st.secrets`에서만 읽습니다.
  `.env`, `.streamlit/secrets.toml`, `.venv/`, 로컬 DB, `logs/`는 `.gitignore`에 있습니다.
- 오류 메시지와 로그에 키가 섞이지 않게, API 오류는 정해 둔 문구로만 바꿔 보여 줍니다.
