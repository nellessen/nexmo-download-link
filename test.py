#!/usr/bin/env python
# coding=UTF-8
# Title:       test.py
# Description: Tests for this project.
# Author       David Nellessen <david.nellessen@familo.net>
# Date:        12.01.15
# Note:        
# ==============================================================================

# Import modules
from tornado.testing import AsyncHTTPTestCase
from tornado.httpclient import HTTPRequest
from app import NexmoApplication
import json
import redis as redis_driver
import configuration

# Sandbox API credentials (see https://labs.nexmo.com/).
SANDBOX_API_KEY = 'SD_98659'
SANDBOX_API_SECRET = 'PS_34729'
SANDBOX_DOMAIN = 'rest-sandbox.nexmo.com'

# Your Redis configuration.
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_PASSWORD = ''
REDIS_DB = 0


def connect_redis_py(redis_host=REDIS_HOST, redis_port=REDIS_PORT, redis_password=REDIS_PASSWORD, redis_db=REDIS_DB):
    return redis_driver.StrictRedis(host=redis_host, port=redis_port, password=redis_password, db=redis_db)


class BaseTest(AsyncHTTPTestCase):

    limit_amount = 5
    limit_expires= 1800
    api_key=SANDBOX_API_KEY
    api_secret=SANDBOX_API_SECRET
    domain=SANDBOX_DOMAIN

    def get_app(self):
        def finish(app, status):
            self.stop()
        app = NexmoApplication(api_key=self.api_key, api_secret=self.api_secret, domain=self.domain,
                               callback=finish, io_loop=self.io_loop,
                               limit_amount=self.limit_amount, limit_expires=self.limit_expires,
                               message='Test message', sender='Test Sender')
        self.wait()
        return app

    def reset_limits(self):
        for key in self.redis.keys('limit_call_*'):
            self.redis.delete(key)

    def setUp(self):
        super(BaseTest, self).setUp()
        # Connect to redis.
        self.redis = connect_redis_py()
        self.reset_limits()

    def test_configuration(self):
        # Test if configuration is correct.
        self.assertEqual(self.limit_amount, self._app.limit_amount)
        self.assertEqual(self.limit_expires, self._app.limit_expires)

    def assert_json_response(self, response, result={}):
        self.assertIn('Content-Type', response.headers)
        self.assertIn('json', response.headers['Content-Type'])
        body = json.loads(response.body)
        for key, value in result.items():
            self.assertIn(key, body)
            self.assertEqual(value, body[key])

    def assert_jsonp_response(self, response, result={}, callback='callback'):
        self.assertIn('Content-Type', response.headers)
        self.assertIn('json', response.headers['Content-Type'])
        body = json.loads(response.body[9:-2])
        for key, value in result.items():
            self.assertIn(key, body)
            self.assertEqual(value, body[key])




class LimitTestCase(BaseTest):
    """Tests request limitations.
    """

    limit_amount = 5
    limit_expires= 1800

    def test_validate_number_limits(self):
        """Tests if the validation limits for /validate_number/ are taking into account.
        """
        # Reset limits first.
        self.reset_limits()

        # Request as often as allowed.
        for i in range(0, self._app.limit_amount):
            self.http_client.fetch(self.get_url('/validate_number/?number=%2B49176123456'), self.stop)
            response = self.wait()
            self.assert_json_response(response,  {'status': 'ok'})

        # Request again and expect error.
        self.http_client.fetch(self.get_url('/validate_number/?number=%2B49176123456'), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'error', "error": "limit_acceded"})

    def test_defaultmessage_limits(self):
        """Tests if the validation limits for /defaultmessage/ are taking into account.
        """
        # Reset limits first.
        self.reset_limits()

        # Request as often as allowed.
        for i in range(0, self._app.limit_amount):
            self.http_client.fetch(self.get_url('/message/?receiver=%2B49176123456'), self.stop)
            response = self.wait()
            self.assert_json_response(response,  {'status': 'ok'})

        # Request again and expect error.
        self.http_client.fetch(self.get_url('/message/?receiver=%2B49176123456'), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'error', "error": "limit_acceded"})



class DefaultMessageHandlerTestCase(BaseTest):
    """Tests the default message handler.
    """

    limit_amount = 500
    limit_expires= 1800
    path = '/message/'

    def test_send_message(self):
        # Test a successful request.
        self.http_client.fetch(self.get_url(self.path + '?receiver=%2B49176123456'), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'ok', 'message': 'Message sent', 'number': '+49 176123456'})

    def test_missing_receiver(self):
        # Test missing receiver.
        self.http_client.fetch(self.get_url(self.path), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'error', 'error': 'receiver_missing'})

    def test_invalid_phone_number(self):
        # Provide text as receiver.
        self.http_client.fetch(self.get_url(self.path + '?receiver=abcdefg'), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'error', 'error': 'receiver_validation'})

    def test_phonenumber_normalization(self):
        # Test if phone number is guessed correctly by browser language.
        request = HTTPRequest(self.get_url(self.path + '?receiver=0176123456'), headers={'Accept-Language': 'DE'})
        self.http_client.fetch(request, self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'ok', 'message': 'Message sent', 'number': '+49 176123456'})

    def test_jsonp(self):
        # Tests jsonp requests.
        self.http_client.fetch(self.get_url(self.path + '?receiver=%2B49176123456&callback=callback'), self.stop)
        response = self.wait()
        self.assert_jsonp_response(response,  {'status': 'ok', 'message': 'Message sent', 'number': '+49 176123456'})




class ErrorTestCase(BaseTest):
    """Tests error handling.
    """
    api_secret = 'wrong api key'

    def test_nexmo_error(self):
        # Test API response when Nexmo API response with errors.
        self.http_client.fetch(self.get_url('/message/?receiver=%2B49176123456'), self.stop)
        response = self.wait()
        self.assert_json_response(response,  {'status': 'error', 'error': 'nexmo_error'})

    def test_404(self):
        self.http_client.fetch(self.get_url('/WRONGURL/?receiver=%2B49176123456'), self.stop)
        response = self.wait()
        self.assertEqual(404, response.code)



class ConfigurationHandlerTestCase(DefaultMessageHandlerTestCase):
    """Test handlers defined via configuration file.
    """
    path = '/configurationhandler/'

    def setUp(self):
        configuration.SIMPLE_MESSAGE_HANDLERS['/configurationhandler/'] = {
            'message': 'Message by configuration handler',
            'sender': 'Sender 2'
        }
        super(ConfigurationHandlerTestCase, self).setUp()


