'''
Shared setup for the integration suite.

These tests run against the *local* Supabase stack (`supabase start`), never a
remote project. Everything here exists to guarantee that:

  1. the local stack's credentials are discovered automatically, so no secret
     ever has to be committed or copied into a test config;
  2. `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are set before
     `backend.db.supabase_operations` is imported (that module builds its
     client at import time, so the env has to be right first);
  3. the whole suite skips cleanly when the stack is down, instead of failing
     with a confusing connection error;
  4. the destructive teardown can only ever point at localhost.
'''

import importlib
import os
import shutil
import subprocess

import pytest

# ---------------------------------------------------------------------------
# Discover the local stack's credentials.
#
# This runs at conftest import time (before any test module is imported) because
# backend.db.supabase_operations reads os.environ at *its* import time.
# ---------------------------------------------------------------------------

LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0")

_local_env: dict[str, str] = {}
_unavailable: str | None = None


def _read_supabase_status() -> dict[str, str]:
    '''
    Ask the Supabase CLI for the running stack's URLs and keys.

    `supabase status -o env` prints shell-style KEY="value" lines, which is a
    stable contract across CLI versions even as the key *names* change
    (SERVICE_ROLE_KEY vs SECRET_KEY, ANON_KEY vs PUBLISHABLE_KEY).
    '''
    if shutil.which("supabase") is None:
        raise RuntimeError("the `supabase` CLI is not installed")

    result = subprocess.run(
        ["supabase", "status", "-o", "env"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())

    values = {}
    for line in result.stdout.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    return values


def _pick(values: dict[str, str], *names: str) -> str:
    for name in names:
        if values.get(name):
            return values[name]
    raise RuntimeError(f"`supabase status` reported none of {names}")


try:
    _status = _read_supabase_status()
    _local_env = {
        "SUPABASE_URL": _pick(_status, "API_URL"),
        # Newer CLI releases renamed the privileged key; accept either spelling.
        "SUPABASE_SERVICE_ROLE_KEY": _pick(_status, "SERVICE_ROLE_KEY", "SECRET_KEY"),
        "SUPABASE_ANON_KEY": _pick(_status, "ANON_KEY", "PUBLISHABLE_KEY"),
        "DB_URL": _pick(_status, "DB_URL"),
    }
    # Point the module-level client in supabase_operations at the local stack.
    # This deliberately overrides whatever is in the developer's shell or .env.
    os.environ["SUPABASE_URL"] = _local_env["SUPABASE_URL"]
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = _local_env["SUPABASE_SERVICE_ROLE_KEY"]
except Exception as exc:  # CLI missing, stack down, Docker down, ...
    _unavailable = str(exc)


def _assert_local(url: str) -> None:
    '''
    Hard stop against ever running a truncating test suite at a real project.

    Cheap to check, and the one failure mode here is unrecoverable.
    '''
    if not any(host in url for host in LOCAL_HOSTS):
        pytest.exit(
            f"refusing to run integration tests against non-local host: {url}",
            returncode=1,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def local_supabase() -> dict[str, str]:
    '''
    Credentials for the running local stack, or a skip if it isn't up.
    '''
    if _unavailable is not None:
        pytest.skip(
            f"local Supabase stack is not available ({_unavailable}). "
            "Start it with: supabase start && supabase db reset"
        )
    _assert_local(_local_env["SUPABASE_URL"])
    _assert_local(_local_env["DB_URL"])
    return _local_env


@pytest.fixture(scope="session")
def ops(local_supabase):
    '''
    The module under test.

    Imported lazily rather than at the top of the test file because
    backend.db.supabase_operations calls create_client() at import time: if the
    env isn't already pointed at the local stack, importing it either blows up
    or — worse — silently binds to whatever project the developer's .env names.
    '''
    return importlib.import_module("backend.db.supabase_operations")


@pytest.fixture(scope="session")
def db(local_supabase):
    '''
    A direct psycopg connection, used only for setup/teardown.

    Talking to Postgres directly (rather than through PostgREST) keeps teardown
    independent of the API layer the tests are actually exercising.
    '''
    import psycopg

    with psycopg.connect(local_supabase["DB_URL"], autocommit=True) as conn:
        yield conn


@pytest.fixture(autouse=True)
def clean_tables(db):
    '''
    Give every test an empty database.

    Truncating up front (rather than after) means a failed test leaves its rows
    behind for inspection. RESTART IDENTITY keeps conversations.id predictable
    from run to run; CASCADE follows the conversations -> threads foreign key.
    '''
    with db.cursor() as cur:
        cur.execute("truncate table public.threads restart identity cascade")
    yield
