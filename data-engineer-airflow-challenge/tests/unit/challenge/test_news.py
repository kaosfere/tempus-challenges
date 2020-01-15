import io
from unittest import mock

import newsapi
import pytest
from dags.challenge import news


class MockApi:
    def __init__(self, api_key):
        self.count = 0

    def get_top_headlines(self, **kwargs):
        if self.count == 0:
            self.count += 1
            return {"articles": [{"title": "headlines"}]}
        else:
            return {"articles": []}

    def get_everything(self, **kwargs):
        if self.count == 0:
            self.count += 1
            return {"articles": [{"title": "everything"}]}
        else:
            return {"articles": []}


def mock_max_results_exception(*args, **kwargs):
    exception = newsapi.newsapi_exception.NewsAPIException(Exception())
    exception.get_code = lambda: "maximumResultsReached"
    return exception


def mock_generic_exception(*args, **kwargs):
    exception = newsapi.newsapi_exception.NewsAPIException(Exception())
    exception.get_code = lambda: "dummycode"
    return exception


@mock.patch("newsapi.NewsApiClient.get_sources")
def test_get_sources(mock_client):
    mock_client.return_value = {"sources": [{"id": "foo"}, {"id": "bar"}]}
    expected_sources = ["foo", "bar"]
    client = news.NewsApiClient("dummykey")
    assert client.get_sources() == expected_sources


@mock.patch("newsapi.NewsApiClient")
def test_top_headlines(mock_client):
    mock_client.return_value = MockApi("dummykey")
    client = news.NewsApiClient("dummykey")
    search = client.top_stories(language="en")
    assert next(search)["title"] == "headlines"
    with pytest.raises(StopIteration):
        next(search)


@mock.patch("newsapi.NewsApiClient")
def test_search(mock_client):
    mock_client.return_value = MockApi("dummykey")
    client = news.NewsApiClient("dummykey")
    search = client.search(query="dummy")
    assert next(search)["title"] == "everything"
    with pytest.raises(StopIteration):
        next(search)


@mock.patch(
    "newsapi.NewsApiClient.get_top_headlines",
    side_effect=mock_max_results_exception(),
)
def test_max_results(mock_api):
    client = news.NewsApiClient("dummykey")
    search = client._paged_search(language="en")
    with pytest.raises(StopIteration):
        next(search)


@mock.patch(
    "newsapi.NewsApiClient.get_top_headlines",
    side_effect=mock_generic_exception(),
)
def test_other_errors(mock_api):
    client = news.NewsApiClient("dummykey")
    search = client._paged_search(language="en")
    with pytest.raises(newsapi.newsapi_exception.NewsAPIException):
        next(search)


@mock.patch("dags.challenge.news.NewsApiClient.top_stories")
def test_writer(mock_api):
    mock_api.return_value = [
        {
            "source": {"id": "sourceid", "name": "sourcename"},
            "title": "headlines",
            "publishedAt": "now",
            "url": "url",
        }
    ]
    client = news.NewsApiClient("dummykey")
    output = io.StringIO()
    news.write_csv(output, client.top_stories())
    assert output.getvalue().strip() == "sourceid,headlines,now,url,0.00"

    # Also test the case where a source has a name but no ID.
    mock_api.return_value = [
        {
            "source": {"id": None, "name": "sourcename"},
            "title": "headlines",
            "publishedAt": "now",
            "url": "url",
        }
    ]
    output = io.StringIO()
    news.write_csv(output, client.top_stories())
    assert output.getvalue().strip() == "sourcename,headlines,now,url,0.00"


def test_stories_by_source():
    stories = [
        {"source": {"id": "foo"}, "body": "story1"},
        {"source": {"id": "foo"}, "body": "story2"},
        {"source": {"id": "bar"}, "body": "story3"},
    ]

    expected = {
        "foo": [
            {"source": {"id": "foo"}, "body": "story1"},
            {"source": {"id": "foo"}, "body": "story2"},
        ],
        "bar": [{"source": {"id": "bar"}, "body": "story3"}],
    }

    assert news.stories_by_source(stories) == expected


def test_story_grade():
    assert (
        "{0:.2f}".format(
            news.story_grade({"description": "Sample Description"})
        )
        == "8.79"
    )

    # Test that we get a synthetic score of 0 if the text can't be parsed
    # by readability, instead of throwing a ValueError
    assert "{0:.2f}".format(news.story_grade({"description": "..."})) == "0.00"
