"""Validating functions for CAS versions 1, 2, and 3"""

from aiohttp import ClientSession
from lxml import etree
from .utils import cas_url
from .log import log


class InvalidCasResponse(Exception):
    def __init__(self, message, resp):
        super().__init__(message)
        self.resp = resp


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


async def _validate_1(resp):
    """Validates for CASv1"""
    text = await resp.text()
    # "Parse" the response
    (valid, user) = text.splitlines()
    if valid == 'yes':
        return {'user': user}
    else:
        return False


async def _validate_2(resp):
    """Validates for CASv2"""
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


async def _validate_3(resp):
    """Validates for CASv3"""
    nsmap = {'cas': 'http://www.yale.edu/tp/cas'}
    text = await resp.text()
    try:
        tree = etree.fromstring(text)
    except:
        raise InvalidCasResponse("Received invalid XML in response!", resp)
    failure = tree.find('cas:authenticationFailure', nsmap)
    if failure is not None:
        # Authentication failed!
        log.info('Authentication failure: {}'.format(failure.text))
        return False
    success = tree.find('cas:authenticationSuccess', nsmap)
    if success is not None:
        attrs = process_attributes(tree)
        user = tree.find('*/cas:user', nsmap)
        attrs['user'] = user.text
        return attrs
    else:
        # Neither success nor failure?
        raise InvalidCasResponse("Neither success nor failure on login!", resp)


async def validate(ticket, service, root_url, version, **kwargs):
    """Validates the ticket according to the version of the CAS protocol supplied.

    :param ticket str: The ticket id.
    :param service str: The application the client is trying to access
    :param root_url str: The URL for the CAS service
    :param version str: The version of the CAS service
    :param \*kwargs: Additional parameters passed to the validate function.
                     (which, in turn, is passed to the CAS url builder)
    """
    log.info("Attempting to validate ticket...")
    if not isinstance(version, str):
        raise TypeError("CAS version must be passed as a string, not {}"
                        .format(type(version)))
    log.info("Validating ticket {}".format(ticket))
    if version == '1':
        kind = 'validate'
        _validate = _validate_1
    elif version == '2':
        kind = 'serviceValidate'
        _validate = _validate_2
    elif version == '3':
        kind = 'p3/serviceValidate'
        _validate = _validate_3
    else:
        raise ValueError("Unsupported CAS version {}".format(version))

    validation_url = cas_url(
            kind,
            root_url,
            service=service,
            ticket=ticket,
            **kwargs
            )
    log.info("Requesting validation URL {}".format(validation_url))
    async with ClientSession() as session:
        async with session.get(validation_url) as resp:
            return await _validate(resp)
