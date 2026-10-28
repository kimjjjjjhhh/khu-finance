@echo off
chcp 65001 >nul
rem 로컬 실행: 이 컴퓨터에서만 열린다 (같은 네트워크의 다른 기기는 접속 못 함)
cd /d "%~dp0"
if "%CHATKHU_API_KEY%"=="" if not exist ".streamlit\secrets.toml" echo [안내] API 키가 없어 AI 통역 대신 규칙 기반 모드로 동작합니다.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address localhost
