# Tempus Data Engineer Challenge Solution
This is my solution to the Airflow challenge.

I have chosen to implement both the "basic" headlines requirement and the 
extra-credit "search" feature.   I did take the simple approach to the search
feature and ran individual searches rather than combining multiple search
terms into one parsable string -- hopefully that won't count too much against
me! :)

It wasn't quite clear from the instructions whether you wanted an *additional*
transform on the data beyond chunking and subdividing into into CSVs.  Just to
be safe there I decided to enrich each story with an additional attribute
containing the Kincaid reading level score of the story's description.  It's a
little silly, but it's something.

A full suite of unit tests were written to cover the `news.py` module I
created, and pytest shows 72% test coverage on that file.  The bulk of the
uncovered code is in the two "handler" functions that Airflow invokes which
would be a bit ugly to test cleanly without much additional benefit.

On the whole I think I have done most of the error checking that makes sense
in something of this scope.   Expected exceptions from NewsAPI or the
readability library have been handled already, while any gross failures will
be raised up the stack.  I have made a conscious decision not to unlink
our temporary files when we're done with them.  This will allow them to
persist in the scratch-space so they can be examed after potential failures,
should that be useful.  This could easily be changed if that's not desired
behavior.

One area that could benefit would be to add a bit more verification around
the upload of the files to S3 -- reading them back and doing a checksum to
verify accuracy might be a good future enhancement, for example.  Another
area for growth there would be cleaner handling of protocol-level failures
from boto3.   At this point a single failed upload will fail the entire process,
but we might want to allow as many as possible succeed and report on failures
at the end so we know about them.

For AWS interactions I decided to let boto3 use its own standard credential
resolution method, so it'll check `~/.aws`, environment variables, and all
the usual locations.   For the purpose of running this via Docker I have added
the three standard AWS environment variables to the `docker-compose` file, so
as long as those are set in your environment they should be passed in.

In a "real world" solution, the better method would be either to add AWS
credentials as a configured connection in Airflow and use its own S3 hooks, or
simply to use IAM roles if you're running your workers in AWS space.  Neither
of those is suitable for this self-contained solution though.

I have used `black`, my preferred python code formatter, on this code.  It 
does convert single quotes to double, so I know that some of the existing
quotes may have been changed.  I also made a few additions to the `.gitignore`
to make it work with my workflow.  Those should be the only two notable changes
to the original outside my own additions.

I also made sure that `make lint` finished clean, and ran `pydocstyle` on the
`news.py` source file to ensure that that was commented sensibly.

## Execution
Two variables must be set in your environment for this to fully work.  They
shoud be fairly self-explanatory:

* TEMPUS_DAG_S3_BUCKET
* TEMPUS_DAG_NEWSAPI_KEY

Additionally you will likely want to set AWS credentials and a default region
in your environment so that they will be availiable in the docker containers:

* AWS_ACCESS_KEY_ID
* AWS_SECRET_ACCESS_KEY
* AWS_DEFAULT_REGION
  
With those present, `make run` should be sufficient to make magic happen.

## That's all folks!
Thanks for your time and consideration.