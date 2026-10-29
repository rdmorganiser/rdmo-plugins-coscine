# Testing

The initial baseline is Python 3.12, RDMO 2.5.2, and SQLite. Tests use an installed
RDMO package and its release-matched test configuration and fixtures. No deployed
application, browser, external service, or private credentials are needed.

## Local development

From this repository's root, create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Download the upstream testing files once. Use the same release for the checkout
and installed RDMO package:

```bash
export RDMO_VERSION=2.5.2
git clone --depth 1 --branch "$RDMO_VERSION" --filter=blob:none --sparse \
  https://github.com/rdmorganiser/rdmo.git .rdmo-testing
git -C .rdmo-testing sparse-checkout set testing
python -m pip install -e '.[test]' "rdmo[allauth,openapi]==$RDMO_VERSION"
pytest
```

The checkout is ignored by Git. Only `.rdmo-testing/testing` is added to the
Python path, so RDMO itself comes from the installed package. The `test` extra
declares pytest and pytest-django directly; RDMO's larger `pytest` extra is not
required. Dependency installation and the initial checkout require network
access; the tests themselves do not.

Run just the unit tests with:

```bash
pytest tests/test_signing.py tests/test_pid_mapping.py
```

These tests initialize Django but do not request a database. Use `--setup-show`
to inspect fixture activation: `django_db_setup` should not appear in a unit-only
run. Run the endpoint tests with `pytest tests/test_exports.py`.

To check the Django configuration separately:

```bash
PYTHONPATH="$PWD/testing:$PWD/.rdmo-testing/testing" \
  DJANGO_SETTINGS_MODULE=coscine_test_settings python -m django check
```

The upstream RDMO 2.5.2 test URL configuration emits a `urls.W005` warning about
the duplicate `v1-openapi` namespace. It also occurs without this plugin; the
configuration check still exits successfully.

For lint checks, install `ruff` (also included in the `dev` extra), then run:

```bash
ruff check testing tests
ruff format --check testing tests
```

## Pre-commit hooks

The pre-commit configuration runs Ruff linting and formatting, offline zizmor
audits of GitHub Actions and pre-commit configuration, and the existing file
checks and spelling checks. All third-party hook revisions are frozen to commit
SHAs, with release versions recorded in comments.

Install pre-commit (also included in the `dev` extra), enable the hooks locally,
and check all tracked files:

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

Hook installation needs network access on its first run. The zizmor audits run
offline and do not require a GitHub token. To update hook releases while keeping
the configuration frozen:

```bash
pre-commit autoupdate --freeze
```

## Verify the installed wheel

Editable installation is convenient for development. To verify packaging,
including the bundled DFG mapping, use a fresh environment and run pytest outside
the source directory. The following Bash commands start from the repository root
after downloading the upstream testing files above:

```bash
repo_dir="$PWD"
wheel_env=$(mktemp -d)
python3.12 -m venv "$wheel_env/venv"
"$wheel_env/venv/bin/python" -m pip install build
"$wheel_env/venv/bin/python" -m build --wheel --outdir "$wheel_env/wheels"
wheels=("$wheel_env"/wheels/*.whl)
"$wheel_env/venv/bin/python" -m pip install \
  "${wheels[0]}[test]" "rdmo[allauth,openapi]==${RDMO_VERSION:-2.5.2}"
"$wheel_env/venv/bin/python" -m pip check
(
  cd "$wheel_env"
  "$wheel_env/venv/bin/pytest" -c "$repo_dir/pyproject.toml" "$repo_dir/tests"
)
```

The suite uses pytest's `importlib` import mode and disables automatic Django
project discovery. Neither the plugin source directory nor the upstream RDMO
source directory is added to `sys.path` by the test configuration. Avoid
`python -m pytest` from the source root when verifying a wheel: Python adds that
working directory to its import path. Also avoid adding the repository root to
`PYTHONPATH` yourself.

## Test responsibilities

`testing/coscine_test_settings.py` extends upstream `config.settings`, registers
the plugin, and configures an in-memory SQLite database and public test signing
credentials. Coscine-specific fixtures live in `tests/conftest.py`.

`testing/rdmo_test_fixtures.py` is a separate, generic pytest plugin. It extends
pytest-django's normal migrated database setup, loads the explicitly allowed
upstream fixture files, and initializes group permissions. Its allowlist matches
[RDMO 2.5.2's conftest.py](https://github.com/rdmorganiser/rdmo/blob/2.5.2/conftest.py),
which excludes `config.json`. Missing expected files cause a clear setup error.
Upstream's root `conftest.py` is not automatically loaded by this suite.

The database and fixture data are created only when a test requests database
access. Endpoint tests use ordinary pytest-django transaction rollback isolation,
project `1`, and the upstream owner/manager/author/guest accounts. Answer changes
belong to individual tests and are rolled back. Transactional tests and
`live_server` would require reloading data after database flushes and are outside
the initial setup. Migrations remain enabled.

The tests cover the real export route, permissions, expected answer content,
download headers, JWT claims and signature, Unicode payload hashing, identifier
mapping, and invalid signing configuration. No RDMO functionality is mocked.

## CI and later extraction

Both workflows initially live here:

- `.github/workflows/ci.yml` triggers on pull requests and pushes to `main` and
  calls the local reusable workflow.
- `.github/workflows/_plugin-tests.yml` accepts `rdmo-version`, `python-version`
  (default `3.12`), and `django-settings-module` inputs. Callers provide a
  `pyproject.toml` with a `test` extra, a `tests/` suite, and a `testing/` directory
  containing importable test support and settings.

The reusable workflow checks out matching upstream testing files, builds and
installs the caller's wheel with its test extra, and checks dependency consistency.
It checks Django and runs pytest from the runner's temporary directory, using
explicit paths. Its import check discovers the wheel's top-level packages and
requires them and RDMO to resolve inside the installed Python environment. The
workflow currently expects a wheel with at least one regular Python package.
Actions are pinned to commit SHAs and checkout credentials are not persisted.

Keep these extraction boundaries:

| Component | Current owner | Later destination |
| --- | --- | --- |
| Reusable workflow and generic import check | This repository | `rdmorganiser/.github` |
| Generic fixture loader | This repository | RDMO's `testing/`, alongside its fixtures |
| Settings, behavioral tests, test-specific data | This plugin | Remain here |

Moving the workflow later requires changing the caller's `uses` reference to a
versioned shared workflow. It needs no Coscine-specific Python code. Moving the
fixture module alongside upstream fixtures preserves its import name:
`pytest_plugins = ['rdmo_test_fixtures']`; the local copy can then be removed once
the selected RDMO release provides it. The workflow does not copy Python support
from the shared `.github` repository.

Validate this arrangement with a second plugin before expanding its interface.
Compatibility matrices, PostgreSQL, browser tests, external-service mocking, and
a separately distributed testing package are deferred. Hosted workflow execution
must be confirmed on the first pushed branch or pull request.
