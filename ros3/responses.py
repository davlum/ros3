import os
import logging
import functools
from typing import Callable
import requests
from requests.auth import AuthBase
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from boto3 import session
from moto.s3.responses import ResponseObject
from moto.s3.models import s3_backend
from urllib.parse import urlparse, parse_qs, ParseResult, urlencode


class Configuration:

    def __init__(self):
        self.endpoint_url = os.environ.get('ROS3_S3_ENDPOINT_URL')
        path_to_whitelist = os.environ.get('ROS3_PATH_TO_WHITELIST')
        if path_to_whitelist is None:
            self.whitelist = None
        else:
            self.whitelist = self.read_whitelist(path_to_whitelist)
        logging.debug("WHITELIST IS %s", self.whitelist)

    @staticmethod
    def read_whitelist(path):
        with open(path) as f:
            return [x.strip() for x in f.readlines()]


config = Configuration()


def extract_bucket_from_path(path) -> (str, str):
    paths = path.split('/')
    filtered = [p for p in paths if p]
    return filtered[0], '/' + '/'.join(filtered[1:])


def get_host_and_path(parsed_url: ParseResult) -> (str, str):
    bucket, path = extract_bucket_from_path(parsed_url.path)
    if config.whitelist is not None and bucket not in config.whitelist:
        raise ValueError("Bucket is not whitelisted, will not sent requests to `s3://%s`", bucket)
    return f'https://{bucket}.s3.amazonaws.com', path


def create_url(parsed_url: ParseResult) -> str:
    querystring = ''
    host, path = get_host_and_path(parsed_url)
    if parsed_url.query:
        querystring = '?' + urlencode(parse_qs(parsed_url.query, keep_blank_values=True), doseq=True)
    if config.endpoint_url:
        return config.endpoint_url + parsed_url.path + querystring
    else:
        return host + path + querystring


class S3V4Sign(AuthBase):
    """
    AWS V4 Request Signer for Requests.
    from https://github.com/jmenga/requests-aws-sign
    """

    def __init__(self, parsed_url: ParseResult):
        sesh = session.Session()
        self.credentials = sesh.get_credentials()
        self.region = sesh.region_name
        self.url = create_url(parsed_url)
        logging.exception("Redirected URl is %s", self.url)

    def __call__(self, request: AWSRequest):
        # Method hard coded to 'GET' as this prevents making accidental 'POSTS'
        aws_request = AWSRequest(method='GET', url=self.url, data=request.body)
        S3SigV4Auth(self.credentials, 's3', self.region).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers.items()))
        return request


def mirror_req_to_s3(request: requests.Request) -> (int, dict, str):
    """
    :param request: The request from the client to be mirrored to S3
    :return: A response of form (status_code, headers, content)

    This method will throw if the underlying request to S3 throws.

    We assume requests to ros3 are S3 path-style requests of form;

        https://s3.Region.amazonaws.com/bucket-name/key-name

    The request is redirect using the bucket which is the first component of the path
    to the virtual hosted style which is of form;

        https://bucket-name.s3.Region.amazonaws.com/key-name

    If clients make request to the ros3 service using virtual hosted-style requests
    it will not work out well.

    More documentation can be found about this here;
    https://docs.aws.amazon.com/AmazonS3/latest/dev/VirtualHosting.html
    """
    parsed_url = urlparse(request.url)
    auth = S3V4Sign(parsed_url)
    real_resp = requests.get(auth.url, auth=auth)
    real_resp.raise_for_status()
    # NOTE: Returning {} as the returned headers, essentially dropping
    # all of the response headers. Maybe filter desired headers?
    return real_resp.status_code, {}, real_resp.content


def read_s3_wrapper(func: Callable) -> Callable:
    """
    :param func: ResponseObject._<resource>_response method
    :return: Wrapped ResponseObject._<resource>_response method

    Qu'est ce que fuck

    This will attempt a normal read from mock S3, and if that throws and exception
    it will try to read from the real S3. If that fails, return the error from
    the request to the mock S3. Reads should be redirected to the real S3 if the
    mock S3 returns no content and the bucket is on bucket `whitelist`.
    """
    @functools.wraps(func)
    def wrapper(self, request: requests.Request, full_url, headers):
        if request.method == "GET":
            try:
                return func(self, request, full_url, headers)
            except Exception as e:
                try:
                    return mirror_req_to_s3(request)
                except Exception as other_e:
                    logging.exception(other_e)
                    raise e
        else:
            return func(self, request, full_url, headers)
    return wrapper


class S3GetResponse(ResponseObject):

    def __init__(self, backend):
        super().__init__(backend)

    _key_response = read_s3_wrapper(ResponseObject._key_response)

    _bucket_response = read_s3_wrapper(ResponseObject._bucket_response)


S3ResponseInstance = S3GetResponse(s3_backend)
