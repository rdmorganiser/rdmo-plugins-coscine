"""Coscine configuration layered on the release-matched RDMO test application."""

from config.settings import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, 'rdmo_coscine']  # noqa: F405
PROJECT_EXPORTS = [
    *PROJECT_EXPORTS,  # noqa: F405
    ('coscine-json', 'Coscine JSON', 'rdmo_coscine.exports.CoscineJSONExport'),
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}
ALLOWED_HOSTS = ['testserver', 'localhost']
LANGUAGE_CODE = 'en'

# Public test credentials only. Long enough for every supported HMAC algorithm.
COSCINE_EXPORTS = {
    'jwt_secret': 'coscine-test-secret-never-use-in-production-' * 2,
    'jwt_algorithm': 'HS256',
    'jwt_issuer': 'rdmo-test',
}
