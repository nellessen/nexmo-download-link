#!/usr/bin/env python
# coding=UTF-8
# Title:       handler.py
# Description: This file contains all tornado.web.RequestHandler classes used in this application
# Author       David Nellessen <david.nellessen@familo.net>
# Date:        12.01.15
# Note:        
# ==============================================================================

# Import modules
from tornado import web, gen,  escape
from tornado.escape import utf8
import logging
import phonenumbers
import pygeoip
from tornado.iostream import StreamClosedError


class BaseHandler(web.RequestHandler):
    """
    A base handler providing localization features, phone number validation
    and formation as well as use of service limitation based on IP addresses.
    It also implements support for JSONP (for cross-domain requests).
    """
    guess_country = True
    default_country = 'DE'

    def __init__(self, application, request, **kwargs):
        super(BaseHandler, self).__init__(application, request, **kwargs)
        self.counter = {}


    def write(self, chunk):
        """
        Overwrites the default write method to support tornado.webJSONP.
        """
        if self._finished:
            raise RuntimeError("Cannot write() after finish().  May be caused "
                               "by using async operations without the "
                               "@asynchronous decorator.")
        if isinstance(chunk, dict):
            chunk = escape.json_encode(chunk)
            self.set_header("Content-Type", "application/json; charset=UTF-8")
            callback = self.get_argument('callback', None)
            if callback:
                chunk = callback + '(' + chunk + ');'
        chunk = utf8(chunk)
        self._write_buffer.append(chunk)


    def get_browser_locale_code(self):
        """
        Determines the user's locale from ``Accept-Language`` header.
        This is similar to tornado.web.get_browser_locale except it
        returns the code and not a Locale instance. Also this will return
        a result weather a translation for this language was loaded or not.

        See http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.4
        """
        if "Accept-Language" in self.request.headers:
            languages = self.request.headers["Accept-Language"].split(",")
            locales = []
            for language in languages:
                parts = language.strip().split(";")
                if len(parts) > 1 and parts[1].startswith("q="):
                    try:
                        score = float(parts[1][2:])
                    except (ValueError, TypeError):
                        score = 0.0
                else:
                    score = 1.0
                locales.append((parts[0], score))
            if locales:
                locales.sort(key=lambda pair: pair[1], reverse=True)
                logging.debug(locales)
                codes = [l[0] for l in locales]
                return codes[0]
        return self.__class__.default_country


    def get_user_country_by_ip(self):
        """
        Determines the user's country by his IP-address. This will return
        the country code or None if not found.
        """
        try:
            country = self.application.geo_ip.country_code_by_addr(
                                                    self.request.remote_ip)
        except pygeoip.GeoIPError:
            try:
                country = self.application.geo_ipv6.country_code_by_addr(
                                                     self.request.remote_ip)
            except pygeoip.GeoIPError:
                pass
        if not country:
            logging.warning('Could not locate country for ' + self.request.remote_ip)
            return None
        else:
            logging.debug('Determined country by IP address: ' + country)
            return country


    def parse_phonenumber(self, number):
        """
        Validates and parses a phonenumber. It will return a
        phone number object or False if parsing failed.

        If the phone number is not given in full international notion the
        parameter the country will be guesses if the class attribute guess_country
        is True. Guessing will be done as follows:
        1. If a query string parameter 'country' is given as a country code
        (i.e. 'US', 'DE', ...) it will be used.
        2. If no parameter country is given the country will be determined by
        the remote IP address.
        3. Otherwise the country determined by the request header
        Accept-Language will be used.
        4. As a fall-back the classes default_country attribute will be used.
        """
        try:
            return phonenumbers.parse(number)
        except:
            # Get the country code to use for phone number parsing.
            if self.__class__.guess_country:
                country_code = self.get_argument('country', None)
                if country_code == None:
                    country_code = self.get_user_country_by_ip()
                if country_code == None:
                    code = self.get_browser_locale_code().replace('-', '_')
                    parts = code.split('_')
                    if len(parts) > 1: country_code = parts[1]
                if country_code == None: country_code = self.__class__.default_country
                country_code = country_code.upper()
                logging.debug("Final country code: " + country_code)
            else:
                country_code = self.__class__.default_country
            # Parse the phone number into international notion.
            try:
                number_parsed = phonenumbers.parse(number, country_code)
                return number_parsed
            except:
                return False


    @gen.coroutine
    def limit_call(self, chash=None, amount=2, expire=10):
        """
        Use this function to limit user requests. Returns True if this function
        was called less then 'amount' times in the last 'expire' seconds with
        the same value 'chash' and the same remote IP address or False
        otherwise.
        """
        key = 'limit_call_' + chash + '_' + self.request.remote_ip
        redis = self.application.redis
        try:
            current_value = yield gen.Task(redis.get, key)
        except StreamClosedError:
            yield gen.Task(self.application.redis_reconnect)
            redis = self.application.redis
            current_value = yield gen.Task(redis.get, key)
        if current_value != None and int(current_value) >= amount:
            logging.info('Call Limitation acceded: ' + key)
            raise gen.Return(False)
        else:
            yield gen.Task(redis.incr, key)
            if not current_value: yield gen.Task(redis.expire, key, expire)
            raise gen.Return(True)


class DLRHandler(web.RequestHandler):
    """
    Handles delivery receipts.
    """
    def get(self):
        """
        All delivery receipts will be send as HTTP-GET requests.
        """
        # TODO: Parse request!
        logging.info('Received DLR. Not yet parsed though.')



class NumberValidationHandler(BaseHandler):
    """
    Validates a phone number.
    """
    limit_amount = 10
    limit_expires = 3600

    @gen.coroutine
    def get(self):
        """
        Validates a phone number given as the query string parameter 'number'.

        If the phone number is not given in full international notion the
        parameter the country will be guesses if the class attribute guess_country
        is True. Guessing will be done as follows:
        1. If a query string parameter 'country' is given as a country code
        (i.e. 'US', 'DE', ...) it will be used.
        2. If no parameter country is given the country will be determined by
        the remote IP address.
        3. Otherwise the country determined by the request header
        Accept-Language will be used.
        4. As a fall-back the classes attribute default_country will be used.
        """
        # Limit calls.
        if self.limit_amount and not (yield self.limit_call('number_validation', self.limit_amount, self.limit_expires)):
            #raise web.HTTPError(403, 'Number Validation request limit acceded')
            self.finish({'status': 'error',
                         'error': 'limit_acceded'})
            return

        # Decode request's query string parameters.
        number = self.get_argument('number', None)
        if not number:
            self.finish({'status': 'error',
                         'error': 'number_missing'})
            return
        logging.debug('Received number {} for validation'.format(number))
        numberobj = self.parse_phonenumber(number)
        if numberobj:
            number = phonenumbers.format_number(numberobj,
                                   phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        else: number = False
        self.finish({'status': 'ok',
                     'number': number})



class SimpleMessageHandler(BaseHandler):
    message = 'This is an Example Message'
    sender = 'Put a sender title or number here'
    limit_amount = 10
    limit_expires = 3600

    @gen.coroutine
    def get(self):
        # Limit calls.
        if self.limit_amount and not (yield (self.limit_call('example_handler', self.limit_amount, self.limit_expires))):
            self.finish({'status': 'error',
                         'error': 'limit_acceded'})
            return

        # Get receiver's phone number as 'receiver' parameter.
        receiver = self.get_argument('receiver', None)
        if not receiver:
            self.finish({'status': 'error',
                         'error': 'receiver_missing'})
            return

        # Parse the given phone number.
        receiverobj = self.parse_phonenumber(receiver)
        if not receiverobj:
            self.finish({'status': 'error',
                         'error': 'receiver_validation'})
            return

        # Format numbers for processing and displaying.
        receiver_nice = phonenumbers.format_number(receiverobj,
                                   phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        receiver = phonenumbers.format_number(receiverobj,
                                   phonenumbers.PhoneNumberFormat.E164)

        # Send message to receiver.
        result = yield gen.Task(self.application.nexmo_client.send_message,
                                self.__class__.sender, receiver,
                                self.__class__.message)

        # Process result.
        if result: self.finish({'status': 'ok',
                                'message': 'Message sent',
                                'number': receiver_nice})
        else: self.finish({'status': 'error',
                           'error': 'nexmo_error',
                           'message': 'Nexmo Service Error',
                           'number': receiver_nice})

