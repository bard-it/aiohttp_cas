from urllib import parse
import functools

from aiohttp.web import HTTPForbidden
from aiohttp_session import get_session

from .handlers import login_handler, logout_handler
from .utils import APP_KEY, SESSION_KEY


def setup(app, host, version,
          host_prefix='', host_scheme='https',
          login_route='/login', logout_route='/logout',
          on_success='/', on_logout='/'):
    """Sets up CAS authentication for the app.

    :param app: aiohttp app.
    :param str host: CAS host to authenticate against
    :param str version: Version of CAS to use
    :param str host_prefix: Server prefix that CAS runs under
    :param str host_scheme: Scheme to access the CAS host under
    :param str login_route: Route for local login handler
    :param str logout_route: Route for local logout handler
    :param str on_success: Default route for redirect after a successful login
    :param str on_logout: Route for redirect after logout
    """

    # Add a closing /, if necessary
    if not host_prefix.endswith('/'):
        host_prefix += '/'

    cas_root_url = parse.urlunsplit((
        host_scheme, host, host_prefix,
        None, None
        ))
    app[APP_KEY] = {
                    'VERSION': version,
                    'ROOT_URL': cas_root_url,
                    'LOGIN_ROUTE': login_route,
                    'LOGOUT_ROUTE': logout_route,
                    'ON_SUCCESS': on_success,
                    'ON_LOGOUT': on_logout,
                    }

    app.router.add_route('GET', login_route, login_handler)
    app.router.add_route('GET', logout_route, logout_handler)
    return app


def login_required(func, *args, **kwargs):
    """Decorator for handler functions.

    Applied to a request handler, it will first check if our user is logged in,
    and if they are not, will tack on a redirect parameter to the session set
    to the requested url and run the login handler

    :param func: function to wrap
    """
    @functools.wraps(func)
    async def wrapped(request):
        session = await get_session(request)
        stored_attrs = session.get(SESSION_KEY)
        if (not stored_attrs) or 'user' not in stored_attrs:
            session[SESSION_KEY] = {'redir': request.path}
            return await login_handler(request)
        else:
            return await func(request)
    return wrapped

def filter_attrs(filter_fn, *args, **kwargs):
    """Decorator for handler functions.

    Applied to a request handler, it will apply the filter_fn to the attributes.
    If filter_fn(attrs) returns true, the request will succeed; if not, it raises a
    HTTPForbidden error.

    I think this will only work after at least one @login_required.

    Example:

    @login_required
    @filter_attrs(lambda x: x['employeeType'] != 'staff')
    async def handler(request):
        return "Hello there!"

    :param func: function to wrap
    :param filter_fn: function to evaluate the attributes with
    """
    def actual_decorator(func):
        @functools.wraps(func)
        async def wrapped(request):
            session = await get_session(request)
            stored_attrs = session.get(SESSION_KEY)
            if (not stored_attrs):
                raise HTTPForbidden
            elif filter_fn(stored_attrs):
                return await func(request)
            else:
                raise HTTPForbidden
        return wrapped
    return actual_decorator
