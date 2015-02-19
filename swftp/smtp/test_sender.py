#!/usr/bin/python

import smtplib

sender = 'from@fromdomain.com'
receivers = ['e@todomain.com']

message = """From: From Person <from@fromdomain.com>
To: To Person <to@todomain.com>
Subject: SMTP e-mail test
This is a test e-mail message.
"""

try:
    smtpObj = smtplib.SMTP('localhost', port=2500)
    smtpObj.sendmail(sender, receivers, message)
    print "Successfully sent email"
except smtplib.SMTPException as e:
    print "Error: unable to send email", e
