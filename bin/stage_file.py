#!/usr/bin/env python

"""
Stage files in the HCA Staging Area

Usage:

    stage_file cp <file> <urn>

"""

import argparse, base64, json, os, sys

try:
    import boto3
    from boto3.s3.transfer import TransferConfig
except ImportError:
    print("\nPlease install boto3 to use this script, e.g. \"pip install boto3\"\n")
    exit(1)

KB = 1024
MB = KB * KB


def sizeof_fmt(num, suffix='B'):
    """
    From https://stackoverflow.com/a/1094933
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%d %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


class Main:

    STAGING_BUCKET_TEMPLATE = "org-humancellatlas-staging-%s"
    CLEAR_TO_EOL = "\x1b[0K"

    def __init__(self):
        self._parse_args()
        junk, junk, junk, self.area_uuid, encoded_credentials = self.args.urn.split(':')
        uppercase_credentials = json.loads(base64.b64decode(encoded_credentials))
        credentials = {k.lower(): v for k, v in uppercase_credentials.items()}
        session = boto3.session.Session(**credentials)
        self.s3 = session.resource('s3')
        self._stage_file(self.args.file_path)

    def _parse_args(self):
        parser = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('file_path', metavar="<file>",
                            help="name of file to stage")
        parser.add_argument('urn', metavar='<URN>',
                            help="URN of staging area (given to you by Ingest Broker)")
        parser.add_argument('-d', '--deployment', metavar="<deployment>", default='dev',
                            help="Deployment to use (default=dev)")
        self.args = parser.parse_args()

    def callback(self, bytes_transferred):
        self.cumulative_bytes_transferred += bytes_transferred
        percent_complete = (self.cumulative_bytes_transferred * 100) / self.file_size
        sys.stdout.write("\r%s of %s transferred (%.0f%%)%s" %
                         (sizeof_fmt(self.cumulative_bytes_transferred),
                          sizeof_fmt(self.file_size),
                          percent_complete,
                          self.CLEAR_TO_EOL))
        sys.stdout.flush()

    def _stage_file(self, file_path):
        print("Uploading %s to staging area %s..." % (os.path.basename(file_path), self.area_uuid))
        self.file_size = os.stat(file_path).st_size
        bucket_name = self.STAGING_BUCKET_TEMPLATE % (self.args.deployment,)
        file_s3_key = "%s/%s" % (self.area_uuid, os.path.basename(file_path))
        bucket = self.s3.Bucket(bucket_name)
        obj = bucket.Object(file_s3_key)
        with open(file_path, 'rb') as fh:
            self.cumulative_bytes_transferred = 0
            obj.upload_fileobj(fh,
                               ExtraArgs={'ACL': 'bucket-owner-full-control'},
                               Callback=self.callback,
                               Config=self.transfer_config(self.file_size)
                               )
        print("\n")

    @classmethod
    def transfer_config(cls, file_size):
        etag_stride = cls._s3_chunk_size(file_size)
        return TransferConfig(multipart_threshold=etag_stride,
                              multipart_chunksize=etag_stride)

    @staticmethod
    def _s3_chunk_size(file_size):
        if file_size <= 10000 * 64 * MB:
            return 64 * MB
        else:
            div = file_size // 10000
            if div * 10000 < file_size:
                div += 1
            return ((div + (MB-1)) // MB) * MB


if __name__ == '__main__':
    runner = Main()
