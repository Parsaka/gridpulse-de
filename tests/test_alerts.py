import httpx

from gridpulse import alerts


def test_alert_posts_text_and_content(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, json=json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(alerts.httpx, "post", fake_post)
    assert alerts.send_alert("db down", url="http://hook.test/x") is True
    assert seen["url"] == "http://hook.test/x"
    assert seen["json"] == {"text": "db down", "content": "db down"}


def test_alert_without_url_is_logged_not_sent(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_ALERT_WEBHOOK", "")
    monkeypatch.setattr(alerts.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert alerts.send_alert("nobody listening") is False


def test_alert_delivery_failure_never_raises(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(alerts.httpx, "post", boom)
    assert alerts.send_alert("x", url="http://hook.test/x") is False


def test_alert_http_error_status_returns_false(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(alerts.httpx, "post", fake_post)
    assert alerts.send_alert("x", url="http://hook.test/x") is False
