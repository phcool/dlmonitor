import os, sys
from ..db import create_engine
from .paper_source import PaperSource
from sqlalchemy_searchable import search
from sqlalchemy import desc, func
import time
from time import mktime
from datetime import datetime
import logging
import arxiv
from sentence_transformers import SentenceTransformer
import numpy as np
from pgvector.sqlalchemy import Vector

SEARCH_KEY = "cat:cs.CV+OR+cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML"

class ArxivSource(PaperSource):
    """
    Source for fetching and searching arXiv papers.
    """
    
    def __init__(self):
        super(ArxivSource, self).__init__()
        self.source_name = "arxiv"

    def _get_version(self, arxiv_url):
        """Extract version number from arXiv URL"""
        version = 1
        last_part = arxiv_url.split("/")[-1]
        if "v" in last_part:
            version = int(last_part.split("v")[-1])
        return version
    
    def _get_model_class(self):
        """Get the ArxivModel class for database operations"""
        from ..db import ArxivModel
        return ArxivModel

    def fetch_new(self, model=None):
        """
        Fetch new papers from arXiv and store them in the database.
        This implementation directly uses the arxiv library.
        Also generates embeddings for new papers using sentence-transformers.
        
        Args:
            model: Pre-loaded SentenceTransformer model instance
            
        Returns:
            bool: True if new papers were found, False otherwise
        """
        from ..db import session_scope, ArxivModel
        
        # Use the provided model or load a new one
        if model is None:
            model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Create client with appropriate configuration
        client = arxiv.Client(
            page_size=100,  # Each API call will fetch 100 results
            delay_seconds=3,  # Wait 3 seconds between API calls to be nice to the server
            num_retries=3    # Retry failed requests up to 3 times
        )
        
        # Format the search query correctly
        formatted_query = SEARCH_KEY.replace("+OR+", " OR ")
        
        self.logger.info(f"开始从arXiv获取论文...")
        
        with session_scope() as session:
            # Use max_results value from parent class
            max_results = min(self.MAX_PAPERS_PER_SOURCE, 2000)
            
            search_query = arxiv.Search(
                query=formatted_query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.LastUpdatedDate
            )
            
            try:
                # Get results iterator
                results_iterator = client.results(search_query)
                
                # Process results in batches to avoid memory issues
                batch_size = 32
                batch = []
                total_new = 0
                total_fetched = 0
                consecutive_empty_batches = 0
                papers_per_category = {}  # Track papers per category
                
                # Process results
                for i, result in enumerate(results_iterator):
                    # Add to current batch
                    batch.append(result)
                    total_fetched += 1
                    
                    if len(batch) >= batch_size or i == max_results - 1 or total_fetched >= self.MAX_PAPERS_PER_SOURCE:
                        # Check which papers already exist
                        arxiv_urls = [paper.entry_id for paper in batch]
                        existing_urls = {url[0] for url in session.query(ArxivModel.arxiv_url).filter(ArxivModel.arxiv_url.in_(arxiv_urls)).all()}
                        
                        # Prepare data for new papers
                        new_papers = []
                        
                        anything_new = False
                        for paper in batch:
                            arxiv_url = paper.entry_id
                            
                            # Track papers by category
                            for category in paper.categories:
                                if category not in papers_per_category:
                                    papers_per_category[category] = 0
                                papers_per_category[category] += 1
                            
                            # Only process new papers
                            if arxiv_url not in existing_urls:
                                anything_new = True
                                total_new += 1
                                
                                # Prepare paper data
                                paper_data = {
                                    'title': paper.title.replace("\n", "").replace("  ", " "),
                                    'abstract': paper.summary.replace("\n", "").replace("  ", " "),
                                    'authors': ", ".join([author.name for author in paper.authors])[:800],
                                    'arxiv_url': arxiv_url,
                                    'version': self._get_version(arxiv_url),
                                    'pdf_url': paper.pdf_url,
                                    'published_time': datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                                    'journal_link': paper.journal_ref if hasattr(paper, "journal_ref") else "",
                                    'tag': " | ".join(paper.categories),
                                    'popularity': 0
                                }
                                
                                # Process paper data and generate embedding
                                processed_data, embedding = self._process_paper_metadata(paper_data, model)
                                
                                # Create new paper record
                                new_paper = ArxivModel(
                                    arxiv_url=processed_data['arxiv_url'],
                                    version=processed_data['version'],
                                    title=processed_data['title'],
                                    abstract=processed_data['abstract'],
                                    pdf_url=processed_data['pdf_url'],
                                    authors=processed_data['authors'],
                                    published_time=processed_data['published_time'],
                                    journal_link=processed_data['journal_link'],
                                    tag=processed_data['tag'],
                                    popularity=processed_data['popularity'],
                                    embedding=embedding
                                )
                                
                                new_papers.append(new_paper)
                        
                        # Add new papers to session
                        if new_papers:
                            for new_paper in new_papers:
                                session.add(new_paper)
                            
                        # Commit batch
                        session.commit()
                        
                        # Update consecutive empty batches counter
                        if anything_new:
                            consecutive_empty_batches = 0
                        else:
                            consecutive_empty_batches += 1
                        
                        batch = []
                        
                        # Check if we have enough papers for each main category
                        main_categories_satisfied = True
                        for main_cat in ["cs.CV", "cs.AI", "cs.LG", "cs.CL"]:
                            if main_cat not in papers_per_category or papers_per_category[main_cat] < self.MIN_PAPERS_PER_TOPIC:
                                main_categories_satisfied = False
                                break
                        
                        # Stop conditions
                        if total_fetched >= self.MAX_PAPERS_PER_SOURCE:
                            break
                        
                        if i >= 100 and consecutive_empty_batches >= 3:
                            break
                        
                        if i >= 500 and main_categories_satisfied:
                            break
                
            except arxiv.UnexpectedEmptyPageError as e:
                # Handle empty page error - common with arXiv API
                self.logger.warning(f"获取arXiv数据时出现空页面错误: {str(e)}")
                
                # Process any remaining papers in the batch
                if batch:
                    total_new = self._process_remaining_batch(session, batch, model, total_new)
            
            except Exception as e:
                # Handle other exceptions
                self.logger.error(f"获取arXiv论文时出错: {str(e)}")
                raise
            
            # 简单统计主要类别的论文数量
            main_cats_count = sum(papers_per_category.get(cat, 0) for cat in ["cs.CV", "cs.AI", "cs.LG", "cs.CL", "cs.NE"])
            
            self.logger.info(f"arXiv论文获取完成。共获取{total_fetched}篇论文，其中新增{total_new}篇。机器学习及相关类别共{main_cats_count}篇。")
            
            return total_new > 0
    
    def _process_remaining_batch(self, session, batch, model, total_new):
        """Process remaining papers in the batch after an exception"""
        from ..db import ArxivModel
        
        # Check which papers already exist
        arxiv_urls = [paper.entry_id for paper in batch]
        existing_urls = {url[0] for url in session.query(ArxivModel.arxiv_url).filter(ArxivModel.arxiv_url.in_(arxiv_urls)).all()}
        
        # Prepare data for new papers
        new_papers = []
        new_count = total_new
        
        for paper in batch:
            arxiv_url = paper.entry_id
            
            # Only process new papers
            if arxiv_url not in existing_urls:
                new_count += 1
                
                # Prepare paper data
                paper_data = {
                    'title': paper.title.replace("\n", "").replace("  ", " "),
                    'abstract': paper.summary.replace("\n", "").replace("  ", " "),
                    'authors': ", ".join([author.name for author in paper.authors])[:800],
                    'arxiv_url': arxiv_url,
                    'version': self._get_version(arxiv_url),
                    'pdf_url': paper.pdf_url,
                    'published_time': datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                    'journal_link': paper.journal_ref if hasattr(paper, "journal_ref") else "",
                    'tag': " | ".join(paper.categories),
                    'popularity': 0
                }
                
                # Process paper data and generate embedding
                processed_data, embedding = self._process_paper_metadata(paper_data, model)
                
                # Create new paper record
                new_paper = ArxivModel(
                    arxiv_url=processed_data['arxiv_url'],
                    version=processed_data['version'],
                    title=processed_data['title'],
                    abstract=processed_data['abstract'],
                    pdf_url=processed_data['pdf_url'],
                    authors=processed_data['authors'],
                    published_time=processed_data['published_time'],
                    journal_link=processed_data['journal_link'],
                    tag=processed_data['tag'],
                    popularity=processed_data['popularity'],
                    embedding=embedding
                )
                
                new_papers.append(new_paper)
        
        # Add new papers to session
        if new_papers:
            for new_paper in new_papers:
                session.add(new_paper)
            
        # Commit batch
        session.commit()
        
        return new_count
