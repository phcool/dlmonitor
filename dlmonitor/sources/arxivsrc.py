import os, sys
from ..db import create_engine
from .base import Source
from sqlalchemy_searchable import search
from sqlalchemy import desc
import time
from time import mktime
from datetime import datetime
import logging
import arxiv

SEARCH_KEY = "cat:cs.CV+OR+cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML"
MAX_QUERY_NUM = 10000

class ArxivSource(Source):

    def _get_version(self, arxiv_url):
        version = 1
        last_part = arxiv_url.split("/")[-1]
        if "v" in last_part:
            version = int(last_part.split("v")[-1])
        return version

    def get_one_post(self, arxiv_id):
        from ..db import get_global_session, ArxivModel
        session = get_global_session()
        query = session.query(ArxivModel).filter(ArxivModel.id == int(arxiv_id))
        results = query.all()
        if results:
            return results[0]
        else:
            return None

    def get_posts(self, keywords=None, since=None, start=0, num=20):
        from ..db import get_global_session, ArxivModel
        if keywords:
            keywords = keywords.strip()
        session = get_global_session()
        query = session.query(ArxivModel)
        if since:
            # Filter date
            assert isinstance(since, str)
            query = query.filter(ArxivModel.published_time >= since)
        if not keywords or keywords.lower() == 'fresh papers':
            # Recent papers
            results = (query.order_by(desc(ArxivModel.published_time))
                       .offset(start).limit(num).all())
        elif keywords.lower() == 'hot papers':
            results = (query.order_by(desc(ArxivModel.popularity))
                              .offset(start).limit(num).all())
        else:
            # search_kw = " or ".join(["({})".format(x) for x in keywords.split(",")])
            search_kw = " or ".join(keywords.split(","))
            searched_query = search(query, search_kw, sort=True)
            results = searched_query.offset(start).limit(num).all()
        return results

    def fetch_new(self):
        """
        Fetch new papers from arXiv and store them in the database.
        This implementation directly uses the arxiv library instead of calling query_arxiv.
        """
        from ..db import session_scope, ArxivModel
        
        # Create client with appropriate configuration
        client = arxiv.Client(
            page_size=100,  # Each API call will fetch 100 results
            delay_seconds=3,  # Wait 3 seconds between API calls to be nice to the server
            num_retries=3    # Retry failed requests up to 3 times
        )
        
        # Format the search query correctly
        formatted_query = SEARCH_KEY.replace("+OR+", " OR ")
        
        with session_scope() as session:
            # Instead of fetching in batches with multiple API calls,
            # we'll make a single search with a larger max_results
            # Use MAX_QUERY_NUM but limit to a reasonable value to avoid memory issues
            max_results = min(MAX_QUERY_NUM, 2000)  # Limit to 2000 to avoid memory issues
            
            search_query = arxiv.Search(
                query=formatted_query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.LastUpdatedDate
            )
            
            logging.info(f"Fetching up to {max_results} papers from arXiv...")
            
            try:
                # Get results iterator
                results_iterator = client.results(search_query)
                
                # Process results in batches to avoid memory issues
                batch_size = 100
                batch = []
                total_new = 0
                consecutive_empty_batches = 0  # Track consecutive batches with no new papers
                
                # Process first 200 results (2 pages) which are usually reliable
                for i, result in enumerate(results_iterator):
                    # Process in batches
                    batch.append(result)
                    
                    if len(batch) >= batch_size or i == max_results - 1:  # Process batch or last item
                        logging.info(f"Processing batch of {len(batch)} papers...")
                        
                        anything_new = False  # Reset for each batch
                        for paper in batch:
                            arxiv_url = paper.entry_id
                            
                            # Check if paper already exists in database
                            if session.query(ArxivModel).filter_by(arxiv_url=arxiv_url).count() == 0:
                                anything_new = True
                                total_new += 1
                                
                                # Create new paper record
                                new_paper = ArxivModel(
                                    arxiv_url=arxiv_url,
                                    version=self._get_version(arxiv_url),
                                    title=paper.title.replace("\n", "").replace("  ", " "),
                                    abstract=paper.summary.replace("\n", "").replace("  ", " "),
                                    pdf_url=paper.pdf_url,
                                    authors=", ".join([author.name for author in paper.authors])[:800],
                                    published_time=datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                                    journal_link=paper.journal_ref if hasattr(paper, "journal_ref") else "",
                                    tag=" | ".join(paper.categories),
                                    popularity=0
                                )
                                session.add(new_paper)
                        
                        # Commit batch and clear
                        session.commit()
                        
                        # Update consecutive empty batches counter
                        if anything_new:
                            consecutive_empty_batches = 0  # Reset counter if we found new papers
                        else:
                            consecutive_empty_batches += 1
                        
                        batch = []
                        
                        # If we've processed at least 100 papers and had 3 consecutive batches with no new papers, we can stop
                        if i >= 100 and consecutive_empty_batches >= 3:
                            logging.info(f"No new papers found in {consecutive_empty_batches} consecutive batches. Stopping.")
                            break
                
            except arxiv.UnexpectedEmptyPageError as e:
                # Handle empty page error - this is common with arXiv API
                logging.warning(f"Received empty page from arXiv API: {str(e)}")
                logging.info("This is a common issue with the arXiv API. Processing will continue with the data already fetched.")
                
                # Process any remaining papers in the batch
                if batch:
                    logging.info(f"Processing final batch of {len(batch)} papers...")
                    
                    anything_new = False
                    for paper in batch:
                        arxiv_url = paper.entry_id
                        
                        # Check if paper already exists in database
                        if session.query(ArxivModel).filter_by(arxiv_url=arxiv_url).count() == 0:
                            anything_new = True
                            total_new += 1
                            
                            # Create new paper record
                            new_paper = ArxivModel(
                                arxiv_url=arxiv_url,
                                version=self._get_version(arxiv_url),
                                title=paper.title.replace("\n", "").replace("  ", " "),
                                abstract=paper.summary.replace("\n", "").replace("  ", " "),
                                pdf_url=paper.pdf_url,
                                authors=", ".join([author.name for author in paper.authors])[:800],
                                published_time=datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                                journal_link=paper.journal_ref if hasattr(paper, "journal_ref") else "",
                                tag=" | ".join(paper.categories),
                                popularity=0
                            )
                            session.add(new_paper)
                    
                    # Commit final batch
                    session.commit()
            
            except Exception as e:
                # Handle other exceptions
                logging.error(f"Error fetching papers from arXiv: {str(e)}")
                # Re-raise the exception if it's not an empty page error
                raise
            
            logging.info(f"Finished fetching papers. Added {total_new} new papers.")
            
            return total_new > 0  # Return True if any new papers were added
