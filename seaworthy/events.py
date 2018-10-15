import iso8601

from seaworthy._streams import stream_timeout


def wait_for_healthcheck(container, timeout, status='healthy'):
    """
    Wait for the HEALTHCHECK status on a container to reach a specific status.

    Note that this uses the Docker daemon event stream to wait for the
    container's ``health_status`` event. It first checks if the container is
    already healthy before streaming events. If the container does not have a
    health check an error will be raised.
    """
    # TODO: Get a client from somewhere else??
    client = container.client

    # "Snapshot" a point in the event stream by getting the current time
    # Note that we get this from the Docker daemon in case the daemon is
    # running in a VM and has a time offset (e.g. macOS)
    since = iso8601.parse_date(client.info()['SystemTime']).timestamp()

    # First check the container's current state
    container.reload()

    # Check the container has a health check
    health = container.attrs['State'].get('Health')
    if not health:
        raise ValueError("Container '{}' does not have a healthcheck"
                         .format(container.name))

    # Check that the health check isn't already what we'll wait for
    if health['Status'] == status:
        return

    filters = {
        'type': 'container',
        'container': container.id,
        'event': 'health_status'
    }
    # Oh god Docker, whhhhyyy????
    event_status = 'health_status: {}'.format(status)

    stream = container.client.events(since=since, filters=filters, decode=True)
    generator = stream_timeout(stream, timeout)
    try:
        for event in generator:
            if event['status'] == event_status:
                return
    except TimeoutError:
        raise TimeoutError(
            "Timed out waiting for 'health_status' event with status '{}'"
            .format(status))
