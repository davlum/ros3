from __future__ import unicode_literals
from moto.s3.models import s3_backend
from ros3.urls import url_paths

s3_backends = {"global": s3_backend}
mock_s3 = s3_backend.decorator
mock_s3_deprecated = s3_backend.deprecated_decorator
