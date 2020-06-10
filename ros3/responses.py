import functools
from typing import Dict, List, Tuple
import hmac
import hashlib
import requests
import xmltodict
import urllib.parse
import datetime
from urllib.parse import parse_qs, urlparse
from requests.auth import AuthBase
from moto.s3.responses import ResponseObject
from moto.s3.models import s3_backend
from moto.s3.utils import parse_region_from_url
from urllib.parse import urlparse, urlencode, parse_qs
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests
from boto3 import session
import os


class Configuration:

    def __init__(self):
        self.access_key = os.environ['ROS3_AWS_ACCESS_KEY_ID']
        self.secret_key = os.environ['ROS3_AWS_SECRET_ACCESS_KEY']
        self.session_token = os.environ.get('ROS3_AWS_SESSION_TOKEN')


config = Configuration()


class AWSV4Sign(AuthBase):
    """
    AWS V4 Request Signer for Requests.
    from https://github.com/jmenga/requests-aws-sign
    """

    def __init__(self):
        sesh = session.Session(
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            aws_session_token=config.session_token
        )
        self.credentials = sesh.get_credentials

    def __call__(self, r):
        url = urlparse(r.url)
        region = parse_region_from_url(r.url)
        path = url.path or '/'
        querystring = ''
        if url.query:
            querystring = '?' + urlencode(parse_qs(url.query, keep_blank_values=True), doseq=True)
        headers = {k.lower(): v for k, v in r.headers.items()}
        location = headers.get('host') or url.netloc
        safe_url = url.scheme + '://' + location.split(':')[0] + path + querystring
        request = AWSRequest(method=r.method.upper(), url=safe_url, data=r.body)
        SigV4Auth(self.credentials, 's3', region).add_auth(request)
        r.headers.update(dict(request.headers.items()))
        return r


def read_s3_wrapper(func):
    @functools.wraps(func)
    def wrapper(self, request: requests.Request, full_url, headers):
        if request.method == "GET":
            auth = AWSV4Sign()
            real_resp = requests.get(full_url, auth=auth)
            real_resp.raise_for_status()
            try:
                fake_resp = func(self, request, full_url, headers)
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                raise e
            dict_response = xmltodict.parse(fake_resp[2])
            print(dict_response)
        else:
            return func(self, request, full_url, headers)

    return wrapper


class S3GetResponse(ResponseObject):

    def __init__(self, backend):
        super().__init__(backend)

    _key_response = read_s3_wrapper(ResponseObject._key_response)

    _bucket_response = read_s3_wrapper(ResponseObject._bucket_response)


S3ResponseInstance = S3GetResponse(s3_backend)
