"""Generic pytest support, suitable for moving alongside RDMO's test fixtures.

Keep plugin-specific settings and test data out of this module. The allowlist
matches rdmo/conftest.py at release 2.5.2, including its exclusion of config.json.
"""

from pathlib import Path

import pytest

from django.conf import settings
from django.core.management import call_command

from rdmo.accounts.utils import set_group_permissions

FIXTURE_NAMES = (
    'accounts',
    'conditions',
    'domain',
    'groups',
    'options',
    'overlays',
    'projects',
    'questions',
    'sites',
    'tasks',
    'users',
    'views',
)


@pytest.fixture(scope='session')
def rdmo_fixture_files():
    paths = sorted(
        path
        for directory in settings.FIXTURE_DIRS
        for name in FIXTURE_NAMES
        if (path := Path(directory) / f'{name}.json').is_file()
    )
    missing = set(FIXTURE_NAMES) - {path.stem for path in paths}
    if missing:
        raise pytest.UsageError(
            f'Missing RDMO fixtures: {", ".join(sorted(missing))}. '
            'Check the release-matched .rdmo-testing checkout and FIXTURE_DIRS.'
        )
    return paths


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker, rdmo_fixture_files):
    """Extend pytest-django's migrated test database with upstream fixture data."""
    with django_db_blocker.unblock():
        call_command('loaddata', *rdmo_fixture_files, verbosity=0)
        set_group_permissions()
