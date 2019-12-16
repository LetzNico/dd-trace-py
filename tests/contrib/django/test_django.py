import pytest

from ddtrace.constants import SAMPLING_PRIORITY_KEY
from ddtrace.ext import http
from ddtrace.ext.priority import USER_KEEP
from ddtrace.propagation.http import HTTP_HEADER_TRACE_ID, HTTP_HEADER_PARENT_ID, HTTP_HEADER_SAMPLING_PRIORITY
from ddtrace.propagation.utils import get_wsgi_header

import tests
from tests.contrib.patch import PatchMixin
# from .compat import reverse
from .utils import DjangoTestCase

import django


class DjangoMixin:
    """Test cases for all Django versions. For use with DjangoTestCase."""
    def test_django_request_distributed(self):
        """
        When making a request to a Django app
            With distributed tracing headers
                The django.request span properly inherits from the distributed trace
        """
        headers = {
            get_wsgi_header(HTTP_HEADER_TRACE_ID): '12345',
            get_wsgi_header(HTTP_HEADER_PARENT_ID): '78910',
            get_wsgi_header(HTTP_HEADER_SAMPLING_PRIORITY): USER_KEEP,
        }
        resp = self.client.get('/', **headers)
        assert resp.status_code == 200
        assert resp.content == b'Hello, test app.'

        # Assert we properly inherit
        # DEV: Do not use `test_spans.get_root_span()` since that expects `parent_id is None`
        root = self.test_spans.find_span(name='django.request')
        root.assert_matches(
            name='django.request',
            trace_id=12345,
            parent_id=78910,
            metrics={
                SAMPLING_PRIORITY_KEY: USER_KEEP,
            },
        )

    @pytest.mark.django_db
    def test_connection(self):
        from django.contrib.auth.models import User
        users = User.objects.count()
        assert users == 0

        spans = self.get_spans()
        # assert spans, spans
        # assert len(spans) == 1
        self.assert_span_count(1)

        span = spans[0]
        assert span.name == 'sqlite.query'
        assert span.service == 'defaultdb'
        assert span.span_type == 'sql'
        assert span.get_tag('django.db.vendor') == 'sqlite'
        assert span.get_tag('django.db.alias') == 'default'

    '''
    def test_cached_view(self):
        # make the first request so that the view is cached
        url = reverse('cached-users-list')
        response = self.client.get(url)
        assert response.status_code == 200

        # check the first call for a non-cached view
        spans = self.tracer.writer.pop()
        assert len(spans) == 6
        # the cache miss
        assert spans[1].resource == 'get'
        # store the result in the cache
        assert spans[4].resource == 'set'
        assert spans[5].resource == 'set'

        # check if the cache hit is traced
        response = self.client.get(url)
        spans = self.tracer.writer.pop()
        assert len(spans) == 3

        span_header = spans[1]
        span_view = spans[2]
        assert span_view.service == 'django'
        assert span_view.resource == 'get'
        assert span_view.name == 'django.cache'
        assert span_view.span_type == 'cache'
        assert span_view.error == 0
        assert span_header.service == 'django'
        assert span_header.resource == 'get'
        assert span_header.name == 'django.cache'
        assert span_header.span_type == 'cache'
        assert span_header.error == 0

        expected_meta_view = {
            'django.cache.backend': 'django.core.cache.backends.locmem.LocMemCache',
            'django.cache.key': (
                'views.decorators.cache.cache_page..'
                'GET.03cdc1cc4aab71b038a6764e5fcabb82.d41d8cd98f00b204e9800998ecf8427e.en-us'
            ),
            'env': 'test',
        }

        expected_meta_header = {
            'django.cache.backend': 'django.core.cache.backends.locmem.LocMemCache',
            'django.cache.key': 'views.decorators.cache.cache_header..03cdc1cc4aab71b038a6764e5fcabb82.en-us',
            'env': 'test',
        }

        assert span_view.meta == expected_meta_view
        assert span_header.meta == expected_meta_header

    def test_cached_template(self):
        # make the first request so that the view is cached
        url = reverse('cached-template-list')
        response = self.client.get(url)
        assert response.status_code == 200

        # check the first call for a non-cached view
        spans = self.tracer.writer.pop()
        assert len(spans) == 5
        # the cache miss
        assert spans[2].resource == 'get'
        # store the result in the cache
        assert spans[4].resource == 'set'

        # check if the cache hit is traced
        response = self.client.get(url)
        spans = self.tracer.writer.pop()
        assert len(spans) == 3

        span_template_cache = spans[2]
        assert span_template_cache.service == 'django'
        assert span_template_cache.resource == 'get'
        assert span_template_cache.name == 'django.cache'
        assert span_template_cache.span_type == 'cache'
        assert span_template_cache.error == 0

        expected_meta = {
            'django.cache.backend': 'django.core.cache.backends.locmem.LocMemCache',
            'django.cache.key': 'template.cache.users_list.d41d8cd98f00b204e9800998ecf8427e',
            'env': 'test',
        }

        assert span_template_cache.meta == expected_meta
        assert 0
    '''


@pytest.mark.skipif(django.VERSION < (2, 0, 0), reason='')
class TestDjango2App(DjangoTestCase, PatchMixin, DjangoMixin):
    APP_NAME = 'django_app'

    def test_patched(self):
        self.assert_wrapped(django.apps.registry.Apps.populate)
        self.assert_wrapped(django.core.handlers.base.BaseHandler.load_middleware)

    def test_middleware_patching(self):
        # Test that various middlewares that are included are patched
        self.assert_wrapped(django.middleware.common.CommonMiddleware.process_request)
        self.assert_wrapped(django.middleware.security.SecurityMiddleware.process_request)

        # Test that each middleware hook is patched
        self.assert_wrapped(tests.contrib.django.middleware.EverythingMiddleware.process_response)
        self.assert_wrapped(tests.contrib.django.middleware.EverythingMiddleware.process_request)
        self.assert_wrapped(tests.contrib.django.middleware.EverythingMiddleware.process_view)
        self.assert_wrapped(tests.contrib.django.middleware.EverythingMiddleware.process_template_response)
        self.assert_wrapped(tests.contrib.django.middleware.EverythingMiddleware.process_exception)
        self.assert_wrapped(tests.contrib.django.middleware.fn_middleware(None))

    def test_django_200_request_root_span(self):
        """
        When making a request to a Django app
            We properly create the `django.request` root span
        """
        resp = self.client.get('/')
        assert resp.status_code == 200
        assert resp.content == b'Hello, test app.'

        spans = self.get_spans()
        # Assert the correct number of traces and spans
        assert len(spans) == 26

        # Assert the structure of the root `django.request` span
        root = self.get_root_span()

        if django.VERSION >= (2, 2, 0):
            resource = 'GET ^$'
        else:
            resource = 'GET tests.contrib.django.views.index'

        meta = {
            'django.request.class': 'django.core.handlers.wsgi.WSGIRequest',
            'django.response.class': 'django.http.response.HttpResponse',
            'django.view': 'tests.contrib.django.views.index',
            'http.method': 'GET',
            'http.status_code': '200',
            'http.url': 'http://testserver/',
        }
        if django.VERSION >= (2, 2, 0):
            meta['http.route'] = '^$'

        root.assert_matches(
            name='django.request',
            service='django',
            resource=resource,
            parent_id=None,
            span_type=http.TYPE,
            error=0,
            meta=meta,
        )

    def test_django_request_middleware(self):
        """
        When making a request to a Django app
            We properly create the `django.middleware` spans
        """
        resp = self.client.get('/')
        assert resp.status_code == 200
        assert resp.content == b'Hello, test app.'

        # Assert the correct number of traces and spans
        self.test_spans.assert_span_count(26)

        # Get all the `django.middleware` spans in this trace
        middleware_spans = list(self.test_spans.filter_spans(name='django.middleware'))
        assert len(middleware_spans) == 24

        # Assert common span structure
        for span in middleware_spans:
            span.assert_matches(
                name='django.middleware',
                service='django',
                error=0,
                span_type=None,
            )

        span_resources = {
            'django.contrib.auth.middleware.AuthenticationMiddleware.__call__',
            'django.contrib.auth.middleware.AuthenticationMiddleware.process_request',
            'django.contrib.messages.middleware.MessageMiddleware.__call__',
            'django.contrib.messages.middleware.MessageMiddleware.process_request',
            'django.contrib.messages.middleware.MessageMiddleware.process_response',
            'django.contrib.sessions.middleware.SessionMiddleware.__call__',
            'django.contrib.sessions.middleware.SessionMiddleware.process_request',
            'django.contrib.sessions.middleware.SessionMiddleware.process_response',
            'django.middleware.clickjacking.XFrameOptionsMiddleware.__call__',
            'django.middleware.clickjacking.XFrameOptionsMiddleware.process_response',
            'django.middleware.common.CommonMiddleware.__call__',
            'django.middleware.common.CommonMiddleware.process_request',
            'django.middleware.common.CommonMiddleware.process_response',
            'django.middleware.csrf.CsrfViewMiddleware.__call__',
            'django.middleware.csrf.CsrfViewMiddleware.process_request',
            'django.middleware.csrf.CsrfViewMiddleware.process_response',
            'django.middleware.csrf.CsrfViewMiddleware.process_view',
            'django.middleware.security.SecurityMiddleware.__call__',
            'django.middleware.security.SecurityMiddleware.process_request',
            'django.middleware.security.SecurityMiddleware.process_response',
            'tests.contrib.django.middleware.ClsMiddleware.__call__',
            'tests.contrib.django.middleware.EverythingMiddleware',
            'tests.contrib.django.middleware.EverythingMiddleware.__call__',
            'tests.contrib.django.middleware.EverythingMiddleware.process_view'
        }
        assert set([s.resource for s in middleware_spans]) == span_resources

        # Get middleware spans in reverse order of start time
        middleware_spans = sorted(middleware_spans, key=lambda s: s.start, reverse=True)

        # Assert the first middleware span's parent is the root span (django.request)
        root_span = self.test_spans.get_root_span()
        assert root_span.name == 'django.request'
        first_middleware = middleware_spans[-1]
        assert first_middleware.parent_id == root_span.span_id

    def test_request_view(self):
        """
        When making a request to a Django app
            We properly create the `django.view` span
        """
        resp = self.client.get('/')
        assert resp.status_code == 200
        assert resp.content == b'Hello, test app.'

        # Assert the correct number of traces and spans
        self.assert_span_count(26)

        view_spans = list(self.test_spans.filter_spans(name='django.view'))
        assert len(view_spans) == 1

        # Assert span properties
        view_span = view_spans[0]
        view_span.assert_matches(
            name='django.view',
            service='django',
            resource='tests.contrib.django.views.index',
            error=0,
        )


@pytest.mark.skipif(django.VERSION >= (2, 0, 0), reason='')
class TestDjango1App(DjangoTestCase, PatchMixin, DjangoMixin):
    APP_NAME = 'django1_app'

    def test_middleware_patching(self):
        # Test that various middlewares that are included are patched
        self.assert_wrapped(django.middleware.common.CommonMiddleware.process_request)
        self.assert_wrapped(django.middleware.security.SecurityMiddleware.process_request)

        # Test that each middleware hook is patched
        self.assert_wrapped(tests.contrib.django.middleware.CatchExceptionMiddleware.process_exception)

    def test_middleware(self):
        resp = self.client.get('/')
        assert resp.status_code == 200
        assert resp.content == b'Hello, test app.'

        # Assert the correct number of traces and spans
        if django.VERSION < (1, 11, 0):
            self.test_spans.assert_span_count(15)
        else:
            self.test_spans.assert_span_count(16)

        # Get all the `django.middleware` spans in this trace
        middleware_spans = list(self.test_spans.filter_spans(name='django.middleware'))
        if django.VERSION < (1, 11, 0):
            assert len(middleware_spans) == 13
        else:
            assert len(middleware_spans) == 14

        root = self.test_spans.get_root_span()
        root.assert_matches(name='django.request')

        # Assert common span structure
        for span in middleware_spans:
            span.assert_matches(
                name='django.middleware',
                service='django',
                error=0,
                span_type=None,
                parent_id=root.span_id,  # They are all children of the root django.request
            )

        # DEV: Order matters here, we want all `process_request` before `process_view`, before `process_response`
        expected_resources = [
            'django.contrib.sessions.middleware.SessionMiddleware.process_request',
            'django.middleware.common.CommonMiddleware.process_request',
            'django.middleware.csrf.CsrfViewMiddleware.process_request',  # Not in < 1.11.0
            'django.contrib.auth.middleware.AuthenticationMiddleware.process_request',
            'django.contrib.auth.middleware.SessionAuthenticationMiddleware.process_request',
            'django.contrib.messages.middleware.MessageMiddleware.process_request',
            'django.middleware.security.SecurityMiddleware.process_request',
            'django.middleware.csrf.CsrfViewMiddleware.process_view',
            'django.middleware.security.SecurityMiddleware.process_response',
            'django.middleware.clickjacking.XFrameOptionsMiddleware.process_response',
            'django.contrib.messages.middleware.MessageMiddleware.process_response',
            'django.middleware.csrf.CsrfViewMiddleware.process_response',
            'django.middleware.common.CommonMiddleware.process_response',
            'django.contrib.sessions.middleware.SessionMiddleware.process_response',
        ]
        if django.VERSION < (1, 11, 0):
            expected_resources.remove('django.middleware.csrf.CsrfViewMiddleware.process_request')
        middleware_spans = sorted(middleware_spans, key=lambda s: s.start)
        span_resources = [s.resource for s in middleware_spans]
        assert span_resources == expected_resources