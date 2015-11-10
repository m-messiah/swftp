"""
This file defines what is required for swftp-sftp to work with twistd.

See COPYING for license information.
"""
from swftp import VERSION
from swftp.logging import StdOutObserver
from swftp.swiftfilesystem import SwiftFileSystem
from swftp import swift

from twisted.application import internet, service
from twisted.python import usage, log
from twisted.internet import reactor, defer
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.mail.smtp import SMTPFactory, ESMTP, SMTPServerError
from twisted.cred.credentials import UsernamePassword

import ConfigParser
import signal
import os
import sys
import time

from rabbitmq.cluster import RabbitReplica, RabbitClusterClient
from server import SwftpSMTPFactory

CONFIG_DEFAULTS = {
    'auth_url': 'http://127.0.0.1:8080/auth/v1.0',
    'host': '0.0.0.0',
    'port': '2500',

    'swift_username':'username',
    'swift_password':'password',

    'rewrite_storage_scheme': '',
    'rewrite_storage_netloc': '',

    'num_persistent_connections': '100',
    'num_connections_per_session': '10',
    'connection_timeout': '240',
    'sessions_per_user': '10',
    'extra_headers': '',

    'verbose': 'false',

    'rabbitmq_hosts': '127.0.0.1:5672',
    'queue_name': 'smtp_messages',
    'username': 'admin',
    'password': 'admin',
}


def run():
    options = Options()
    try:
        options.parseOptions(sys.argv[1:])
    except usage.UsageError, errortext:
        print '%s: %s' % (sys.argv[0], errortext)
        print '%s: Try --help for usage details.' % (sys.argv[0])
        sys.exit(1)

    # Start Logging
    obs = StdOutObserver()
    obs.start()

    s = makeService(options)
    s.startService()
    reactor.run()


def parse_config_list(conf_name, conf_value, valid_options_list):
    lst, lst_not = [], []
    for ch in conf_value.split(","):
        ch = ch.strip()
        if ch in valid_options_list:
            lst.append(ch)
        else:
            lst_not.append(ch)

    if lst_not:
        log.msg(
            "Unsupported {}: {}".format(conf_name, ", ".join(lst_not)))
    return lst


def get_config(config_path, overrides):
    c = ConfigParser.ConfigParser(CONFIG_DEFAULTS)
    c.add_section('smtp')
    c.add_section('rabbitmq')
    if config_path:
        log.msg('Reading configuration from path: %s' % config_path)
        c.read(config_path)
    else:
        config_paths = [
            '/etc/swftp/swftp.conf',
            os.path.expanduser('~/.swftp.cfg')
        ]
        log.msg('Reading configuration from paths: %s' % config_paths)
        c.read(config_paths)
    for k, v in overrides.iteritems():
        if v:
            c.set('smtp', k, str(v))

    return c


class Options(usage.Options):
    "Defines Command-line options for the swftp-sftp service"
    optFlags = [
        ["verbose", "v", "Make the server more talkative"]
    ]
    optParameters = [
        ["config_file", "c", None, "Location of the swftp config file."],
        ["auth_url", "a", None,
            "Auth Url to use. Defaults to the config file value if it exists."
            "[default: http://127.0.0.1:8080/auth/v1.0]"],
        ["port", "p", None, "Port to bind to."],
        ["host", "h", None, "IP to bind to."],
    ]


def makeService(options):
    """
    Makes a new swftp-sftp service. The only option is the config file
    location. See CONFIG_DEFAULTS for list of configuration options.
    """
    from twisted.cred.portal import Portal

    from swftp.realm import SwftpRealm
    from swftp.auth import SwiftBasedAuthDB
    from swftp.utils import (
        log_runtime_info, GLOBAL_METRICS, parse_key_value_config)

    c = get_config(options['config_file'], options)

    smtp_service = service.MultiService()

    # ensure timezone is GMT
    os.environ['TZ'] = 'GMT'
    time.tzset()

    print('Starting SwFTP-smtp %s' % VERSION)

    authdb = SwiftBasedAuthDB(
        c.get('smtp', 'auth_url'),
        global_max_concurrency=c.getint('smtp', 'num_persistent_connections'),
        max_concurrency=c.getint('smtp', 'num_connections_per_session'),
        timeout=c.getint('smtp', 'connection_timeout'),
        extra_headers=parse_key_value_config(c.get('smtp', 'extra_headers')),
        verbose=c.getboolean('smtp', 'verbose'),
        rewrite_scheme=c.get('smtp', 'rewrite_storage_scheme'),
        rewrite_netloc=c.get('smtp', 'rewrite_storage_netloc'),
    )

    rabbitmq_hosts = c.get('rabbitmq', 'rabbitmq_hosts')
    rabbitmq_cluster = RabbitClusterClient([RabbitReplica(host, port) \
                        for host, port in [(h,int(p)) for h,p in [r.split(':') \
                        for r in rabbitmq_hosts.split(',')]]], \
                        c.get('rabbitmq', 'username'), \
                        c.get('rabbitmq', 'password')) \
                        if rabbitmq_hosts else None
    queue_name = c.get('smtp', 'queue_name')
    swift_username = c.get('smtp', 'swift_username')
    swift_password = c.get('smtp', 'swift_password')

    def swift_connect():
        d = authdb.requestAvatarId(
            UsernamePassword(swift_username, swift_password)
        )

        def cb(connection):
            return connection

        def errback(failure):
            log.err("Swift connection failed: %s" % failure.type)
            raise SMTPServerError(451, "Internal server error")

        d.addCallbacks(cb, errback)
        return d

    @defer.inlineCallbacks
    def prepare_path():
        try:
            swift_conn = yield swift_connect()
            swift_filesystem = SwiftFileSystem(swift_conn)
            try:
                yield swift_filesystem.get_container_listing('smtp', '/')
            except swift.NotFound:
                yield swift_filesystem.makeDirectory('/smtp/')
        except:
            pass
        defer.returnValue(None)

    prepare_path()

    smtp_factory = SwftpSMTPFactory(swift_connect, rabbitmq_cluster, queue_name)

    signal.signal(signal.SIGUSR1, log_runtime_info)
    signal.signal(signal.SIGUSR2, log_runtime_info)

    internet.TCPServer(
        c.getint('smtp', 'port'),
        smtp_factory,
        interface=c.get('smtp', 'host')).setServiceParent(smtp_service)

    return smtp_service
