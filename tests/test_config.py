import os
from bridger.config import Config

def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    monkeypatch.setenv("OPENCODE_WORKING_DIR", "/tmp/opencode")
    cfg = Config()
    assert cfg.telegram_bot_token == "123:abc"
    assert cfg.telegram_chat_id == "456"
    assert cfg.opencode_working_dir == "/tmp/opencode"
    assert cfg.opencode_server_url == "http://127.0.0.1:4096"
    assert cfg.bridger_timeout == 300
    assert cfg.bridger_log_level == "INFO"

def test_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    try:
        Config()
        assert False, "should raise"
    except ValueError as e:
        assert "TELEGRAM_BOT_TOKEN" in str(e)