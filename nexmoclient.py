#!/usr/bin/env python
# coding=UTF-8
# Title:       nexmoclient.py
# Description: A asynchronous client for Nexmo's SMS API for Tornado applications.
# Author       David Nellessen <david.nellessen@familo.net>
# Date:        12.01.15
# Note:        
# ==============================================================================

# Import modules
import json
import logging
import phonenumbers
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.httputil import url_concat


class AsyncNexmoClient(object):
    def __init__(self, api_key, api_secret, domain='rest.nexmo.com', endpoint='sms/json',
                 ssl=False, long_virtual_number=None, dlr_url=None, development_mode=False):
        """
        :param dlr_url: when using this parameter a callback-url has to be defined on
        `https://dashboard.nexmo.com/private/settings`
        :return:
        """
        self.http_client = AsyncHTTPClient()
        self.api_key = api_key
        self.api_secret = api_secret
        self.domain = domain
        self.endpoint = endpoint
        self.ssl = ssl
        self.long_virtual_number = long_virtual_number
        self.dlr_url = dlr_url
        self.development_mode = development_mode

    def assamble_url(self, sender, to, text):
        """
        Assambles the url for sending a message. This will url encode
        all parameters.
        """
        phonenumber = phonenumbers.parse(to)
        # Nexmo seems to dislike escaped "+" so it's replaced with a double zero
        to = "00" + phonenumbers.format_number(phonenumber, phonenumbers.PhoneNumberFormat.E164)[1:]
        # Replace sender for north american numbers.
        # See sender sestrictions: https://help.nexmo.com/hc/en-us/articles/204017023-USA-Direct-route-
        if self.long_virtual_number and to[0:3] == '001':
            sender = self.long_virtual_number
        params = {'api_key': self.api_key,
                  'api_secret': self.api_secret,
                  'from': sender,
                  'to': to,
                  'text': text.encode('utf-8', 'replace'),
                  'type': 'text'}
        if self.dlr_url:
            params['status-report-req'] = 1

        if self.ssl:
            protocol = 'https'
        else:
            protocol = 'http'
        url = "{protocol}://{domain}/{endpoint}".format(protocol=protocol, domain=self.domain, endpoint=self.endpoint)
        url = url_concat(url, params)
        return url

    def send_message(self, sender, to, text, callback=None):
        """
        Sends a message through the Nexmo Gateway.
        """
        url = self.assamble_url(sender, to, text)
        logging.debug('Requesting Nexmo service: ' + url)
        request = HTTPRequest(url=url, method='GET')

        # Define response callback.
        def handle_request(response):
            if response.error:
                logging.warning("Request failed: " + str(response.error))
                if callback:
                    callback(False)
                    return

            try:
                json_response = json.loads(response.body)
            except ValueError as exc:
                logging.error("response was not json", exc_info=1)
                callback(False)
                return

            message_was_send = []
            try:
                for message in json_response['messages']:
                    if message['status'] != "0":
                        message_was_send.append(False)
                    else:
                        message_was_send.append(True)

                if len(message_was_send) > 1:
                    logging.warn("message was sent as multipart in {} parts".format(len(message_was_send)))

                if not all(message_was_send):
                    logging.error("sending of {} messages failed. Error message: {}".format(len(filter(lambda x: x is False, message_was_send)), json_response))
                    callback(False)
                    return

            except ValueError:
                logging.error("response is unexpected", exc_info=True)
                callback(False)
                return
            callback(True)

        if self.development_mode:
            # in development mode no requests are send everything is a (huge) success
            callback(True)
        else:
            self.http_client.fetch(request, handle_request)


class SMSSender(object):
    """
    Singleton called by `.smssender.get_sms_sender`
    """
    __sms_instance = None

    def __new__(cls, override_develmode=False):
        if SMSSender.__sms_instance is None:
            from conf.settings import NEXMO
            if override_develmode:
                DEVEL_MODE = False
            else:
                from conf.settings import DEVEL_MODE
            SMSSender.__sms_instance = AsyncNexmoClient(NEXMO['api_key'], NEXMO['api_secret'], ssl=NEXMO['ssl'],
                                                        long_virtual_number=NEXMO['long-virtual-number'], dlr_url=None,
                                                        development_mode=DEVEL_MODE)
        return SMSSender.__sms_instance

    @classmethod
    def destroy_instance(cls):
        SMSSender.__sms_instance = None