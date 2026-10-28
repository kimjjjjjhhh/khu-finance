"""저장소에 비밀 값이 없는지 검사한다. 배포나 push 전에 실행: python -m scripts.check_secrets

- 커밋 대상 파일(추적 중 + 새 파일, .gitignore 제외)과 커밋 이력 전체(git log -p)를 본다
- 실제 키 값(환경변수나 st.secrets에 있으면)과 키처럼 생긴 문자열을 찾는다
- 올라가면 안 되는 경로(.env, secrets.toml, .venv, DB, logs)가 이력에 있는지 본다
찾은 값은 출력하지 않고 파일 이름과 종류만 보여 준다. 문제가 있으면 종료 코드 1.
"""
import re
import subprocess
import sys

import config

# 테스트가 일부러 쓰는 가짜 키 (키가 새지 않는지 확인하는 용도)
ALLOWED = {"sk-test-SECRET-should-never-appear"}
PATTERNS = {
    "sk- 형식 키": re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    "Bearer 토큰": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    "AWS/GitHub/Google 키": re.compile(r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_\-]{30,}"),
    "키 대입": re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"),
}
FORBIDDEN_PATH = re.compile(r"(^|/)(\.env($|\.)|\.venv/|logs/)|secrets\.toml$|\.(db|sqlite3|log)$")
PLACEHOLDER = re.compile(r"여기에|your[-_]|example|placeholder|xxx", re.I)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def find(text: str, key: str | None) -> list[str]:
    kinds = ["실제 키 값"] if key and key in text else []
    for name, p in PATTERNS.items():
        for m in p.finditer(text):
            value = m.group(m.lastindex or 0)
            if value not in ALLOWED and m.group(0) not in ALLOWED and not PLACEHOLDER.search(value):
                kinds.append(name)
    return sorted(set(kinds))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    key = config.api_key()
    problems = 0

    files = [f for f in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines() if f]
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if kinds := find(text, key):
            print(f"[파일] {f}: {', '.join(kinds)}")
            problems += 1
        if FORBIDDEN_PATH.search(f):
            print(f"[파일] {f}: 올라가면 안 되는 경로")
            problems += 1

    history = git("log", "--all", "-p", "--no-color", "--format=commit %h")
    added = "\n".join(l[1:] for l in history.splitlines() if l.startswith("+") and not l.startswith("+++"))
    if kinds := find(added, key):
        print(f"[이력] 추가된 줄에서: {', '.join(kinds)}")
        problems += 1
    paths = {p for p in git("log", "--all", "--pretty=format:", "--name-only").splitlines() if p}
    for p in sorted(paths):
        if FORBIDDEN_PATH.search(p):
            print(f"[이력] {p}: 올라가면 안 되는 경로")
            problems += 1

    n_commits = len(git("rev-list", "--all").split())
    print(f"검사: 파일 {len(files)}개, 커밋 {n_commits}개, 이력 경로 {len(paths)}개, "
          f"실제 키 값 대조 {'함' if key else '안 함 (키 없음)'}")
    print("문제 없음" if not problems else f"문제 {problems}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
