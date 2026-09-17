import hashlib
import os
from functools import partial
from unittest.mock import MagicMock

import certifi
import pytest

from cs1302_code_visualizer import trace_generator
from scripts import update_tracer_hash


@pytest.mark.parametrize("existing", [None, "", "/old/cacert.pem", certifi.where()])
@pytest.mark.parametrize("downloader", ["updater", "installer"])
def test_tracer_download_configures_certificates_before_network(
    monkeypatch, tmp_path, existing, downloader
):
    if existing is None:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    else:
        monkeypatch.setenv("SSL_CERT_FILE", existing)
    data = b"test jar contents"
    digest = hashlib.sha256(data).hexdigest()
    url = "https://example.test/tracer.jar"

    def get_url(request_url, **kwargs):
        assert os.environ["SSL_CERT_FILE"] == certifi.where()
        assert request_url == url
        assert kwargs["verify"] == certifi.where()
        assert kwargs["timeout"] == trace_generator.DEFAULT_REQUEST_TIMEOUT
        assert kwargs["stream"] is True
        if downloader == "updater":
            assert kwargs["headers"]["User-Agent"] == "cs1302-code-visualizer/updater"
        return response

    response = MagicMock(status_code=200, headers={})
    response.__enter__.return_value = response
    response.iter_content.return_value = [data[:4], b"", data[4:]]
    monkeypatch.setattr(trace_generator.requests, "get", get_url)
    monkeypatch.setattr(trace_generator, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_generator, "read_tracer_url_and_sum_from_toml", lambda: (url, digest))

    if downloader == "updater":
        assert update_tracer_hash.download_and_hash(url) == (data, digest)
    else:
        trace_generator.ensure_code_tracer_installed()
        assert (tmp_path / "code-tracer.jar").read_bytes() == data

    response.raise_for_status.assert_called_once()
    response.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.parametrize("downloader", ["updater", "installer"])
@pytest.mark.parametrize("failure", ["http", "stream"])
def test_tracer_download_closes_response_on_failure(monkeypatch, tmp_path, downloader, failure):
    response = MagicMock(status_code=200, headers={})
    response.__enter__.return_value = response
    error = trace_generator.requests.HTTPError("download failed")
    if failure == "http":
        response.raise_for_status.side_effect = error
    else:
        response.iter_content.side_effect = error
    monkeypatch.setattr(trace_generator.requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(trace_generator, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_generator, "read_tracer_url_and_sum_from_toml", lambda: None)
    download = (
        partial(update_tracer_hash.download_and_hash, "https://example.test/tracer.jar")
        if downloader == "updater"
        else trace_generator.ensure_code_tracer_installed
    )
    with pytest.raises(trace_generator.requests.HTTPError, match="download failed"):
        download()
    response.__exit__.assert_called_once()
    assert response.__exit__.call_args.args[1] is error
    assert not (tmp_path / "code-tracer.jar").exists()


def test_updater_reports_requests_errors(monkeypatch, tmp_path, capsys):
    config = tmp_path / "pyproject.toml"
    content = 'tracer-url = "https://example.test/tracer.jar"\n'
    config.write_text(content)
    monkeypatch.setattr(
        update_tracer_hash, "parse_args",
        lambda: MagicMock(pyproject=config, url=None, version=None),
    )
    request = MagicMock(side_effect=trace_generator.requests.Timeout("download timed out"))
    monkeypatch.setattr(update_tracer_hash.requests, "get", request)
    assert update_tracer_hash.main() == 1
    assert "Error downloading" in capsys.readouterr().err
    assert config.read_text() == content
