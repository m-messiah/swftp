"""
See COPYING for license information.
"""
from twisted.internet import reactor
from txstatsd.client import TwistedStatsDClient, StatsDClientProtocol
from txstatsd.metrics.metrics import Metrics
from txstatsd.process import PROCESS_STATS, COUNTER_STATS
from txstatsd.report import ReportingService

from swftp.utils import MetricCollector
from time import time as timestamp
import socket


def makeService(host='127.0.0.1', port=8125, sample_rate=1.0, prefix=''):
    client = TwistedStatsDClient(host, port)
    metrics = Metrics(connection=client, namespace=prefix)
    reporting = ReportingService()

    #for report in PROCESS_STATS:
    #    reporting.schedule(report, sample_rate, metrics.gauge)

    #for report in COUNTER_STATS:
    #    reporting.schedule(report, sample_rate, metrics.gauge)

    # Attach log observer to collect metrics for us
    metric_collector = MetricCollector()
    metric_collector.start()

    metric_reporter = MetricReporter(host, port, metrics, metric_collector, prefix)
    reporting.schedule(metric_reporter.report_metrics, sample_rate, None)

    protocol = StatsDClientProtocol(client)
    reactor.listenUDP(0, protocol)
    return reporting


class MetricReporter(object):
    def __init__(self, host, port, metric, collector, prefix):
        self.metric = metric
        self.graphite = (host, port)
        self.collector = collector
        self.prefix = prefix

    def report_metrics(self):
        # Report collected metrics
        results = self.collector.current
        sender = socket.socket()
        sender.connect(self.graphite)
        ts = int(timestamp())
        for name, value in results.items():
            self.metric.increment(name, value)
            sender.send("%s.%s %s %s\n" % (self.prefix, name, value, ts))
        sender.close()
        self.collector.sample()
