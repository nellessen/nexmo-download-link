Nexmo Messaging Proxy
===================
A proxy for Nexmo's SMS API for implementing custom messaging services like a download link service for your website.

Author: David Nellessen (https://github.com/nellessen/) <br />
License: [MIT License](LICENSE) <br />


[Nexmo SMS](https://www.nexmo.com/messaging/) is a SMS service. This application provides a very simple,
JSON-based web-API for accessing the [Nexmo API](https://www.nexmo.com/messaging/) from public accessible web sites
or web applications. A typical use-case for this Proxy is a website that provides a *send download link* form.


Features
--------
There are a couple of nice feature worth mentioning. First of all you can
regard this package as a framework for building messaging application
using the Nexmo SMS service. The [Default Message Handler](#defining-default-message-handler) is just a shortcut
for quickly implementing a standard use-case where you want to define a
static message and sender ID and get an API end-point that sends this message
to a phone number given as query string parameter. But you can also implement
more complex handlers. Either way you will get several nice features:

### Phone number validation and normalization
The phone numbers will be validated and normalized. If the user does not
provide an international phone number the country of the user will be
guessed by his IP address with fallbacks to the browser locale or a default
country (you can turn this of in *--guess_country*). The geo-IP
features works in this app without external services needed. In addition
to the handler you configure there is a validation handler that validates
phone numbers the same way. You can use it it if you want to check a number
before sending a message. It is available under the path */validate_number/*.
You must provide the phone number to validate as the query string parameter
*number*.

TODO: Detailed documentation of the validation service.

### Request limitation
To avoid unwanted costs there is a default limitation of requests on an
IP base for the messaging service and for the validation
service (10 requests per hour).
This limitation uses Redis to count requests. This is very fast with a minimum
of memory needed. Another nice side-effect is that you can run multiple
instances of this application on the same machine and the limits will still
work as intended.

### Cross-Domain Requests
If you want to host the service on a domain separate from where your website
lives, you will face the same-origin-policy issue.
Therefore this application supports JSONP in addition to JSON. So if you are using
jQuery set `dataType: 'jsonp'` instead of `dataType: 'json'` in Ajax requests
and you won't run into same-origin issues.

### Scalability
This application is based on [Tornado](http://www.tornadoweb.org/) which uses an event-driven,
non-blocking-IO architecture which handles a lot of requests.
You can use a setup with nginx as a proxy and start multiple instance
of this application which will multiply the performance. Syncing and
persisting the request limits is done using Redis.


Example
-------
Open the **example.html** for an example how to use a service.



Installation and Configuration
-----------------------------

### Requirements
First of all you need Python and Redis on your machine running this application.
In addition install the following packages (assuming you are using PIP):
```Bash
pip install tornado, toredis, redis, pygeoip, phonenumbers
git clone https://github.com/nellessen/nexmo-download-link.git
cd nexmo-download-link
```


### Running the Application
Run the following command from within the directory where this file is located
to start a http server listening on port 80:
```Bash
python app.py --port=80
```


### Configuration
You can configure the app via parameters or with environment vars.
The later method is recommended because it hides sensible information
like API secret or Redis password from the process list. Any of the
following parameters can be used as an environment var if written in
upper case.


|  Parameter    | Description |
|---------------|-------------|
|  --message            | The message for the default message handler |
|  --sender             | The sender ID for the default message handler |
|  --request_path       | The path for the default message handler (default /message/) |
|  --port               | Run this application on the given port, e.g. 80 (default 8888) (default 8888) |
|  --localhostonly      | Application listens on localhost only (default False) (default False) |
|  --guess_country      | If True autocompletes non-internation phone numbers according to the browser locale (default True) (default False) |
|  --default_country    | The default country when getting browser locale fails (default DE) (default DE) |
|  --limit_amount       | The amount of requests per user per handler allowed (default 10) (default 10) |
|  --limit_expires      | The time in seconds after that the limit defined by limit_amount expires (default 3600) |
|  --nexmo_api_key      | Your Nexmo API key |
|  --nexmo_api_secret   | Your Nexmo API secret |
|  --nexmo_dlr_url      | URL that points to this application to receive DLR requests from Nexmo |
|  --nexmo_domain       | Nexmo API domain (default rest.nexmo.com) (default rest.nexmo.com) |
|  --nexmo_endpoint     |  Nexmo API endpoint (default sms/json) (default sms/json) |
|  --nexmo_long_virtual_number | Use this long virtual number as sender ID for north American recipients only |
|  --nexmo_ssl          | Use SSL for Nexmo API requests (default False) (default False) |
|  --redis_db           | Work on this Redis DB (default 0) (default 0) |
|  --redis_host         | Connect with Redis using this port (default localhost) (default localhost) |
|  --redis_password     | Redis password |
|  --redis_port         | Connect with Redis using this port (default 6379) (default 6379) |
|  --development_mode   | Run application in devel mode (default False) (default False) |
|  --help               | show this help information |
|  --log_file_max_size  | max size of log files before rollover (default 100000000) |
|  --log_file_num_backups | number of log files to keep (default 10) |
|  --log_file_prefix=PATH | Path prefix for log files. Note that if you are running multiple tornado processes, log_file_prefix must be different for each of them (e.g. include the port number) |
|  --log_to_stderr      | Send log output to stderr (colorized if possible). By default use stderr if --log_file_prefix is not set and no other logging is configured. |
|  --logging | Set the Python log level. If 'none', tornado won't touch the logging configuration. (default info) |



Defining Default Message Handler
-------------------------------
A default message handler can be defined with environment vars. Run the app as follows
to define a simple message handler with *Welcome to Example* as the message sent with
*Awesome Sender* as sender ID. You need to provide your Nexmo API credentials:
```Python
NEXMO_API_KEY="***" NEXMO_API_SECRET="***" SENDER="Awesome Sender" MESSAGE="Welcome to Example" python app.py
```
This will create a message service API as follows:

### Example Request
*Request URL*
```
http://1.2.3.4:8888/message/
```

*Query String Parameters (URL-encoded)*
```
receiver: 017612345678
```

*Request Headers*
```
Request Method: GET
Accept: application/json
Accept-Language:en-US,en;q=0.8,de;q=0.6
Content-Type:application/json
```

### Example Response

*Response Headers*
```
Status Code: 200
Content-Type: application/json; charset=UTF-8
...
```
**Status Code**:
- 200: Request succeeded. Does not mean sending succeeded (see below).
- 404: You have requested a wrong URL
- 500: Server crashed

*Response Body*
```javascript
{
    "status": "ok",
    "message": "Message sent",
    "number": "+49 176 12345678"
}
```
The above response indicates that the request was successful and that the
Nexmo API call was successful. It does not guarantee message delivery though.
It might take some time, depending on the Nexmo Gateway. You can activate
delivery reports though (not yet implemented!).

**No receiver phone number**:
In case the no query string parameter *receiver* is sent you will receive the
following response body:
 ```javascript
{
    "status": "error",
    "error": "receiver_missing"
}
```

**Invalid phone number**:
In case the phone number provided is invalid you will receive the following
response body:
 ```javascript
{
    "status": "error",
    "error": "receiver_validation"
}
```

**Request limit acceded**:
In case you have performed to many requests from the same IP you will receive
the following response body:
 ```javascript
{
    "status": "error",
    "error": "limit_acceded"
}
```

**Nexmo Error**:
If the Nexmo service response with an error you will receive the following
response body:
 ```javascript
{
    "status":"error",
    "error":"nexmo_error",
    "message": "Nexmo Service Error",
    "number":"+49 176 49559259"
}
```
This happens in case the Nexmo Server has issues or your account data configured
is wrong or if the remote service response with an error for any other reason.

If everything is OK a message will be send to *+49 176 12345678*.