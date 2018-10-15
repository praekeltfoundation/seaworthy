import threading
from queue import Queue


class FakeStreamSource:
    """
    A fake thing that emits canned items.

    Logs can either be streamed through a socket using ``.attach_socket()`` or
    tailed by using ``.items()``. After a log entry has been streamed, it is
    stored and we don't stream it next time. Only items that have already been
    streamed are tailed.
    """

    def __init__(self, items, expected_params=None, close_timeout=2):
        self.items = items
        self._seen_items = []
        self._expected_stream_params = {}
        if expected_params is not None:
            self._expected_stream_params.update(expected_params)
        self._feeders = set()
        self._close_timeout = close_timeout

    def cleanup(self):
        while self._feeders:
            self._feeders.pop().cancel()

    def tail_items(self, tail):
        if tail == 0:
            # Nothing to tail.
            return []
        if tail == 'all':
            # ALL THE LOGS/ITEMS!
            return self._seen_items
        # Just some of the items.
        assert tail > 0
        return self._seen_items[-tail:]

    def stream_items(self, tail, kw):
        assert kw == self._expected_stream_params
        feeder = StreamFeeder(self, self.tail_items(tail))
        self._feeders.add(feeder)
        feeder.start()
        return feeder.client_stream()


class StreamFeeder(threading.Thread):
    def __init__(self, source, tail):
        super().__init__()
        self.src = source
        self.q = Queue()
        self.tail = tail
        self.finished = threading.Event()

    def client_stream(self):
        return FakeCancellableStream(self, self.q)

    def cancel(self):
        self.finished.set()
        self.join()

    def send_item(self, item):
        self.q.put(item)

    def run(self):
        # Emit tailed items.
        for item in self.tail:
            self.send_item(item)
        # Emit previously unstreamed items at designated intervals.
        for delay, item in self.src.items[len(self.src._seen_items):]:
            # Wait for either cancelation (break) or timeout (no break).
            if self.finished.wait(delay):
                break
            self.src._seen_items.append(item)
            self.send_item(item)
        # Wait until we're done, which we may already be. Since some of the
        # tests don't do client-side timeouts, we use a fake-specific "server"
        # timeout.
        self.finished.wait(self.src._close_timeout)
        # Time to clean up.
        self.q.put(None)


class FakeCancellableStream:
    """
    Fake CancellableStream that iterates over the items.
    """

    def __init__(self, feeder, q):
        self._feeder = feeder
        self._q = q

    def __iter__(self):
        return self

    def __next__(self):
        assert self._q is not None, "Stream already closed."
        item = self._q.get()
        if item is None:
            self._q = None
            raise StopIteration
        return item

    def close(self):
        self._feeder.cancel()
