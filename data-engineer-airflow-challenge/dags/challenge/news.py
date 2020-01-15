"""Extract data from NewsAPI and upload it to S3."""
import collections
import csv
import logging
import os

import boto3
import newsapi
import readability


class NewsApiClient:
    """Provide a logic-wrapper around the NewsAPI client."""

    def __init__(self, api_key):
        self._client = newsapi.NewsApiClient(api_key)

    def get_sources(self, language=None):
        """Return a list of news sources with an optional language spec."""
        source_list = []
        sources = self._client.get_sources(language=language)
        for source in sources["sources"]:
            source_list.append(source["id"])
        return source_list

    def _paged_search(self, page_size=100, top=True, **kwargs):
        """Perform a paged search of the NewsAPI.

        This is a genericized method which containes the logic for handling
        a number of different requests.   Based upon whether or not we are
        called with the `top` parameter being true we will either get the
        top headlines or perform a full database search.

        The following additional query parameters can be passed in as keyword
        arguments and will be forwarded to the NewsAPI query if present:

        * language
        * query
        * sources

        Since this is not meant to be a public function we're going to skip
        doing any combinatorial sanity checks on the passed arguments.  The
        specific implementations below will take care of that.

        The return value is a generator which will yield one article from the
        news API every time it is polled.  If the maximum number of results in
        a query is hit (100 for a dev API key) we will cap the returns at 100
        and log a warning about it.  Any other exceptions from NewsAPI get
        re-raised.
        """
        language = kwargs.get("language")
        query = kwargs.get("query")
        sources = kwargs.get("sources", [])
        source_string = ",".join(sources)

        if top:
            search_method = self._client.get_top_headlines
        else:
            search_method = self._client.get_everything

        articles = []
        current_page = 1
        while True:
            try:
                page = search_method(
                    language=language,
                    q=query,
                    sources=source_string,
                    page=current_page,
                    page_size=page_size,
                )
            except newsapi.newsapi_exception.NewsAPIException as exc:
                if exc.get_code() == "maximumResultsReached":
                    logging.warning("Reached maximum query results.")
                    break
                else:
                    raise exc
            if len(page["articles"]):
                articles.extend(page["articles"])
                current_page += 1
            else:
                break

        for article in articles:
            yield article

    def top_stories(self, sources=[], language="en"):
        """Perform a `get_top_headlines` search on NewsAPI.

        A list of sources is optional.  If provided the logic in _paged_search
        will concatenate the array into a list to match the API' requirements.
        """
        return self._paged_search(language=language, sources=sources)

    def search(self, query, sources=[], language=None):
        """Perform a `get_everything` search on NewsAPI.

        A list of sources is optional.  If provided the logic in _paged_search
        will concatenate the array into a list to match the API' requirements.
        """
        return self._paged_search(
            top=False, query=query, language=language, sources=sources
        )


def story_grade(story):
    """Get the Kincaid readability score of a story.

    We only have partial text of a story in its content, so rather than claim
    to be grading the story itself we're just scoring the readability of the
    description.  It's not the most useful transform, but it's something to do
    that doesn't have high overhead.

    Takes a story object from NewsAPI and returns a float.
    """
    grade = 0.0
    text = story.get("description")
    if text:
        try:
            grade = readability.getmeasures(text, lang="en")[
                "readability grades"
            ]["Kincaid"]
        except ValueError:
            pass
    return grade


def write_csv(fh, stories):
    """Write stories in CSV form to an open file handle."""
    writer = csv.writer(fh)
    for story in stories:
        # we want to use the source's ID key if it's present so that we have
        # a valid reference that can be used in other queries against the API,
        # but some sources that the `get_everything` search returns only have
        # a source name, not an ID.   If we're missing the ID we'll use the
        # name just so we have _some_ data in that colume.
        source_id = story["source"]["id"]
        if not source_id or len(source_id) == 0:
            source_id = story["source"]["name"]
        writer.writerow(
            (
                source_id,
                story["title"],
                story["publishedAt"],
                story["url"],
                "{0:.2f}".format(story_grade(story)),
            )
        )


def upload_news(filepath, bucket, key):
    """Upload a given file to S3.

    As noted in the README, we are just using boto3's standard credential
    resolution mechanisms.  If this were the real world, a better solution
    might be to add the connection in Airflow and reference that using
    Airflow's S3 hook.  That's a lot of overhead for this test case though.
    """
    s3 = boto3.client("s3")
    s3.upload_file(filepath, bucket, key)


def stories_by_source(stories):
    """Provide a collection of stories ordered by source.

    The return of the NewsAPi search for multiple sources is not sorted by
    source.  Since we want to provide a file for each source thir function
    will iterate through the list and return a defaultdict keyed by each
    source's ID string.
    """
    by_source = collections.defaultdict(list)
    for story in stories:
        source = story["source"]["id"]
        by_source[source].append(story)
    return by_source


def generate_headlines(tmpdir, bucket, apikey, **context):
    """Generate a set of headlines.

    The Airflow context is used to determine the execution date for the
    creation of filenames.
    """
    client = NewsApiClient(apikey)
    logging.info("Getting headlines source list.")
    sources = client.get_sources(language="en")
    logging.info(f"Using sources: '{sources}'")
    stories = client.top_stories(sources=sources)
    by_source = stories_by_source(stories)

    for source in by_source:
        logging.info(f"Processing source '{source}'")
        filename = "{}_top_headlines.csv".format(context["ds"])
        filepath = os.path.join(tmpdir, f"{source}_{filename}")
        logging.info(f"Writing headlines to {filepath}")
        with open(filepath, "w") as fh:
            write_csv(fh, by_source[source])
        logging.info(
            f"Uploading headlines from {filepath} to {bucket}/{source}"
        )
        upload_news(filepath, bucket, f"{source}/{filename}")
        logging.info(f"Processing '{source}' complete")


def search_news(tmpdir, bucket, terms, apikey, **context):
    """Search NewsAPI for any number of search terms.

    This takes a list of search terms and runs a distinct search for each one.
    This uses a few more API calls, but gives us more results, and also saves
    from having to do munging of a compound query string to make sure it
    parses cleanly.

    The Airflow context is used to determine the execution date for the
    creation of file names.
    """
    client = NewsApiClient(apikey)
    filename = "{}_combined_search.csv".format(context["ds"])
    filepath = os.path.join(tmpdir, filename)
    all_stories = []
    for term in terms:
        logging.info(f"Perfoming search for '{term}")
        all_stories.extend(client.search(query=term))
    logging.info(f"Writing search results to {filepath}")
    with open(filepath, "w") as fh:
        write_csv(fh, all_stories)
    logging.info(f"Uploading {filepath} to {bucket}")
    upload_news(filepath, bucket, filename)
    logging.info("Complete.")
