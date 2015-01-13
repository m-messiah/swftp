from twisted.cred import portal
from zope import interface

try:
    from twisted.conch.avatar import IConchUser
    from swftp.sftp.server import SwiftSFTPUser
    HAS_SFTP = True
except ImportError:
    HAS_SFTP = False

try:
    from twisted.protocols.ftp import IFTPShell
    from swftp.ftp.server import SwiftFTPShell
    HAS_FTP = True
except ImportError:
    HAS_FTP = False


class SwftpRealm(object):
    interface.implements(portal.IRealm)

    def __init__(self, rabbitmq_cluster, queue_name):
        self.rabbitmq_cluster = rabbitmq_cluster
        self.queue_name = queue_name

    def getHomeDirectory(self):
        return '/'

    def requestAvatar(self, avatarId, mind, *interfaces):
        if avatarId:
            interface = interfaces[0]
            if HAS_SFTP and interface == IConchUser:
                avatar = SwiftSFTPUser(avatarId, self.rabbitmq_cluster, self.queue_name)
                return interface, avatar, avatar.logout
            elif HAS_FTP and interface == IFTPShell:
                shell = SwiftFTPShell(avatarId, self.rabbitmq_cluster, self.queue_name)
                return interface, shell, shell.logout

            raise NotImplementedError(
                'Only the IFTPShell and IConchUser interfaces are supported '
                'by this realm')
