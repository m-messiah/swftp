from twisted.mail.smtp import IMessageDelivery, IMessage, SMTPBadRcpt,\
                              SMTPFactory, ESMTP, rfc822date, SMTPServerError
from zope.interface import implements
from twisted.internet import defer
from twisted.cred.credentials import UsernamePassword
from twisted.cred.error import UnauthorizedLogin
from swftp.logging import msg
from swftp import swift
from swftp.swiftfilesystem import SwiftFileSystem
from twisted.internet.interfaces import IPushProducer
from uuid import uuid4
import json

class SwftpSMTPFactory(SMTPFactory):
    protocol = ESMTP

    def __init__(self, connectToSwift, rabbitmq_cluster, queue_name):
        SMTPFactory.__init__(self)
        self.connectToSwift = connectToSwift
        self.rabbitmq_cluster = rabbitmq_cluster
        self.queue_name = queue_name

    def buildProtocol(self, addr):
        p = SMTPFactory.buildProtocol(self, addr)
        p.delivery = SwiftSMTPUserDelivery(self.connectToSwift, self.rabbitmq_cluster, self.queue_name)
        return p

class SwiftSMTPUserDelivery(object):

    implements(IMessageDelivery)

    def __init__(self, connectToSwift, rabbitmq_cluster, queue_name):
        self.recipients = {}
        self.swift_connection = None
        self.connectToSwift = connectToSwift
        self.rabbitmq_cluster = rabbitmq_cluster
        self.queue_name = queue_name

    def receivedHeader(self, helo, origin, recipients):
        r = ",".join(str(u) for u in recipients)
        return "Received: for %s %s" % (r, rfc822date())

    def validateFrom(self, helo, origin):
        self.origin = str(origin)
        return origin

    @defer.inlineCallbacks
    def isRecipientValid(self, recipient):
        valid = self.recipients.get(recipient)
        if valid is not None:
            msg("Recipient %s is %svalid [cached]" % (recipient, "" if valid else "not "))
            defer.returnValue(valid)
        if not self.swift_connection:
            self.swift_connection = yield self.connectToSwift()
        swift_filesystem = SwiftFileSystem(self.swift_connection)
        try:
            yield swift_filesystem.getAttrs(''.join(['/smtp/',recipient]))
            valid = True
        except swift.NotFound:
            valid = False
        msg("Recipient %s is %svalid" % (recipient, "" if valid else "not "))
        self.recipients[recipient] = valid
        defer.returnValue(valid)

    @defer.inlineCallbacks
    def validateTo(self, user):
        recipient = str(user.dest)
        valid = yield self.isRecipientValid(recipient)
        if not valid:
            raise SMTPBadRcpt(user)
        swift_filesystem = SwiftFileSystem(self.swift_connection)
        path = '/smtp/%s/%s' % (recipient, uuid4())
        d, swift_file = swift_filesystem.startFileUpload(path)

        @defer.inlineCallbacks
        def onUpload(ignored):
            if not self.rabbitmq_cluster or not self.queue_name:
                defer.returnValue(None)
            replica = yield self.rabbitmq_cluster.connect()
            yield replica.send(self.queue_name, json.dumps({
                'username': self.swift_connection.username,
                'path': path,
                'origin': self.origin,
                'recipient': recipient,
                'gate': 'smtp'}))

        d.addCallback(onUpload)
        yield swift_file.started
        msg("Uploading %s" % path)
        defer.returnValue(lambda: SwiftMessage(d, swift_file))

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
