import boto3
import pytest
from botocore.exceptions import ClientError


def get_s3_client():
    return boto3.client(
        service_name='s3',
        region_name='us-east-1',
        endpoint_url='http://s3:5000',
    )


def get_ros3_client():
    return boto3.client(
        service_name='s3',
        region_name='us-east-1',
        endpoint_url='http://localhost:2000',
    )


def load_s3():
    client = get_s3_client()
    client.create_bucket(Bucket='real-bucket-1')
    client.create_bucket(Bucket='real-bucket-2')
    client.put_object(Bucket='real-bucket-1', Key='foo/bar/hellogoodbye.txt', Body='hello goodbye')
    client.put_object(Bucket='real-bucket-1', Key='kux/foo/hello.txt', Body='hello')
    client.put_object(Bucket='real-bucket-1', Key='foo/kux/hello.txt', Body='hello')
    client.put_object(Bucket='real-bucket-2', Key='foo/bar/goodbye.txt', Body='goodbye')


def test_create_bucket():
    load_s3()
    client = get_ros3_client()
    client.create_bucket(Bucket='fake-bucket')
    client.put_object(Bucket='fake-bucket', Key='foo/bar/goodbye.txt', Body='goodbye')
    resp = client.get_object(Bucket='fake-bucket', Key='foo/bar/goodbye.txt')
    assert resp['Body'].read().decode('utf-8') == 'goodbye'


def test_list_objects_v2_whitelisted():
    client = get_ros3_client()
    resp = client.list_objects_v2(Bucket='real-bucket-1', Prefix='foo')
    res = {ele['Key'] for ele in resp['Contents']}
    assert res == {'foo/bar/hellogoodbye.txt', 'foo/kux/hello.txt'}


def test_list_objects_v2_not_whitelisted():
    client = get_ros3_client()
    with pytest.raises(ClientError) as err:
        client.list_objects_v2(Bucket='real-bucket-2', Prefix='foo')
    err_dict = err.value.response['Error']
    assert err_dict['Message'] == 'The specified bucket does not exist'
    assert err_dict['BucketName'] == 'real-bucket-2'


def test_get_object():
    client = get_ros3_client()
    resp = client.get_object(Bucket='real-bucket-1', Key='foo/bar/hellogoodbye.txt')
    assert resp['Body'].read().decode('utf-8') == 'hello goodbye'
