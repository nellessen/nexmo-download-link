#!/usr/bin/env python
# coding=UTF-8
# Title:       app.py
# Description: 
# Author       David Nellessen <david.nellessen@familo.net>
# Date:        12.01.15
# Note:        
# ==============================================================================

# Import modules
import logging
from urlparse import urlparse
import os
import tornado.ioloop
import tornado.locale
import tornado.web
from tornado.options import define, options
import pygeoip
import toredis
import handler
import nexmoclient
import configuration
from functools import partial



# Define command line parameters.
define('port', default=int(os.environ.get('PORT', 8888)), type=int, help='Run this application on the given port, e.g. 80 (default 8888)')
define('localhostonly', default=bool(os.environ.get('LOCALHOSTONLY', False)), type=bool, help='Application listens on localhost only (default False)')
define('nexmo_api_key', default=str(os.environ.get('NEXMO_API_KEY', '')), type=str, help='Your Nexmo API key')
define('nexmo_api_secret', default=str(os.environ.get('NEXMO_API_SECRET', '')), type=str, help='Your Nexmo API secret')
define('nexmo_domain', default=str(os.environ.get('NEXMO_DOMAIN', 'rest.nexmo.com')), type=str, help='Nexmo API domain (default rest.nexmo.com)')
define('nexmo_endpoint', default=str(os.environ.get('NEXMO_ENDPOINT', 'sms/json')), type=str, help='Nexmo API endpoint (default sms/json)')
define('nexmo_ssl', default=bool(os.environ.get('NEXMO_SSL', False)), type=bool, help='Use SSL for Nexmo API requests (default False)')
define('nexmo_long_virtual_number', default=str(os.environ.get('NEXMO_LONG_VIRTUAL_NUMBER', "")), type=str, help='Use this long virtual number as sender ID for north American recipients only')
define('nexmo_dlr_url', default=str(os.environ.get('NEXMO_DLR_URL', '')), type=str, help='URL that points to this application to receive DLR requests from Nexmo')
define('development_mode', default=bool(os.environ.get('DEVELOPMENT_MODE', False)), type=bool, help='Run application in devel mode (default False)')
define('message', default=str(os.environ.get('MESSAGE', '')), type=str, help='The message for the default message handler')
define('sender', default=str(os.environ.get('SENDER', '')), type=str, help='The sender ID for the default message handler')
define('request_path', default=str(os.environ.get('REQUEST_PATH', '/message/')), type=str, help='The path for the default message handler (default /message/)')
define('limit_amount', default=int(os.environ.get('LIMIT_AMOUNT', 10)), type=int, help='The amount of requests per user per handler allowed (default 10)')
define('limit_expires', default=int(os.environ.get('LIMIT_EXPIRES', 3600)), type=int, help='The time in seconds after that the limit defined by limit_amount expires')
define('guess_country', default=bool(os.environ.get('GUESS_COUNTRY', '')), type=bool, help='If True autocompletes non-internation phone numbers according to the browser locale (default True)')
define('default_country', default=str(os.environ.get('DEFAULT_COUNTRY', 'DE')), type=str, help='The default country for when getting browser locale fails (default DE)')
define('redis_host', default=str(os.environ.get('REDIS_HOST', 'localhost')), type=str, help='Connect with Redis using this port (default localhost)')
define('redis_port', default=int(os.environ.get('REDIS_PORT', 6379)), type=int, help='Connect with Redis using this port (default 6379)')
define('redis_password', default=str(os.environ.get('REDIS_PASSWORD', '')), type=str, help='Redis password')
define('redis_db', default=int(os.environ.get('REDIS_DB', 0)), type=int, help='Work on this Redis DB (default 0)')



class NexmoApplication(tornado.web.Application):
    """
    Main class for this application holding everything together.
    It defines the URL scheme for the API endpoints, configures application
    settings, initializes a tornado.web.Application instance and establishes
    db connections.
    """
    def __init__(self, api_key, api_secret, domain='rest.nexmo.com', endpoint='sms/json',
                 ssl=False, long_virtual_number=None, dlr_url=None, development_mode=False,
                 message=None, sender=None, request_path='/message/', limit_amount=10, limit_expires=3600, guess_country=True,
                 default_country='DE', redis_host='localhost', redis_port=6379, redis_password='', redis_db=0,
                 callback=None, io_loop=None):
        # Handlers defining the URL scheme.
        handlers = [
            (r"/validate_number/", type('ConfiguredNumberValidationHandler', (handler.NumberValidationHandler,),
                                        {'limit_amount': limit_amount, 'limit_expires': limit_expires,
                                         'guess_country': guess_country, 'default_country': default_country})),
        ] + self.parse_handler_from_config(limit_amount, limit_expires, guess_country, default_country)
        if dlr_url:
            handlers += [(urlparse(dlr_url).path, handler.DLRHandler)]
        if message and sender and request_path and not request_path in configuration.SIMPLE_MESSAGE_HANDLERS:
            handlers += [self.get_default_handler(message, sender, request_path, limit_amount, limit_expires,
                                                  guess_country, default_country)]
        logging.debug('Registered handler: {}'.format(handlers))

        # Setup Nexmo client.
        self.nexmo_client = nexmoclient.AsyncNexmoClient(api_key, api_secret, domain, endpoint, ssl,
                                                         long_virtual_number, dlr_url, development_mode)

        # Load GeoIP database.
        self.geo_ip = pygeoip.GeoIP('GeoIP.dat', pygeoip.MEMORY_CACHE)
        self.geo_ipv6 = pygeoip.GeoIP('GeoIPv6.dat', pygeoip.MEMORY_CACHE)

        # Configure application settings.
        settings = {'gzip': True}

        # Call super constructor to initiate a Tornado Application.
        tornado.web.Application.__init__(self, handlers, **settings)

        # Set members for later access.
        self.limit_amount = limit_amount
        self.limit_expires = limit_expires

        # Create db connection.
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_password = redis_password
        self.redis_db = redis_db
        self.io_loop = io_loop
        self.redis = toredis.Client(io_loop=io_loop)
        self.redis_connect(redis_host, redis_port, redis_password, redis_db, callback=callback, io_loop=io_loop)


    def redis_connect(self, redis_host, redis_port, redis_password, redis_db, callback=None, io_loop=None):
        self.redis = toredis.Client(io_loop=io_loop)
        redis_select = partial(self.redis.select, index=redis_db, callback=partial(callback, self))
        if redis_password:
            redis_auth = partial(self.redis.auth, password=redis_password, callback=redis_select)
        else:
            redis_auth = redis_select
        self.redis.connect(host=redis_host, port=redis_port, callback=redis_auth)


    def redis_reconnect(self, callback=None):
        self.redis_connect(self.redis_host, self.redis_port, self.redis_password, self.redis_db, callback, self.io_loop)


    def parse_handler_from_config(self, limit_amount, limit_expires, guess_country, default_country):
        handlers = []
        conf = configuration.SIMPLE_MESSAGE_HANDLERS
        for (k, v) in conf.iteritems():
            v['type'] = type('SimpleMessageHandler' + k,
                             (handler.SimpleMessageHandler,),
                             {'message': v['message'], 'sender': v['sender'],
                              'limit_amount': limit_amount, 'limit_expires': limit_expires,
                              'guess_country': guess_country, 'default_country': default_country})
            handlers.append((k, v['type']))
        return handlers

    def get_default_handler(self, message, sender, path, limit_amount, limit_expires, guess_country, default_country):
            return (path, type('DefaultMessageHandler',
                                           (handler.SimpleMessageHandler,),
                                           {'message': message, 'sender': sender,
                                            'limit_amount': limit_amount, 'limit_expires': limit_expires,
                                            'guess_country': guess_country, 'default_country': default_country}))





def main():
    """
    Main function to start the application. It parses command line arguments,
    initiates application classes, starts the server and Tornado's IOLoop.
    """
    # Parse and validate command line parameters.
    tornado.options.parse_command_line()
    port = tornado.options.options.port
    localhostonly = tornado.options.options.localhostonly
    nexmo_api_key = tornado.options.options.nexmo_api_key
    nexmo_api_secret = tornado.options.options.nexmo_api_secret
    nexmo_domain = tornado.options.options.nexmo_domain
    nexmo_endpoint = tornado.options.options.nexmo_endpoint
    nexmo_ssl = tornado.options.options.nexmo_ssl
    nexmo_long_virtual_number = tornado.options.options.nexmo_long_virtual_number
    nexmo_dlr_url = tornado.options.options.nexmo_dlr_url
    if nexmo_dlr_url:
        logging.error('DLR not yet implemented')
        return
    development_mode = tornado.options.options.development_mode
    message = tornado.options.options.message
    sender = tornado.options.options.sender
    request_path = tornado.options.options.request_path
    limit_amount = tornado.options.options.limit_amount
    limit_expires = tornado.options.options.limit_expires
    guess_country = tornado.options.options.guess_country
    default_country = tornado.options.options.default_country
    redis_host = tornado.options.options.redis_host
    redis_port = tornado.options.options.redis_port
    redis_password = tornado.options.options.redis_password
    redis_db = tornado.options.options.redis_db
    if (message and (not sender or not request_path)) or (sender and (not message or not request_path)):
        logging.error('You must specify message AND sender AND request_path')
        return
    if tornado.options.options.localhostonly:
        address='127.0.0.1'
        address_info = 'Listening to localhost only'
    else:
        address = ''
        address_info = 'Listening to all addresses on all interfaces'

    logging.info('''Starting Nexmo Application with the following parameters:
port: {port}
localhostonly: {localhostonly} ({address_info})
nexmo_api_key: {nexmo_api_key}
nexmo_api_secret: ****
nexmo_domain: {nexmo_domain}
nexmo_endpoint: {nexmo_endpoint}
nexmo_ssl: {nexmo_ssl}
nexmo_long_virtual_number: {nexmo_long_virtual_number}
nexmo_dlr_url: {nexmo_dlr_url}
development_mode: {development_mode}
message: {message}
sender: {sender}
request_path: {request_path}
limit_amount: {limit_amount}
limit_expires: {limit_expires}
guess_country: {guess_country}
default_country: {default_country}
redis_host: {redis_host}
redis_port: {redis_port}
redis_password: {redis_password}
redis_db: {redis_db}

Initialization starting...
    '''.format(port=port, localhostonly=localhostonly, address_info=address_info, nexmo_api_key=nexmo_api_key,
               nexmo_api_secret=nexmo_api_secret, nexmo_domain=nexmo_domain, nexmo_endpoint=nexmo_endpoint,
               nexmo_ssl=nexmo_ssl, nexmo_long_virtual_number=nexmo_long_virtual_number, nexmo_dlr_url=nexmo_dlr_url,
               development_mode=development_mode, message=message, sender=sender, request_path=request_path, limit_amount=limit_amount,
               limit_expires=limit_expires, guess_country=guess_country, default_country=default_country,
               redis_host=redis_host, redis_port=redis_port,
               redis_password={True: 'Yes', False: 'No password given'}.get(bool(redis_password)), redis_db=redis_db))

    # Start application an listen on given port.
    def on_ready_callback(app, status):
        logging.info('...Application initialization completed. Start listening on port {}'.format(port))
        app.listen(port, address=address, xheaders=True)
    app = NexmoApplication(api_key=nexmo_api_key,
               api_secret=nexmo_api_secret, domain=nexmo_domain, endpoint=nexmo_endpoint,
               ssl=nexmo_ssl, long_virtual_number=nexmo_long_virtual_number, dlr_url=nexmo_dlr_url,
               development_mode=development_mode, message=message, sender=sender, request_path=request_path, limit_amount=limit_amount,
               limit_expires=limit_expires, guess_country=guess_country, default_country=default_country,
               redis_host=redis_host, redis_port=redis_port, redis_password=redis_password, redis_db=redis_db,
               callback=on_ready_callback)
    tornado.ioloop.IOLoop.instance().start()


# Run main method if script is run from command line.
if __name__ == "__main__":
    main()
