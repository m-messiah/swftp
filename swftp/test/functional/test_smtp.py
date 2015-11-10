#!/usr/bin/python
import shutil
import tempfile

import time
from twisted.internet import defer, reactor
from twisted.web.client import HTTPConnectionPool
from twisted.trial import unittest
import smtplib

from . import get_config, clean_swift, get_swift_client

conf = get_config()


class SMTPFuncTest(unittest.TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        self.pool = HTTPConnectionPool(reactor, persistent=True)
        self.swift = get_swift_client(conf, pool=self.pool)
        self.tmpdir = tempfile.mkdtemp()
        self.smtp = self.get_smtp_client()
        yield clean_swift(self.swift)

    @defer.inlineCallbacks
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        self.smtp.close()
        yield clean_swift(self.swift)
        yield self.pool.closeCachedConnections()

    def get_smtp_client(self):
        return get_smtp_client(conf)


def validate_config(config):
    for key in 'smtp_host smtp_port sender receivers'.split():
        if key not in config:
            raise unittest.SkipTest("%s not set in the test config file" % key)


def get_smtp_client(config):
    validate_config(config)
    smtp = smtplib.SMTP(config['smtp_host'], port=config['smtp_port'])
    if config.get('debug'):
        smtp.set_debuglevel(5)
    return smtp


class BasicTests(unittest.TestCase):
    def test_get_client(self):
        smtp = get_smtp_client(conf)
        smtp.ehlo_or_helo_if_needed()
        smtp.quit()

    def test_get_client_close(self):
        smtp = get_smtp_client(conf)
        smtp.ehlo_or_helo_if_needed()
        smtp.close()

    def test_get_client_sock_close(self):
        for n in range(100):
            smtp = get_smtp_client(conf)
            smtp.ehlo_or_helo_if_needed()
            smtp.sock.close()
            smtp.file.close()


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.active_connections = []

    def tearDown(self):
        for conn in self.active_connections:
            try:
                conn.close()
            except:
                pass

    def get_client(self):
        conn = get_smtp_client(conf)
        self.active_connections.append(conn)
        return conn

    def test_get_many_client(self):
        for i in range(32):
            smtp = get_smtp_client(conf)
            smtp.close()

    # This test assumes sessions_per_user = 10
    def test_get_many_concurrent(self):
        validate_config(conf)
        for i in range(100):
            smtp = smtplib.SMTP(conf['smtp_host'], port=conf['smtp_port'])
            self.active_connections.append(smtp)
        time.sleep(10)

    # This test assumes sessions_per_user = 10
    def test_concurrency_limit_disconnect_one(self):
        for i in range(10):
            self.get_client()

        conn = self.active_connections.pop()
        conn.close()

        # This should not raise an error
        self.get_client()


class SendTests(SMTPFuncTest):
    @defer.inlineCallbacks
    def test_send(self):
        validate_config(conf)
        message = ("From: From Person <from@fromdomain.com>\n"
                   "To: To Person <to@todomain.com>\n"
                   "Subject: SMTP e-mail test\n"
                   "This is a test e-mail message.\n")
        self.smtp.sendmail(conf['sender'], conf['receivers'], message)
