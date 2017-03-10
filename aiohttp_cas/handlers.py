"""Login and logout handlers."""

from aiohttp import web
from aiohttp_session import get_session
from urllib import parse
from .validators import validate
from .utils import cas_url, APP_KEY, SESSION_KEY
from .log import log


async def login_handler(request):
    """Handles login requests.

    We get the ticket ID from the user, the rest comes from info stored on
    the session.
    """
    ticket = request.GET.get('ticket')

    session = await get_session(request)
    redir = session[SESSION_KEY].get('redir')
    login_route = request.app[APP_KEY]['LOGIN_ROUTE']
    root_url = request.app[APP_KEY]['ROOT_URL']
    on_success = request.app[APP_KEY]['ON_SUCCESS']
    version = request.app[APP_KEY]['VERSION']

    # If we're missing neccessary data, return 400 Bad Request
    if not (request.scheme and request.host):
        log.warn("Invalid scheme ({}) or host ({})"
                 .format(request.scheme, request.host))
        return web.HTTPBadRequest()

    # Build the service URL.
    service = parse.urlunsplit(
            (request.scheme, request.host,
             login_route, None, None)
            )

    if ticket:
        # Validate the ticket.
        attrs = await validate(ticket, service, root_url, version)
        # If it succeeds, add the returned attributes to the session.
        if attrs:
            log.info("Authentication suceeded for ticket ID {}".format(ticket))
            session[SESSION_KEY] = attrs
            # Go to the requested redirect or, failing that,
            # the default "on_success" url
            return web.HTTPFound(redir or on_success)
        else:
            # THEY SHALL NOT PASS
            log.info("Authentication fail for ticket ID {}".format(ticket))
            return web.HTTPUnauthorized()
    # If we don't get a ticket (or if something else happens), redirect
    # to the CAS service login.
    return web.HTTPFound(cas_url('login', root_url, service=service))


async def logout_handler(request):
    """Handles logging out

    Gets the logout route, deletes the session data, then redirects the user
    to the logout route.
    """
    session = await get_session(request)
    on_logout = request.app[APP_KEY]['ON_LOGOUT']
    # Delete the session key and redirect to the logout url
    del session[SESSION_KEY]
    return web.HTTPFound(on_logout)
