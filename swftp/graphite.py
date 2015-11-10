"""
See COPYING for license information.
"""
from twisted.application.service import Service
from twisted.internet.task import LoopingCall

from swftp.utils import MetricCollector
from time import time as timestamp
import socket


class ReportingService(Service):

    def __init__(self, instance_name="", clock=None):
        self.tasks = []
        self.clock = clock
        self.instance_name = instance_name

    def schedule(self, function, interval):
        """
        Schedule C{function} to be called every C{interval}
        """
        task = LoopingCall(function)
        if self.clock is not None:
            task.clock = self.clock
        self.tasks.append((task, interval))
        if self.running:
            task.start(interval, now=True)

    def startService(self):
        Service.startService(self)
        for task, interval in self.tasks:
            task.start(interval, now=False)

    def stopService(self):
        for task, interval in self.tasks:
            task.stop()
        Service.stopService(self)


def makeService(host='127.0.0.1', port=2003, sample_rate=1.0, prefix=''):
    metric_collector = MetricCollector()
    metric_collector.start()
    reporting = ReportingService()

    metric_reporter = MetricReporter((host, port), metric_collector, prefix)
    reporting.schedule(metric_reporter.report_metrics, sample_rate)

    return reporting


class MetricReporter(object):
    def __init__(self, graphite, collector, prefix):
        self.graphite = graphite
        self.collector = collector
        self.prefix = prefix

    def report_metrics(self):
        # Report collected metrics
        results = self.collector.current
        sender = socket.socket()
        sender.connect(self.graphite)
        ts = int(timestamp())
        for name, value in results.items():
            if self.prefix:
                name = self.prefix + "." + name
            sender.send("%s %s %s\n" % (name, value, ts))
        sender.close()
        self.collector.sample()
