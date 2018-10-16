import threading


def stream_timeout(stream, timeout, timeout_msg=None):
    """
    Iterate over items in a streaming response from the Docker client within
    a timeout.

    :param ~docker.types.daemon.CancellableStream stream:
        Stream from the Docker client to consume items from.
    :param timeout:
        Timeout value in seconds.
    :param timeout_msg:
        Message to raise in the exception when a timeout occurs.
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
            raise TimeoutError(timeout_msg)
    finally:
        timer.cancel()
        # Close the stream's underlying response object (if it has one) to
        # avoid potential socket leaks.
        # This method seems to have more success at preventing ResourceWarnings
        # than just stream.close() (should this be improved upstream?)
        # FIXME: Potential race condition if Timer thread closes the stream at
        # the same time we do here, but hopefully not with serious side effects
        if hasattr(stream, '_response'):
            stream._response.close()
