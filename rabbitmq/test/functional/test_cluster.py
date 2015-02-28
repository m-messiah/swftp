import sys
from twisted.trial import unittest
from rabbitmq.cluster import RabbitClusterClient, RabbitReplica
from twisted.internet import reactor, defer
from twisted.python import log

log.startLogging(sys.stdout)

host1 = '192.168.11.18'
host2 = '192.168.11.19'

class RabbitmqFuncTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_connection_1(self):
        self.cluster = RabbitClusterClient([RabbitReplica(host1, 5672), RabbitReplica(host2, 5672)], 'admin', 'admin')
        replica = yield self.cluster.connect()
        self.assertEqual(sum([1 for r in self.cluster.replicas if r.is_connected()]), 1)
        self.assertEqual(replica.host, host1)

    @defer.inlineCallbacks
    def test_connection_2(self):
        self.cluster = RabbitClusterClient([RabbitReplica('127.0.0.1', 666), RabbitReplica(host2, 5672)], 'admin', 'admin')
        yield self.cluster.connect()
        self.assertEqual(sum([1 for r in self.cluster.replicas if r.is_connected()]), 1)

    @defer.inlineCallbacks
    def test_send(self):
        self.cluster = RabbitClusterClient([RabbitReplica(host1, 5672), RabbitReplica(host2, 5672)], 'admin', 'admin')
        replica = yield self.cluster.connect()
        yield replica.send('test_queue', 'test')

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.cluster.disconnect()
