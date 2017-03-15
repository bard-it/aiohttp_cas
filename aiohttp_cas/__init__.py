from urllib import parse
import functools

from aiohttp_session import get_session

from .handlers import login_handler, logout_handler
from .utils import APP_KEY, SESSION_KEY


def setup(app, host, version,
          host_prefix='', host_scheme='https',
          login_route='/login', logout_route='/logout',
          on_success='/', on_logout='/'):
    """Sets up the app.

    :param host str: CAS host to authenticate against
    :param version str: Version of CAS to use
    :param host_prefix: Server prefix that CAS runs under
    :param host_scheme: Scheme to access the CAS host under
    :param login_route: Route for local login handler
    :param logout_route: Route for local logout handler
    :param on_success: Default route for redirect after a successful login
    :param on_logout: Route for redirect after logout
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
