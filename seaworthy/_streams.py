import threading


def stream_timeout(stream, timeout):
    """
    :param stream:
    :param timeout:
    """
    timed_out = threading.Event()

    def timeout_func():
        timed_out.set()
        stream.close()

    timer = threading.Timer(timeout, timeout_func)
    try:
        timer.start()
        for item in stream:
            yield item

        # A timeout looks the same as the loop ending. So we need to check a
        # flag to determine whether a timeout occurred or not.
        if timed_out.is_set():
            raise TimeoutError()
    finally:
        timer.cancel()
        # Close the stream's underlying response object (if it has one) to
        # avoid potential socket leaks.
        if hasattr(stream, '_response'):
            stream._response.close()
