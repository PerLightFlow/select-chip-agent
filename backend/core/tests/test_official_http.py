import socket
import unittest
from unittest.mock import patch, MagicMock
from core.official_http import official_url, public_address, OfficialFetcher, FetchError, PinnedHTTPSConnection


class OfficialHTTPTests(unittest.TestCase):
    def test_only_known_https_hosts_and_official_org_paths(self):
        for url in ['http://www.espressif.com/x','https://127.0.0.1/x',
                    'https://www.espressif.com.evil.test/x','https://user@www.espressif.com/x',
                    'https://www.espressif.com:8080/x','https://github.com/attacker/esp-dl',
                    'https://github.com/espressif/../attacker/x',
                    'https://github.com/espressif/%2e%2e/attacker/x',
                    'https://github.com/espressif/%252e%252e/x',
                    'https://github.com/espressif/esp-dl/issues/1',
                    'https://www.espressif.com/a\\b','https://www.espressif.com/x%0afoo']:
            with self.subTest(url=url), self.assertRaises(FetchError):
                official_url(url)
        self.assertEqual(official_url('https://docs.espressif.com/test#part'),'https://docs.espressif.com/test')
        self.assertEqual(official_url('https://raw.githubusercontent.com/airockchip/rknn_model_zoo/main/README.md'),
            'https://raw.githubusercontent.com/airockchip/rknn_model_zoo/main/README.md')

    def test_rejects_mixed_public_private_dns(self):
        for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1','2002:7f00:1::']:
            records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),
                     (socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]
            with patch('core.official_http.socket.getaddrinfo',return_value=records), self.subTest(ip=ip):
                with self.assertRaises(FetchError):
                    public_address('docs.espressif.com')

    def test_connect_pins_ip_and_keeps_tls_hostname(self):
        context=MagicMock()
        with patch('core.official_http.ssl.create_default_context',return_value=context), \
             patch('core.official_http.socket.create_connection') as connect:
            c=PinnedHTTPSConnection('docs.espressif.com','8.8.8.8',3)
            c.connect()
            connect.assert_called_once_with(('8.8.8.8',443),3)
            context.wrap_socket.assert_called_once_with(connect.return_value,server_hostname='docs.espressif.com')

    @patch('core.official_http.time.sleep')
    def test_redirect_is_checked_again(self, _):
        fetcher=OfficialFetcher()
        with patch.object(fetcher,'_robot_policy'), patch.object(fetcher,'_request',
                return_value=(302,{'location':'https://127.0.0.1/private'},b'')) as req:
            with self.assertRaises(FetchError):
                fetcher.fetch('https://docs.espressif.com/doc')
            self.assertEqual(req.call_count,1)

    def test_robots_disallow_blocks_document_fetch(self):
        fetcher=OfficialFetcher()
        with patch.object(fetcher,'_request',return_value=(200,{},b'User-agent: *\nDisallow: /')):
            with self.assertRaisesRegex(FetchError,'robots'):
                fetcher.fetch('https://docs.espressif.com/doc')

    @patch('core.official_http.time.sleep')
    def test_missing_robots_allows_supported_document(self, _):
        fetcher=OfficialFetcher()
        with patch.object(fetcher,'_request',side_effect=[
                (404,{},b''),(200,{'content-type':'text/html; charset=utf-8'},b'<h1>Docs</h1>')]):
            result=fetcher.fetch('https://docs.espressif.com/doc')
            self.assertEqual(result.body,b'<h1>Docs</h1>')
            self.assertEqual(result.content_type,'text/html')

    def test_robots_server_failure_fails_closed(self):
        fetcher=OfficialFetcher()
        with patch.object(fetcher,'_request',return_value=(503,{},b'')):
            with self.assertRaises(FetchError):
                fetcher.fetch('https://docs.espressif.com/doc')

    def test_stream_is_bounded_without_content_length(self):
        fetcher=OfficialFetcher()
        response=MagicMock(status=200)
        response.getheaders.return_value=[]
        response.read1.return_value=b'12345'
        with patch('core.official_http.public_address',return_value='8.8.8.8'), \
             patch('core.official_http.PinnedHTTPSConnection') as connection:
            connection.return_value.getresponse.return_value=response
            with self.assertRaisesRegex(FetchError,'大小'):
                fetcher._request('https://docs.espressif.com/doc',4)
            connection.return_value.close.assert_called_once()

    def test_compressed_or_oversize_body_rejected(self):
        for headers in [[('Content-Length','999999999')],[('Content-Encoding','gzip')]]:
            response=MagicMock(status=200)
            response.getheaders.return_value=headers
            with patch('core.official_http.public_address',return_value='8.8.8.8'), \
                 patch('core.official_http.PinnedHTTPSConnection') as connection:
                connection.return_value.getresponse.return_value=response
                with self.assertRaises(FetchError):
                    OfficialFetcher()._request('https://docs.espressif.com/doc',100)

    def test_expired_deadline_stops_before_request(self):
        fetcher=OfficialFetcher(seconds=-1)
        with patch.object(fetcher,'_request') as req, self.assertRaises(FetchError):
            fetcher.fetch('https://docs.espressif.com/doc')
        req.assert_not_called()
