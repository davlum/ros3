# ros3
ros3 (Readonly S3) will dispatch reads to the real S3, and writes to a local mock S3.

Configuration in done by an allowlist file that is set from an environment variable `ROS3_PATH_TO_ALLOWLIST`.

The format of the file is 

```.csv
bucket/key/foo
```


