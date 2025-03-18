"""
Nature source class for fetching and searching Nature papers.
"""
from .paper_source import PaperSource
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
import time
from urllib.parse import urlparse, parse_qs

class NatureSource(PaperSource):
    """
    Source for fetching and searching Nature papers using RSS feeds.
    """
    
    def __init__(self):
        super(NatureSource, self).__init__()
        self.source_name = "nature"
        self.base_url = "https://www.nature.com"
        
        # RSS feeds for different Nature journals and topics
        self.rss_feeds = {
            "nature": "https://www.nature.com/nature.rss",
            "nature_ml": "https://www.nature.com/search/rss?q=machine%20learning&journal=nature",
            "nature_ai": "https://www.nature.com/search/rss?q=artificial%20intelligence&journal=nature",
            "nature_cs": "https://www.nature.com/search/rss?q=computer%20science&journal=nature",
            "nature_methods": "https://www.nature.com/nmeth.rss",
            "nature_comp_sci": "https://www.nature.com/natcomputsci.rss",
            "nature_machine_intell": "https://www.nature.com/natmachintell.rss"
        }
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml"
        }
    
    def _get_model_class(self):
        """Get the NatureModel class for database operations"""
        from ..db import NatureModel
        return NatureModel

    def _extract_doi(self, url):
        """Extract DOI from Nature article URL if possible"""
        parsed = urlparse(url)
        if parsed.path.startswith('/articles/'):
            # Modern Nature URLs have format /articles/s41586-023-06802-1
            parts = parsed.path.split('/')
            if len(parts) > 2:
                return parts[2]
        return None
    
    def fetch_new(self, model=None):
        """
        Fetch new papers from Nature RSS feeds and store them in the database.
        
        Args:
            model: Pre-loaded SentenceTransformer model instance
            
        Returns:
            bool: True if new papers were found, False otherwise
        """
        from ..db import session_scope, NatureModel
        from sentence_transformers import SentenceTransformer
        
        # Use the provided model or load a new one
        if model is None:
            model = SentenceTransformer('all-MiniLM-L6-v2')
        
        self.logger.info("开始从Nature获取论文...")
        
        total_new = 0
        total_fetched = 0
        papers_per_topic = {}  # 跟踪每个话题获取的论文数量
        
        with session_scope() as session:
            for feed_name, feed_url in self.rss_feeds.items():
                papers_per_topic[feed_name] = 0
                
                try:
                    # 尝试不同的页面大小和分页参数，如果RSS支持
                    max_attempts = 3
                    page = 1
                    page_size = 50
                    
                    while papers_per_topic[feed_name] < self.MIN_PAPERS_PER_TOPIC and page <= max_attempts:
                        # 为某些支持分页的RSS feed添加分页参数
                        paginated_url = feed_url
                        if "search/rss" in feed_url:
                            # Nature 搜索RSS可能支持分页
                            if "?" in paginated_url:
                                paginated_url += f"&page={page}&page_size={page_size}"
                            else:
                                paginated_url += f"?page={page}&page_size={page_size}"
                        
                        # Parse the RSS feed
                        feed = feedparser.parse(paginated_url)
                        
                        if not feed.entries:
                            break
                        
                        # Process each entry in the feed
                        new_in_feed = self._process_feed_entries(session, feed.entries, model)
                        papers_per_topic[feed_name] += new_in_feed
                        total_new += new_in_feed
                        total_fetched += len(feed.entries)
                        
                        # 如果没有获取到新论文或达到上限，则停止尝试该feed的更多页面
                        if new_in_feed == 0 or total_fetched >= self.MAX_PAPERS_PER_SOURCE:
                            break
                        
                        # 尝试下一页
                        page += 1
                        
                        # Be nice to the server
                        time.sleep(2)
                    
                    # 如果未达到最小数量且RSS不支持分页，尝试获取额外相关feed
                    if papers_per_topic[feed_name] < self.MIN_PAPERS_PER_TOPIC and "search" not in feed_url:
                        # 对于主要期刊，可以尝试获取最近几期的文章
                        if feed_name in ["nature", "nature_methods"]:
                            journal_code = feed_name.replace("nature_", "") if feed_name != "nature" else "nature"
                            for volume in range(1, 4):  # 尝试最近3期
                                latest_issue_url = f"https://www.nature.com/{journal_code}/current-issue.rss"
                                if volume > 1:
                                    latest_issue_url = f"https://www.nature.com/{journal_code}/archive/issue.rss?volume={volume}"
                                
                                feed = feedparser.parse(latest_issue_url)
                                if feed.entries:
                                    new_in_feed = self._process_feed_entries(session, feed.entries, model)
                                    papers_per_topic[feed_name] += new_in_feed
                                    total_new += new_in_feed
                                    total_fetched += len(feed.entries)
                                    
                                    if papers_per_topic[feed_name] >= self.MIN_PAPERS_PER_TOPIC or total_fetched >= self.MAX_PAPERS_PER_SOURCE:
                                        break
                                    
                                    time.sleep(2)
                    
                except Exception as e:
                    self.logger.error(f"获取Nature RSS feed '{feed_name}'时出错: {str(e)}")
                
                # 如果已经达到总获取上限，提前退出
                if total_fetched >= self.MAX_PAPERS_PER_SOURCE:
                    break
            
            # 统计主要期刊的论文数量
            main_journals_count = papers_per_topic.get("nature", 0) + papers_per_topic.get("nature_methods", 0)
            ai_ml_count = papers_per_topic.get("nature_ml", 0) + papers_per_topic.get("nature_ai", 0) + papers_per_topic.get("nature_machine_intell", 0)
            
            self.logger.info(f"Nature论文获取完成。共获取{total_fetched}篇论文，其中新增{total_new}篇。主要期刊{main_journals_count}篇，AI/ML相关{ai_ml_count}篇。")
            
            return total_new > 0
    
    def _process_feed_entries(self, session, entries, model):
        """Process entries from an RSS feed"""
        from ..db import NatureModel
        
        new_count = 0
        
        for entry in entries:
            try:
                # Get basic information from feed entry
                title = entry.title
                article_url = entry.link
                
                # Skip if no URL
                if not article_url:
                    continue
                
                # Check if article already exists
                existing = session.query(NatureModel).filter(NatureModel.article_url == article_url).first()
                if existing:
                    continue
                
                # Get publication date
                if hasattr(entry, 'published_parsed'):
                    published_time = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed'):
                    published_time = datetime(*entry.updated_parsed[:6])
                else:
                    published_time = datetime.now()
                
                # Get authors
                authors = ""
                if hasattr(entry, 'authors'):
                    authors = ", ".join([author.get('name', '') for author in entry.authors])[:800]
                
                # Get summary/abstract
                abstract = ""
                if hasattr(entry, 'summary'):
                    abstract = entry.summary
                    # If HTML summary, parse with BeautifulSoup
                    if abstract and ('<' in abstract and '>' in abstract):
                        soup = BeautifulSoup(abstract, 'html.parser')
                        abstract = soup.get_text().strip()
                
                # Get journal info and DOI
                journal = "Nature"
                if hasattr(entry, 'journal_ref'):
                    journal = entry.journal_ref
                elif feed_name if 'feed_name' in locals() else "":
                    # Try to extract journal name from feed name
                    if "methods" in feed_name:
                        journal = "Nature Methods"
                    elif "comp_sci" in feed_name:
                        journal = "Nature Computational Science"
                    elif "machine_intell" in feed_name:
                        journal = "Nature Machine Intelligence"
                
                doi = self._extract_doi(article_url)
                
                # Prepare paper data
                paper_data = {
                    'title': title,
                    'abstract': abstract,
                    'authors': authors,
                    'article_url': article_url,
                    'journal': journal,
                    'published_time': published_time,
                    'popularity': 0,
                    'doi': doi
                }
                
                # Process paper data and generate embedding using parent class method
                processed_data, embedding = self._process_paper_metadata(paper_data, model)
                
                # Create new paper record
                new_paper = NatureModel(
                    article_url=processed_data['article_url'],
                    title=processed_data['title'],
                    abstract=processed_data['abstract'],
                    authors=processed_data['authors'],
                    journal=processed_data['journal'],
                    published_time=processed_data['published_time'],
                    popularity=processed_data['popularity'],
                    doi=processed_data.get('doi'),
                    embedding=embedding
                )
                
                session.add(new_paper)
                new_count += 1
                
                # Commit every 10 papers to avoid large transactions
                if new_count % 10 == 0:
                    session.commit()
                
            except Exception as e:
                self.logger.error(f"处理RSS条目时出错: {str(e)}")
        
        # Final commit
        if new_count % 10 != 0:
            session.commit()
        
        return new_count
        
    def _process_article_elements(self, session, article_elements, model):
        """
        Legacy method for processing article elements from a search results page.
        Kept for backward compatibility, but RSS feed is now preferred.
        """
        from ..db import NatureModel
        
        new_count = 0
        
        for element in article_elements:
            try:
                # Extract basic information
                title_element = element.select_one('h3.c-card__title a')
                if not title_element:
                    continue
                
                title = title_element.text.strip()
                article_url = self.base_url + title_element.get('href', '')
                
                # Check if article already exists
                existing = session.query(NatureModel).filter(NatureModel.article_url == article_url).first()
                if existing:
                    continue
                
                # Extract journal and publication date
                journal_element = element.select_one('span.c-meta__item:nth-child(1)')
                journal = journal_element.text.strip() if journal_element else ""
                
                date_element = element.select_one('time')
                pub_date = date_element.get('datetime', '') if date_element else ""
                if pub_date:
                    try:
                        published_time = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    except:
                        published_time = datetime.now()
                else:
                    published_time = datetime.now()
                
                # Extract authors and abstract
                authors_element = element.select_one('ul.c-author-list')
                authors = ", ".join([a.text.strip() for a in authors_element.select('li')]) if authors_element else ""
                
                abstract_element = element.select_one('div.c-card__summary')
                abstract = abstract_element.text.strip() if abstract_element else ""
                
                # Prepare paper data
                paper_data = {
                    'title': title,
                    'abstract': abstract,
                    'authors': authors[:800],
                    'article_url': article_url,
                    'journal': journal,
                    'published_time': published_time,
                    'popularity': 0
                }
                
                # Process paper data and generate embedding using parent class method
                processed_data, embedding = self._process_paper_metadata(paper_data, model)
                
                # Create new paper record
                new_paper = NatureModel(
                    article_url=processed_data['article_url'],
                    title=processed_data['title'],
                    abstract=processed_data['abstract'],
                    authors=processed_data['authors'],
                    journal=processed_data['journal'],
                    published_time=processed_data['published_time'],
                    popularity=processed_data['popularity'],
                    embedding=embedding
                )
                
                session.add(new_paper)
                new_count += 1
                
                # Commit every 10 papers to avoid large transactions
                if new_count % 10 == 0:
                    session.commit()
                
            except Exception as e:
                self.logger.error(f"处理网页文章元素时出错: {str(e)}")
        
        # Final commit
        if new_count % 10 != 0:
            session.commit()
        
        return new_count 