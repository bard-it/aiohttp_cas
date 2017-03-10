"""Location of app and session keys, and a small utility function for
building CAS urls"""
from urllib import parse

APP_KEY = 'aiohttp_cas'
SESSION_KEY = 'aiohttp_cas'


def cas_url(kind, root_url, **kwargs):
    """Builds a URL for CAS

    :param kind str: what to join to the root url
    :param root_url str: the root url
    :param \**kwargs: passed in as URL parameters
    """
    args = parse.urlencode(kwargs)
    url = parse.urljoin(root_url, kind)

    return url + '?' + args
