import string
import time

import pytest

from seaworthy.containers.nginx import NginxContainer
from seaworthy.logs import output_lines
from seaworthy.pytest import dockertest


@pytest.fixture(scope='module')
def nginx(docker_helper):
    with NginxContainer(helper=docker_helper) as container:
        yield container


@dockertest()
class TestNginxContainer:
    def test_inspection(self, nginx):
        """
        Inspecting the Nginx container should show that the default image
        and name has been used, a forwarded port has been set up and the
        network aliases are correct.
        """
        attrs = nginx.inner().attrs

        assert attrs['Config']['Image'] == NginxContainer.DEFAULT_IMAGE
        assert attrs['Name'] == '/test_{}'.format(NginxContainer.DEFAULT_NAME)

        assert len(attrs['NetworkSettings']['Ports']['80/tcp']) == 1

        network = attrs['NetworkSettings']['Networks']['test_default']
        # The ``short_id`` attribute of the container is the first 10
        # characters, but the network alias is the first 12 :-/
        assert (network['Aliases'] ==
                [NginxContainer.DEFAULT_NAME, attrs['Id'][:12]])

    def test_default_server(self, nginx):
        """
        The default Nginx server config should be available from the forwarded
        port at the root HTTP path.
        """
        client = nginx.http_client()
        response = client.get('/')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'text/html'
        assert '<title>Welcome to nginx!</title>' in response.text

    def test_exec_nginx(self, nginx):
        """
        We can run an Nginx command inside a running container using
        ``exec_nginx()``.
        """
        output = output_lines(nginx.exec_nginx(['-V']))
        assert output[0].startswith('nginx version: nginx/')

    def test_config_in_volume(self, docker_helper, tmpdir):
        """
        When we mount a volume containing the server config for Nginx, that
        config is used, and when that config is changed and a reload signal is
        sent to Nginx, the new config takes effect.
        """
        config_template = string.Template("""
server {
    listen 80;

    location / {
        root       /usr/share/nginx/html;
        index      index.html index.htm;
        add_header X-Test-Header $test_header;
    }
}
        """)

        config_file = tmpdir.join('test.conf')
        config_file.write(config_template.substitute(test_header='foo'))

        nginx_container = NginxContainer(
            name='nginx_vol', helper=docker_helper, create_kwargs={
                'volumes': {str(tmpdir): '/etc/nginx/conf.d'}})

        with nginx_container:
            client = nginx_container.http_client()

            response = client.get('/')
            assert response.headers['X-Test-Header'] == 'foo'

            # Change the config file and trigger a reload
            config_file.write(config_template.substitute(test_header='bar'))

            # Nothing changed before we reload...
            response = client.get('/')
            assert response.headers['X-Test-Header'] == 'foo'

            nginx_container.exec_signal()

            # It takes a little while for the new config to be loaded.
            # Try a few times with a small delay
            for _ in range(5):  # pragma: no cover
                response = client.get('/')
                if response.headers['X-Test-Header'] == 'bar':
                    break
                time.sleep(0.1)
            assert response.headers['X-Test-Header'] == 'bar'
