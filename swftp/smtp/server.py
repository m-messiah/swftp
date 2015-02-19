from twisted.mail.smtp import IMessageDelivery, IMessage, SMTPBadRcpt,\
                              SMTPFactory, ESMTP, rfc822date, SMTPServerError
from zope.interface import implements
from twisted.internet import defer
from twisted.cred.credentials import UsernamePassword
from twisted.cred.error import UnauthorizedLogin
from swftp.logging import msg
from swftp.swiftfilesystem import SwiftFileSystem
from twisted.internet.interfaces import IPushProducer
from uuid import uuid4

class SwftpSMTPFactory(SMTPFactory):
    protocol = ESMTP

    def __init__(self, swift_connect, recipients, rabbitmq_cluster, queue_name):
        SMTPFactory.__init__(self)
        self.swift_connect = swift_connect
        self.recipients = recipients
        self.rabbitmq_cluster = rabbitmq_cluster
        self.queue_name = queue_name
        self.swift_connection = None

    @defer.inlineCallbacks
    def connectToSwift(self):
        if not self.swift_connection:
            self.swift_connection = yield self.swift_connect()
        defer.returnValue(self.swift_connection)

    def buildProtocol(self, addr):
        p = SMTPFactory.buildProtocol(self, addr)
        p.delivery = SwiftSMTPUserDelivery(self, self.recipients)
        return p

class SwiftSMTPUserDelivery(object):

    implements(IMessageDelivery)

    def __init__(self, factory, recipients):
        self.factory = factory
        self.recipients = recipients

    def receivedHeader(self, helo, origin, recipients):
        r = ",".join(str(u) for u in recipients)
        return "Received: for %s %s" % (r, rfc822date())

    def validateFrom(self, helo, origin):
        return origin

    @defer.inlineCallbacks
    def validateTo(self, user):
        if user.dest.local in self.recipients:
            swift_conn = yield self.factory.connectToSwift()
            swift_filesystem = SwiftFileSystem(swift_conn,
                    self.factory.rabbitmq_cluster, self.factory.queue_name)
            path = '/smtp/%s/%s' % (user.dest.local, uuid4())
            d, swift_file = swift_filesystem.startFileUpload(path)
            yield swift_file.started
            msg("Uploading %s" % path)
            defer.returnValue(lambda: SwiftMessage(d, swift_file))
        else:
            raise SMTPBadRcpt(user)

class SwiftMessage:
    implements(IMessage, IPushProducer)

    def __init__(self, uploading, swift_file):
        swift_file.registerProducer(self, streaming=True)
        self.swift_file = swift_file
        self.uploading = uploading

    def pauseProducing(self):
        pass

    def resumeProducing(self):
        pass

    def stopProducing(self):
        pass

    def lineReceived(self, line):
        self.swift_file.write(''.join([line, '\n']))

    def eomReceived(self):
        self.swift_file.stopProducing()
        self.swift_file.unregisterProducer()
        return self.uploading

    def connectionLost(self):
        # There was an error, throw away the stored lines
        self.swift_file.stopProducing()
        self.swift_file.unregisterProducer()
