import moto.server as server
import sys


# Replace moto s3 with the custom s3 implementation
sys.modules['moto.s3.urls'] = __import__('ros3.urls')


if __name__ == "__main__":
    server.main(['s3', *sys.argv[1:]])
