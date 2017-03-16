.. aiohttp-cas documentation master file, created by
   sphinx-quickstart on Wed Mar 15 15:43:53 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiohttp-cas documentation
=========================

aiohttp-cas adds support for the Central Authentication Service protocol to your
aiohttp.web thingamabob.

Example usage
-----

.. codeblock:: python
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

.. toctree::
   :maxdepth: 2
   :caption: Contents:

.. automodule:: aiohttp_cas
    :members: setup, login_required
