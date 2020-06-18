import os
import logging
import functools
from typing import Callable, List, Dict
from urllib.parse import urlparse, parse_qs, ParseResult, urlencode
import requests
from requests.auth import AuthBase
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from boto3 import session
from moto.s3.responses import ResponseObject
from moto.s3.models import s3_backend


class AllowlistEntry:

    def __init__(self, bucket, key=''):
        self.bucket = bucket
        self.key = key

    @staticmethod
    def from_line(line):
        bucket_key = line.strip().split("/", 1)
        if len(bucket_key) == 1:
            return AllowlistEntry(bucket_key[0])

        return AllowlistEntry(bucket_key[0], bucket_key[1])

    def __str__(self):
        return self.bucket + '/' + self.key


class Configuration:

    def __init__(self):
        self.endpoint_url = os.environ.get('ROS3_S3_ENDPOINT_URL')
        path_to_whitelist = os.environ.get('ROS3_PATH_TO_ALLOWLIST')
        if path_to_whitelist is None:
            self.whitelist = None
        else:
            self.whitelist = self.read_whitelist(path_to_whitelist)
        logging.info("WHITELIST IS %s", [str(e) for e in self.whitelist])

    @staticmethod
    def read_whitelist(path) -> List[AllowlistEntry]:
        with open(path) as f:
            return [AllowlistEntry.from_line(x) for x in f.readlines()]


def extract_bucket_from_path(path) -> (str, str):
    """
    :param path: The path of the request from the client
    :return: A pair of strings containing (bucket, path)

    It is assumed that requests to ros3 are S3 path-style requests of form;

        https://s3.Region.amazonaws.com/bucket-name/key-name

    The request is redirected using the bucket which is the first component of the path
    to the virtual hosted style which is of form;

        https://bucket-name.s3.Region.amazonaws.com/key-name

    """
    paths = path.split('/')
    filtered = [p for p in paths if p]
    return filtered[0], '/' + '/'.join(filtered[1:])


def get_host_and_path(parsed_url: ParseResult) -> (str, str):
    bucket, path = extract_bucket_from_path(parsed_url.path)
    return f'https://{bucket}.s3.amazonaws.com', path


def matches_beginning(prefix: str, allowlist_key: str) -> bool:
    """"
    :param prefix: the value of the prefix query parameter
    :param allowlist_key: the key from
    :return: a bool of whether the prefix can be found on the allowlist.
        Both values are stripped of leading `/` before comparison.
    """
    return prefix.lstrip('/').find(allowlist_key.lstrip('/')) == 0


def is_request_on_allowlist(config: Configuration, parsed_url: ParseResult, params: Dict[str, List[str]]) -> bool:
    if config.whitelist is not None:
        bucket, path = extract_bucket_from_path(parsed_url.path)
        matched_bucket_entries = [entry for entry in config.whitelist if entry.bucket == bucket]
        if 'prefix' in params:
            return [entry for entry in matched_bucket_entries if matches_beginning(params['prefix'][0], entry.key)] != []

        return [entry for entry in matched_bucket_entries if matches_beginning(path, entry.key)] != []
    return True


def create_url(config: Configuration, parsed_url: ParseResult) -> str:
    querystring = ''
    host, path = get_host_and_path(parsed_url)
    if parsed_url.query:
        querystring = '?' + urlencode(parse_qs(parsed_url.query, keep_blank_values=True), doseq=True)
    if config.endpoint_url:
        return config.endpoint_url + parsed_url.path + querystring

    return host + path + querystring


class S3V4Sign(AuthBase):
    """
    AWS V4 Request Signer for Requests.
    from https://github.com/jmenga/requests-aws-sign
    """

    def __init__(self, config: Configuration, parsed_url: ParseResult):
        sesh = session.Session()
        self.credentials = sesh.get_credentials()
        self.region = sesh.region_name
        self.url = create_url(config, parsed_url)
        logging.info("Redirected URl is %s", self.url)

    def __call__(self, request: AWSRequest):
        # Method hard coded to 'GET' as this prevents making accidental 'POSTS'
        aws_request = AWSRequest(method='GET', url=self.url, data=request.body)
        S3SigV4Auth(self.credentials, 's3', self.region).add_auth(aws_request)
        request.headers.update(dict(aws_request.headers.items()))
        return request


def mirror_req_to_s3(config: Configuration, parsed_url: ParseResult) -> (int, dict, str):
    """
    :param parsed_url: The parsed url of the request from the client to be mirrored to S3
    :param config: The application level configuration
    :return: A response of form (status_code, headers, content)

    This method will throw if the underlying request to S3 throws.

    It is assumed requests to ros3 are S3 path-style requests of form;

        https://s3.Region.amazonaws.com/bucket-name/key-name

    The request is redirected using the bucket which is the first component of the path
    to the virtual hosted style which is of form;

        https://bucket-name.s3.Region.amazonaws.com/key-name

    If clients make requests to the ros3 service using virtual hosted-style requests
    it will not work out well.

    More documentation can be found about this here;
    https://docs.aws.amazon.com/AmazonS3/latest/dev/VirtualHosting.html
    """
    auth = S3V4Sign(config, parsed_url)
    real_resp = requests.get(auth.url, auth=auth)
    real_resp.raise_for_status()
    # NOTE: Returning {} as the returned headers, essentially dropping
    # all of the response headers. Maybe filter desired headers?
    return real_resp.status_code, {}, real_resp.content


def read_s3_wrapper(func: Callable, config: Configuration) -> Callable:
    """
    :param func: ResponseObject._<resource>_response method
    :param config: The application level configuration
    :return: Wrapped ResponseObject._<resource>_response method

    Qu'est ce que fuck

    This will attempt a normal read from mock S3, and if that throws and exception
    it will try to read from the real S3. If that fails, return the error from
    the request to the mock S3. Reads should be redirected to the real S3 if the
    mock S3 returns no content and the bucket is on bucket `whitelist`.
    """
    @functools.wraps(func)
    def wrapper(self, request: requests.Request, full_url, headers):
        if request.method in ("GET", "HEAD"):
            parsed_url = urlparse(full_url)
            if is_request_on_allowlist(config, parsed_url, parse_qs(full_url)):
                try:
                    return mirror_req_to_s3(config, parsed_url)
                # pylint: disable=broad-except
                except Exception as e:
                    logging.warning(e)
            return func(self, request, full_url, headers)
        return func(self, request, full_url, headers)
    return wrapper


class S3GetResponse(ResponseObject):

    config = Configuration()
    _key_response = read_s3_wrapper(ResponseObject._key_response, config)

    _bucket_response = read_s3_wrapper(ResponseObject._bucket_response, config)


S3ResponseInstance = S3GetResponse(s3_backend)
