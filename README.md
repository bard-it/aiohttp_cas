# aiohttp_cas
CAS authentication support for aiohttp. Work in progress. Will probably eat your dog and then authenticate it into your payroll system.

## Installation
Not in PyPI yet. Download all this stuff then do
```python setup.py install```

## Use
```
from aiohttp import web
from aiohttp_session import setup as session_setup
from aiohttp_cas import login_required
from aiohttp_cas import setup as cas_setup

async def index(request):
    return web.Response(text='Hello!')

@login_required
async def secret(request):
    return web.Response(text='Shhh! Don\'t tell anyone!')

def make_app():
    app = web.Application()
    # Set up aiohttp_session however you like
    cas_setup(app, 'your_cas_host_here', 'your_cas_version_here')
    app.router.add_route('GET', '/', index)
    app.router.add_route('GET', '/secret', secret)
    return app

web.run_app(make_app())
```
