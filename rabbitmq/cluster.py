from pika import ConnectionParameters, PlainCredentials, BasicProperties
from twisted.python import log
from pika.adapters.twisted_connection import TwistedProtocolConnection
from twisted.internet import defer, reactor, protocol, task

class RabbitReplica:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channel = None
        self.connection = None

    def __str__(self):
        return "%s:%s" % (self.host, self.port)

    def is_connected(self):
        return self.connection and self.connection.is_open

    def disconnect(self):
        log.msg('Disconnecting from %s' % self)
        if self.is_connected():
            self.connection.close()
            d = defer.Deferred()
            def _disconnected(*args):
                d.callback(None)
            self.connection.add_on_close_callback(_disconnected)
            return d
        return defer.succeed(None)


    def send(self, queue_name, body):
        log.msg('Publishing %s body to "%s" on %s' % (len(body), queue_name, self))
        properties=BasicProperties(delivery_mode=1)

        @defer.inlineCallbacks
        def on_declare(queue):
            log.msg("Queue %s declared" % queue_name)
            def on_publish_failed(result):
                channel, response, props, body = result
                log.err("Publish failed %s" % response)
            self.channel.add_on_return_callback(on_publish_failed)
            yield self.channel.basic_publish(exchange='', body=body, routing_key=queue_name, properties=properties, mandatory=True)

        def on_declare_fail(error):
            log.err('Can not declare queue %s' % error)

        d = self.channel.queue_declare(queue=queue_name, auto_delete=False, exclusive=False)
        d.addCallbacks(on_declare, on_declare_fail)
        return d

    def connect(self, credentials):
        if self.is_connected():
            return defer.succeed(True)
        log.msg('Connecting to %s' % self)
        parameters = ConnectionParameters(virtual_host='/', credentials=credentials)
        cc = protocol.ClientCreator(reactor, TwistedProtocolConnection, parameters)
        d = cc.connectTCP(self.host, self.port)

        @defer.inlineCallbacks
        def success(connection):
            self.connection = connection
            self.channel = yield connection.channel()
            log.msg('Connected to %s channel open' % self)
            defer.returnValue(True)

        def failed(error):
            log.err('Connect to %s failed: %s' % (self, error))

        d.addCallback(lambda protocol: protocol.ready)
        d.addCallbacks(success, failed)
        return d

class RabbitClusterClient:

    def __init__(self, replicas, user, password):
        self.replicas = replicas
        self.index = 0
        self.credentials = PlainCredentials(user, password)

    def __str__(self):
        return ''.join([str(r) for r in self.replicas])

    def connect(self):
        @defer.inlineCallbacks
        def replica_connect(result):
            replica = self.replicas[self.index]
            while not (yield replica.connect(self.credentials)):
                self.__next()
                replica = self.replicas[self.index]
                if self.index == 0:
                    log.msg('Reconnecting afer 10 sec')
                    yield task.deferLater(reactor, 10, lambda: None)
            defer.returnValue(replica)
        d = defer.succeed(None)
        d.addCallback(replica_connect)
        return d

    def disconnect(self):
        @defer.inlineCallbacks
        def _disconnect(result):
            for replica in self.replicas:
                yield replica.disconnect()
        d = defer.succeed(None)
        d.addCallback(_disconnect)
        return d


    def __next(self):
        self.index = (self.index + 1) % len(self.replicas)
