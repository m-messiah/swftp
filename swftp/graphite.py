"""
See COPYING for license information.
"""
from twisted.application import service
from swftp.utils import MetricCollector
from time import time as timestamp
import socket


def makeService(host='127.0.0.1', port=2003, sample_rate=1.0, prefix=''):
    metric_collector = MetricCollector()
    metric_collector.start()
    reporting = service.Service()

    metric_reporter = MetricReporter((host, port), metric_collector, prefix)
    reporting.schedule(metric_reporter.report_metrics, sample_rate, None)

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
            sender.send("%s %s %s\n"
                        % (".".join(filter(len, [self.prefix, name])),
                           value, ts))
        sender.close()
        self.collector.sample()
