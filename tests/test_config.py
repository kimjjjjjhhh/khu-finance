"""키와 주소 읽기: 환경변수 우선, 없으면 st.secrets."""
import config


def test_env_wins_over_secrets(monkeypatch):
    monkeypatch.setattr(config, "_secret", lambda name: "secret-값")
    monkeypatch.setenv("CHATKHU_API_KEY", "  env-값 ")
    assert config.api_key() == "env-값"


def test_secrets_used_when_env_missing(monkeypatch):
    monkeypatch.setattr(config, "_secret", {"CHATKHU_API_KEY": "secret-값", "CHATKHU_BASE_URL": "https://x.invalid"}.get)
    assert config.api_key() == "secret-값"
    assert config.base_url() == "https://x.invalid"


def test_nothing_set(monkeypatch):
    assert config.api_key() is None
    assert config.base_url() == config.DEFAULT_BASE_URL


def test_real_secret_reader_without_file_returns_none(monkeypatch, tmp_path):
    import importlib
    real = importlib.reload(config)._secret  # conftest가 막아 둔 것 말고 진짜 함수
    monkeypatch.chdir(tmp_path)  # 비밀 값 파일이 없는 폴더
    assert real("CHATKHU_API_KEY") is None


def test_secret_finder():
    from scripts.check_secrets import find
    # 가짜 키도 파일에 그대로 적으면 검사에 걸리므로 실행할 때 조립한다
    fake = "abcdefghij" + "klmnopqrstuv"
    assert find(f'KEY = "sk-{fake}"', None) == ["sk- 형식 키"]
    assert find("api_" + f'key = "{fake}"', None) == ["키 대입"]
    assert find("진짜키값123", "진짜키값123") == ["실제 키 값"]
    assert find('SECRET = "sk-test-SECRET-should-never-appear"', None) == []  # 테스트용 가짜 키
    assert find('CHATKHU_API_KEY = "여기에-발급받은-키"', None) == []  # 예시 파일의 자리 표시
