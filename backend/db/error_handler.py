'''
python file to handle error handling

Turns the driver-level failures raised by supabase / postgrest / httpx into a
small set of exceptions that describe *what kind* of failure happened, not what
HTTP status to send. The translation to a status code lives in one exception
handler in app.py, so this module stays usable from scripts and tests that have
no web layer.
'''
from contextlib import contextmanager
from postgrest import APIError
import httpx


# --- exception types -------------------------------------------------------

class DatabaseError(RuntimeError):
    '''
    base for every failure raised by the db layer. Raised directly when the cause
    is our own bug or misconfiguration (bad column name, missing table, bad key)
    '''
    def __init__(self, message: str, *, operation: str, code=None):
        super().__init__(message)
        self.operation = operation   # which function failed, for logging
        self.code = code             # postgres SQLSTATE / PGRST code, when there is one


class DatabaseUnavailable(DatabaseError):
    '''
    transient. The database could not be reached, or it gave up on its own
    (timeout, connection exhaustion, gateway error). Retrying is meaningful
    '''


class DatabaseRequestError(DatabaseError):
    '''
    the request itself was rejected, e.g. a malformed uuid or a constraint
    violation. Retrying the identical request will fail the identical way
    '''


# postgres SQLSTATE classes we care about. Anything unlisted falls through to
# DatabaseError, which is the correct default: an unrecognised code is a bug
# until proven otherwise
_TRANSIENT_CODES = {
    "57014",   # query canceled by statement timeout
    "53300",   # too many connections
    "53400",   # configuration limit exceeded
    "40001",   # serialization failure
    "40P01",   # deadlock detected
}
_TRANSIENT_PREFIXES = ("08",)          # connection exception
_BAD_REQUEST_PREFIXES = ("22", "23")   # data exception / integrity constraint violation
_BAD_REQUEST_CODES = {"PGRST103"}      # requested range not satisfiable
_TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}


def _classify(exc: Exception, operation: str) -> DatabaseError:
    '''
    turn a postgrest / httpx failure into one of our three semantic exceptions
    '''
    # no HTTP response ever came back: DNS, refused connection, TLS, timeout
    if isinstance(exc, httpx.HTTPError):
        return DatabaseUnavailable(
            f"{operation}: could not reach the database ({type(exc).__name__})",
            operation=operation,
        )

    code = getattr(exc, "code", None)

    # postgrest falls back to the raw HTTP status when the error body was not
    # JSON (a proxy or cloudflare page), so code can be an int here
    if isinstance(code, int):
        cls = DatabaseUnavailable if code in _TRANSIENT_HTTP else DatabaseError
        return cls(f"{operation}: database returned HTTP {code}", operation=operation, code=code)

    if isinstance(code, str):
        if code in _TRANSIENT_CODES or code.startswith(_TRANSIENT_PREFIXES):
            cls = DatabaseUnavailable
        elif code in _BAD_REQUEST_CODES or code.startswith(_BAD_REQUEST_PREFIXES):
            cls = DatabaseRequestError
        else:
            cls = DatabaseError
        return cls(f"{operation}: {exc}", operation=operation, code=code)

    # no code at all (a 401 from the gateway looks like this) -> our credentials
    return DatabaseError(f"{operation}: {exc}", operation=operation)


@contextmanager
def db_operation(operation: str):
    '''
    wrap a supabase call so every failure leaves the db layer as a DatabaseError
    subclass with the original exception preserved as __cause__
    '''
    try:
        yield
    except (APIError, httpx.HTTPError) as exc:
        raise _classify(exc, operation) from exc
