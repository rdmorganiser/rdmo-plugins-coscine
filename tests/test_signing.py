import hashlib
import json

import pytest

from django.core.exceptions import ImproperlyConfigured

import jwt

from rdmo_coscine.exports import CoscineJSONExport

TEST_SECRET = 'public-test-signing-key-' * 4


@pytest.mark.parametrize('algorithm', ['HS256', 'HS384', 'HS512'])
@pytest.mark.parametrize('issuer', [None, 'rdmo-test'])
def test_signing_claims(algorithm, issuer):
    payload = {'project_id': '42', 'data': [{'values': 'Größe 日本語'}]}
    issued_at = 1_700_000_000
    token = CoscineJSONExport.encode_jwt(
        payload,
        TEST_SECRET,
        algorithm=algorithm,
        issued_at=issued_at,
        issuer=issuer,
    )
    assert token == CoscineJSONExport.encode_jwt(
        payload,
        TEST_SECRET,
        algorithm=algorithm,
        issued_at=issued_at,
        issuer=issuer,
    )
    claims = jwt.decode(token, TEST_SECRET, algorithms=[algorithm])
    canonical = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    expected = {
        'project_id': '42',
        'iat': issued_at,
        'payload_sha256': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
    }
    if issuer:
        expected['iss'] = issuer
    assert claims == expected


@pytest.mark.parametrize('secret', [None, '', 'a' * 31, 123, b'a' * 64])
def test_invalid_signing_secret(settings, exporter, secret):
    settings.COSCINE_EXPORTS = {'jwt_secret': secret}
    with pytest.raises(ImproperlyConfigured, match='jwt_secret'):
        exporter.get_signing_config()


def test_missing_signing_settings(settings, exporter):
    del settings.COSCINE_EXPORTS
    with pytest.raises(ImproperlyConfigured, match='jwt_secret'):
        exporter.get_signing_config()


@pytest.mark.parametrize('algorithm', ['none', 'RS256', '', None])
def test_invalid_signing_algorithm(settings, exporter, algorithm):
    settings.COSCINE_EXPORTS = {'jwt_secret': TEST_SECRET, 'jwt_algorithm': algorithm}
    with pytest.raises(ImproperlyConfigured, match='jwt_algorithm'):
        exporter.get_signing_config()


@pytest.mark.parametrize('algorithm', ['HS256', 'HS384', 'HS512'])
def test_signing_configuration(settings, exporter, algorithm):
    settings.COSCINE_EXPORTS = {
        'jwt_secret': TEST_SECRET,
        'jwt_algorithm': algorithm,
        'jwt_issuer': 'rdmo-test',
    }
    assert exporter.get_signing_config() == settings.COSCINE_EXPORTS


def test_default_signing_configuration(settings, exporter):
    settings.COSCINE_EXPORTS = {'jwt_secret': 'a' * 32}
    assert exporter.get_signing_config() == {
        'jwt_secret': 'a' * 32,
        'jwt_algorithm': 'HS256',
        'jwt_issuer': None,
    }
