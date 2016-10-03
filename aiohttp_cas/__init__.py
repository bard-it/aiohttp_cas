from urllib import parse
import functools

from lxml import etree
import aiohttp
from aiohttp import web
from aiohttp_session import get_session

APP_KEY = 'aiohttp_cas'
SESSION_KEY = 'aiohttp_cas'


class InvalidCasResponse(Exception):
    def __init__(self, message, resp):
        super().__init__(message)
        self.resp = resp


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
    cas_root_url = parse.urlunsplit((
        host_scheme, host, host_prefix + '/',
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


def cas_url(kind, root_url, **kwargs):
    args = parse.urlencode(kwargs)
    url = parse.urljoin(root_url, kind)

    return url + '?' + args


def process_attributes(cas_response):
    """Handles processing the attributes of a CAS3 SAML 1.1(?) response.

    I've seen three different types:
    1) The <cas:authenticationSuccess> element has several <cas:attribute>
       children, each of which has a 'name' and 'value' attribute.
    2) The <cas:authenticationSuccess> element has one <cas:attributes> child,
       which has several <cas:attribute> children, each of which has sibling
       <cas:name> and <cas:value> children
    3) The <cas:authenticationSuccess> element has several children, of the
       form <cas:{attribute name}>{attribute value}</cas:{attribute_name}>

    This should returns a dict version of the attributes, no matter what form
    they take (or, god forbid, a mix for some reason)

    TODO this needs testing for every case still!
    """
    out = {}
    nsmap = {'cas': 'http://www.yale.edu/tp/cas'}
    # First, try to see if we have any <cas:attributes> children anywhere down
    # the line.
    loose_attributes = cas_response.findall('*/cas:attribute', nsmap)
    for attribute in loose_attributes:
        key = None
        value = None
        key_elt = attribute.find('cas:name', nsmap)
        value_elt = attribute.find('cas:value', nsmap)
        if key_elt and value_elt:
            key = key_elt.text
            value = value_elt.text
        if attribute.attrib:
            key = attribute.attrib['name']
            value = attribute.attrib['value']
        if key and value:
            out[key] = value
    # This filters out any <cas:attribute> children of any <cas:attributes>
    # element, since the above should have caught them
    named_attributes = cas_response.xpath(
            '*/cas:attributes/*[not(cas:attribute)]',
            namespaces=nsmap)
    for attribute in named_attributes:
        # This is ugly, but it should work to get the name of the attribute
        # from lxml's fully-qualified tag name
        key = attribute.tag.split('}')[-1]
        value = attribute.text
        if key and value:
            out[key] = value
    return out

async def _validate_1(ticket, service, root_url, **kwargs):
    """Validates for CASv1"""
    validation_url = cas_url(
            'validate',
            root_url,
            service=service,
            ticket=ticket,
            **kwargs
            )
    async with aiohttp.ClientSession() as session:
        async with session.get(validation_url) as resp:
            text = await resp.text()
            (valid, user) = text.splitlines()
            if valid == 'yes':
                return {'user': user}
            else:
                return False

async def _validate_2(ticket, service, root_url, **kwargs):
    """Validates for CASv2"""
    validation_url = cas_url(
            'validate',
            root_url,
            service=service,
            ticket=ticket,
            **kwargs
            )
    async with aiohttp.ClientSession() as session:
        async with session.get(validation_url) as resp:
            nsmap = {'cas': 'http://www.yale.edu/tp/cas'}
            text = await resp.text()
            tree = etree.fromstring(text)
            failure = tree.find('cas:authenticationFailure', nsmap)
            if failure is not None:
                # Authentication failed!
                return False
            success = tree.find('cas:authenticationSuccess', nsmap)
            if success is not None:
                attrs = {'user': tree.find('*/cas:user', nsmap).text}
                return attrs
            else:
                # Neither success nor failure?
                raise InvalidCasResponse('Neither success nor failure on login!', resp)


async def _validate_3(ticket, service, root_url, **kwargs):
    """Validates for CASv3"""
    validation_url = cas_url(
            'serviceValidate',
            root_url,
            service=service,
            ticket=ticket,
            **kwargs)
    async with aiohttp.ClientSession() as session:
        async with session.get(validation_url) as resp:
            nsmap = {'cas': 'http://www.yale.edu/tp/cas'}
            text = await resp.text()
            tree = etree.fromstring(text)
            failure = tree.find('cas:authenticationFailure', nsmap)
            if failure is not None:
                # Authentication failed!
                return False
            success = tree.find('cas:authenticationSuccess', nsmap)
            if success is not None:
                attrs = process_attributes(tree)
                user = tree.find('*/cas:user', nsmap)
                attrs['user'] = user.text
                return attrs
            else:
                # Neither success nor failure?
                raise InvalidCasResponse('Neither success nor failure on login!', resp)


async def validate(ticket, service, root_url, version, **kwargs):
    if not isinstance(version, str):
        raise TypeError('CAS version must be passed as a string, not {}'.format(type(version)))
    _validate = {'1': _validate_1,
                 '2': _validate_2,
                 '3': _validate_3}.get(version)

    if _validate is None:
        raise ValueError("Unsupported CAS version {}".format(version))
    return await _validate(ticket, service, root_url, **kwargs)


async def login_handler(request):
    """Handles login requests"""
    ticket = request.GET.get('ticket')
    session = await get_session(request)
    redir = session[SESSION_KEY].get('redir')
    login_route = request.app[APP_KEY]['LOGIN_ROUTE']
    root_url = request.app[APP_KEY]['ROOT_URL']
    on_success = request.app[APP_KEY]['ON_SUCCESS']
    version = request.app[APP_KEY]['VERSION']

    if not (request.scheme and request.host):
        return web.HTTPBadRequest()

    service = parse.urlunsplit(
            (request.scheme, request.host,
             login_route, None, None)
            )

    if ticket:
        attrs = await validate(ticket, service, root_url, version)
        if attrs:
            session[SESSION_KEY] = attrs
            return web.HTTPFound(redir or on_success)
        else:
            return web.HTTPUnauthorized()

    return web.HTTPFound(cas_url('login', root_url, service=service))


async def logout_handler(request):
    """Handles logging out"""
    session = await get_session(request)
    on_logout = request.app[APP_KEY]['ON_LOGOUT']
    del session[SESSION_KEY]
    return web.HTTPFound(on_logout)


def login_required(func, *args, **kwargs):
    """Decorator for handler functions."""
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
