"""
See COPYING for license information.
"""
import os.path
import socket

from twisted.trial import unittest

from swftp.smtp.service import makeService, Options


TEST_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class SMTPServiceTest(unittest.TestCase):

    def setUp(self):
        opts = Options()
        opts.parseOptions([
            '--config_file=%s' % os.path.join(TEST_PATH, 'test-smtp.conf'),
        ])
        self.service = makeService(opts)
        return self.service.startService()

    def tearDown(self):
        return self.service.stopService()

    def test_service_listen(self):
        sock = socket.socket()
        sock.connect(('127.0.0.1', 2500))
