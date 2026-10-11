"""SSL CA bundle selection for the .app bundle (whispy.ssl_certs)."""

import os

import certifi

from whispy.ssl_certs import use_certifi_if_missing


def test_unset_vars_point_at_certifi():
    env: dict[str, str] = {}
    use_certifi_if_missing(env)
    assert env["SSL_CERT_FILE"] == certifi.where()
    assert env["SSL_CERT_DIR"] == os.path.dirname(certifi.where())


def test_py2app_dangling_path_is_replaced():
    # py2app's __boot__ sets these to a file that does not exist; httpx then
    # failed every HTTPS request with a bare FileNotFoundError.
    bogus = "/Applications/Whispy.app/Contents/Resources/openssl.ca/no-such-file"
    env = {"SSL_CERT_FILE": bogus, "SSL_CERT_DIR": bogus}
    use_certifi_if_missing(env)
    assert env["SSL_CERT_FILE"] == certifi.where()
    assert env["SSL_CERT_DIR"] == os.path.dirname(certifi.where())


def test_existing_user_choice_is_kept(tmp_path):
    cafile = tmp_path / "corp-ca.pem"
    cafile.write_text("dummy")
    env = {"SSL_CERT_FILE": str(cafile), "SSL_CERT_DIR": str(tmp_path)}
    use_certifi_if_missing(env)
    assert env == {"SSL_CERT_FILE": str(cafile), "SSL_CERT_DIR": str(tmp_path)}
