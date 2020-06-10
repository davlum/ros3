import boto3


def test_s3():
    client = boto3.client(
        service_name='s3',
        region_name='us-east-1',
        endpoint_url='http://localhost:3000',
    )

    bucket = 'bucket'
    client.create_bucket(Bucket=bucket)
    client.put_object(Bucket=bucket, Key='key/2020-05/03/02/part.txt', Body="hello goodbye")  # Will be returned
    client.put_object(Bucket=bucket, Key='key/2020-05/03/05/part.txt', Body="hello")  # Will be returned
    client.put_object(Bucket=bucket, Key='key/2020-05/02/02/part.txt', Body="goodbye")  # Won't be returned
    client.put_object(Bucket=bucket, Key='key/2020-05/03/08/part.gz', Body="foobar")  # Won't be returned
    resp = client.list_objects(Bucket=bucket, Delimiter='key')
    print(resp)
