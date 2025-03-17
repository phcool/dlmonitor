import os, sys
from ..db import create_engine
from .base import Source
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

    def get_posts(self, keywords=None, since=None, start=0, num=20, model=None):
        from ..db import get_global_session, ArxivModel
        from sentence_transformers import SentenceTransformer
        from sqlalchemy import func
        
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
            # Check if vector search is available
            has_embeddings = session.query(ArxivModel).filter(ArxivModel.embedding != None).limit(1).count() > 0
            
            if has_embeddings:
                # Generate query embedding
                if model is None:
                    model = SentenceTransformer('all-MiniLM-L6-v2')
                query_embedding = model.encode(keywords).astype(np.float32)
                
                # Use cosine distance method for vector search
                # Note: cosine_distance = 1 - cosine_similarity, so we ORDER BY ASC
                results = (session.query(ArxivModel)
                          .filter(ArxivModel.embedding != None)
                          .order_by(ArxivModel.embedding.cosine_distance(query_embedding))
                          .offset(start).limit(num).all())
                
                # If vector search results are insufficient, supplement with text search
            #     if len(results) < num:
            #         existing_ids = [paper.id for paper in results]
                    
            #         search_kw = " or ".join(keywords.split(","))
            #         remaining = num - len(results)
                    
            #         text_results = (search(query.filter(~ArxivModel.id.in_(existing_ids)), 
            #                               search_kw, sort=True)
            #                        .limit(remaining).all())
                    
            #         results.extend(text_results)
            # else:
            #     # Fall back to traditional text search
            #     search_kw = " or ".join(keywords.split(","))
            #     results = search(query, search_kw, sort=True).offset(start).limit(num).all()
        
        return results

    def fetch_new(self, model=None):
        """
        Fetch new papers from arXiv and store them in the database.
        This implementation directly uses the arxiv library instead of calling query_arxiv.
        Also generates embeddings for new papers using sentence-transformers.
        
        Args:
            model: 预加载的SentenceTransformer模型实例，如果为None则创建新实例
        """
        from ..db import session_scope, ArxivModel
        from sentence_transformers import SentenceTransformer
        
        # 使用传入的模型或加载新模型
        if model is None:
            model = SentenceTransformer('all-MiniLM-L6-v2')  # 使用小型模型以提高性能
        
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
                batch_size = 32  # 降低批次大小以适应向量生成
                batch = []
                total_new = 0
                consecutive_empty_batches = 0  # Track consecutive batches with no new papers
                
                # Process first 200 results (2 pages) which are usually reliable
                for i, result in enumerate(results_iterator):
                    # Process in batches
                    batch.append(result)
                    
                    if len(batch) >= batch_size or i == max_results - 1:  # Process batch or last item
                        logging.info(f"Processing batch of {len(batch)} papers...")
                        
                        # 准备用于检查存在性的 arxiv_url 列表
                        arxiv_urls = [paper.entry_id for paper in batch]
                        existing_urls = {url[0] for url in session.query(ArxivModel.arxiv_url).filter(ArxivModel.arxiv_url.in_(arxiv_urls)).all()}
                        
                        # 为新论文准备数据
                        new_papers = []
                        new_paper_texts = []
                        
                        anything_new = False  # Reset for each batch
                        for paper in batch:
                            arxiv_url = paper.entry_id
                            
                            # Check if paper already exists in database
                            if arxiv_url not in existing_urls:
                                anything_new = True
                                total_new += 1
                                
                                # 准备文本用于向量生成
                                title = paper.title.replace("\n", "").replace("  ", " ")
                                abstract = paper.summary.replace("\n", "").replace("  ", " ")
                                authors = ", ".join([author.name for author in paper.authors])[:800]
                                paper_text = f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}"
                                new_paper_texts.append(paper_text)
                                
                                # Create new paper record (暂不设置 embedding)
                                new_paper = ArxivModel(
                                    arxiv_url=arxiv_url,
                                    version=self._get_version(arxiv_url),
                                    title=title,
                                    abstract=abstract,
                                    pdf_url=paper.pdf_url,
                                    authors=authors,
                                    published_time=datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                                    journal_link=paper.journal_ref if hasattr(paper, "journal_ref") else "",
                                    tag=" | ".join(paper.categories),
                                    popularity=0
                                )
                                new_papers.append(new_paper)
                        
                        # 如果有新论文，生成向量表示
                        if new_papers:
                            logging.info(f"Generating embeddings for {len(new_papers)} new papers...")
                            embeddings = model.encode(new_paper_texts)
                            
                            # 设置向量表示并添加到会话
                            for j, new_paper in enumerate(new_papers):
                                new_paper.embedding = embeddings[j].astype(np.float32)  # 转换为 float32 以兼容 pgvector
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
                    
                    # 准备用于检查存在性的 arxiv_url 列表
                    arxiv_urls = [paper.entry_id for paper in batch]
                    existing_urls = {url[0] for url in session.query(ArxivModel.arxiv_url).filter(ArxivModel.arxiv_url.in_(arxiv_urls)).all()}
                    
                    # 为新论文准备数据
                    new_papers = []
                    new_paper_texts = []
                    
                    anything_new = False
                    for paper in batch:
                        arxiv_url = paper.entry_id
                        
                        # Check if paper already exists in database
                        if arxiv_url not in existing_urls:
                            anything_new = True
                            total_new += 1
                            
                            # 准备文本用于向量生成
                            title = paper.title.replace("\n", "").replace("  ", " ")
                            abstract = paper.summary.replace("\n", "").replace("  ", " ")
                            authors = ", ".join([author.name for author in paper.authors])[:800]
                            paper_text = f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}"
                            new_paper_texts.append(paper_text)
                            
                            # Create new paper record (暂不设置 embedding)
                            new_paper = ArxivModel(
                                arxiv_url=arxiv_url,
                                version=self._get_version(arxiv_url),
                                title=title,
                                abstract=abstract,
                                pdf_url=paper.pdf_url,
                                authors=authors,
                                published_time=datetime.fromtimestamp(mktime(paper.updated.timetuple())),
                                journal_link=paper.journal_ref if hasattr(paper, "journal_ref") else "",
                                tag=" | ".join(paper.categories),
                                popularity=0
                            )
                            new_papers.append(new_paper)
                    
                    # 如果有新论文，生成向量表示
                    if new_papers:
                        logging.info(f"Generating embeddings for {len(new_papers)} new papers...")
                        embeddings = model.encode(new_paper_texts)
                        
                        # 设置向量表示并添加到会话
                        for j, new_paper in enumerate(new_papers):
                            new_paper.embedding = embeddings[j].astype(np.float32)  # 转换为 float32 以兼容 pgvector
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
