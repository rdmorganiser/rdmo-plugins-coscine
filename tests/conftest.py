import pytest

from django.contrib.auth import get_user_model

from rdmo.core.plugins import get_plugin
from rdmo.projects.models import Project

pytest_plugins = ['rdmo_test_fixtures']


@pytest.fixture
def exporter():
    return get_plugin('PROJECT_EXPORTS', 'coscine-json')


@pytest.fixture
def project(db):
    return Project.objects.get(pk=1)


@pytest.fixture
def login_user(db, client):
    def login(username):
        client.force_login(get_user_model().objects.get(username=username))

    return login
