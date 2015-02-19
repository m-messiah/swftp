"""
Defines serviceMaker, which required for automatic twistd integration for
swftp-sftp

See COPYING for license information.
"""
from twisted.application.service import ServiceMaker

serviceMaker = ServiceMaker(
    'swftp-smtp',  # name
    'swftp.smtp.service',  # module
    'An SMTP Proxy Interface for Swift',  # description
    'swftp-smtp'  # tap name
)
