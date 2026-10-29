import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from django.urls import reverse

import jwt


def test_export_json_and_signature(client, project, login_user, settings):
    login_user('owner')
    # Change a known upstream answer, exercising real extraction and UTF-8 hashing.
    answer = project.values.get(snapshot=None, attribute_id=3, set_index=0, collection_index=0)
    answer.text = 'Forschungsdaten: Größe, Köln, 日本語'
    answer.save()

    before = int(time.time())
    response = client.get(reverse('project_export', args=[project.pk, 'coscine-json']))
    after = int(time.time())

    assert response.status_code == 200
    assert response['Content-Type'] == 'text/json'
    assert response['Content-Disposition'] == f'attachment; filename="{project.title}.json"'

    payload = json.loads(response.content)
    token = payload.pop('jwt')
    assert payload['version'] == '1.0.0'
    assert payload['import_type'] == 'rdmo'
    assert payload['project_id'] == str(project.pk)
    assert payload['catalog_title'] == project.catalog.title
    assert payload['catalog_uri'] == project.catalog_uri
    assert {
        'attribute_uri': answer.attribute.uri,
        'question': 'Text?',
        'set': '',
        'values': answer.text,
    } in payload['data']

    claims = jwt.decode(
        token,
        settings.COSCINE_EXPORTS['jwt_secret'],
        algorithms=['HS256'],
        issuer='rdmo-test',
        options={'require': ['iss', 'iat', 'project_id', 'payload_sha256']},
    )
    assert claims['project_id'] == payload['project_id']
    assert type(claims['iat']) is int
    assert before <= claims['iat'] <= after
    # Intentionally independent of the exporter's canonicalization helper.
    canonical = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    assert claims['payload_sha256'] == hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    payload['data'][0]['values'] = 'tampered'
    tampered = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    assert claims['payload_sha256'] != hashlib.sha256(tampered.encode('utf-8')).hexdigest()


@pytest.mark.parametrize(
    ('username', 'status'),
    [('owner', 200), ('manager', 200), ('author', 403), ('guest', 403), ('other', 403)],
)
def test_export_permissions(client, project, login_user, username, status):
    login_user(username)
    response = client.get(reverse('project_export', args=[project.pk, 'coscine-json']))
    assert response.status_code == status


def test_anonymous_export_redirects_to_login(client, project, settings):
    url = reverse('project_export', args=[project.pk, 'coscine-json'])
    response = client.get(url)

    assert response.status_code == 302
    redirect = urlsplit(response['Location'])
    assert redirect.path == urlsplit(settings.LOGIN_URL).path
    assert parse_qs(redirect.query)['next'] == [url]
