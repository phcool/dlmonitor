"""
Nature source class for fetching and searching Nature papers.
"""
from .paper_source import PaperSource
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import json
import logging
import random
from urllib.parse import urlparse, parse_qs, urljoin
import threading
import concurrent.futures
from queue import Queue
from tqdm import tqdm
import feedparser
from dlmonitor.settings import DEFAULT_MODEL

class NatureSource(PaperSource):
    """
    Source for fetching and searching Nature papers using RSS feeds.
    """
    
    def __init__(self):
        super(NatureSource, self).__init__()
        self.source_name = "nature"
        self.base_url = "https://www.nature.com"
        
        # 直接爬取这些期刊的页面
        self.journal_pages = [
            # Nature Machine Intelligence
            {
                "name": "Nature Machine Intelligence",
                "urls": [
                    "https://www.nature.com/natmachintell/research-articles",
                    "https://www.nature.com/natmachintell/articles?type=article",
                    "https://www.nature.com/natmachintell/articles?type=review"
                ]
            },
            # Nature Computational Science
            {
                "name": "Nature Computational Science", 
                "urls": [
                    "https://www.nature.com/natcomputsci/research-articles",
                    "https://www.nature.com/natcomputsci/articles?type=article",
                    "https://www.nature.com/natcomputsci/articles?type=review"
                ]
            },
            # Nature主刊 - AI/ML相关
            {
                "name": "Nature",
                "urls": [
                    "https://www.nature.com/nature/articles?type=article&subject=computer-science",
                    "https://www.nature.com/nature/articles?type=article&subject=artificial-intelligence",
                    "https://www.nature.com/nature/articles?type=article&subject=machine-learning",
                    "https://www.nature.com/search?subject=artificial-intelligence&journal=nature"
                ]
            }
        ]
        
        # RSS源列表
        self.rss_feeds = [
            {
                "name": "Nature Machine Intelligence",
                "url": "https://www.nature.com/natmachintell.rss"
            },
            {
                "name": "Nature Computational Science",
                "url": "https://www.nature.com/natcomputsci.rss"
            },
            {
                "name": "Nature",
                "url": "https://www.nature.com/nature.rss"
            },
            # 添加AI/ML相关主题的RSS
            {
                "name": "Nature AI/ML Articles",
                "url": "https://www.nature.com/search.rss?subject=artificial-intelligence"
            },
            {
                "name": "Nature Computer Science Articles",
                "url": "https://www.nature.com/search.rss?subject=computer-science"
            }
        ]
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.nature.com/"
        }
    
    def _get_model_class(self):
        """获取NatureModel类用于数据库操作"""
        from ..db import NatureModel
        return NatureModel

    def _extract_doi(self, url):
        """从Nature文章URL中提取DOI（如果可能）"""
        if not url:
            return None
            
        parsed = urlparse(url)
        if parsed.path.startswith('/articles/'):
            parts = parsed.path.split('/')
            if len(parts) > 2:
                return parts[2]
                
        return None
    
    def _process_batch(self, session, batch, model, existing_urls=None):
        """
        处理论文批次并添加到数据库
        
        Args:
            session: 数据库会话
            batch: 论文批次
            model: 嵌入模型
            existing_urls: 已存在的URL集合（如果为None则会查询）
            
        Returns:
            tuple: (新增论文数量, 每个期刊的论文数量字典)
        """
        from ..db import NatureModel
        
        # 如果没有提供现有URL，则查询数据库
        if existing_urls is None:
            article_urls = [paper.article_url for paper in batch]
            existing_urls = {url[0] for url in session.query(NatureModel.article_url).filter(NatureModel.article_url.in_(article_urls)).all()}
        
        # 准备新论文数据
        new_papers = []
        batch_new_count = 0
        papers_per_journal = {}
        
        for paper in batch:
            article_url = paper.article_url
            
            # 跟踪每个期刊的论文数量
            journal = paper.journal
            if journal not in papers_per_journal:
                papers_per_journal[journal] = 0
            papers_per_journal[journal] += 1
            
            # 只处理新论文
            if article_url not in existing_urls:
                batch_new_count += 1
                
                # 创建新论文记录
                new_paper = NatureModel(
                    article_url=paper.article_url,
                    title=paper.title,
                    abstract=paper.abstract,
                    authors=paper.authors,
                    journal=paper.journal,
                    published_time=paper.published_time,
                    popularity=paper.popularity,
                    doi=paper.doi,
                    embedding=paper.embedding
                )
                
                new_papers.append(new_paper)
        
        # 将新论文添加到会话
        if new_papers:
            for new_paper in new_papers:
                session.add(new_paper)
            session.commit()
        
        return batch_new_count, papers_per_journal
    
    def _fetch(self, search_queries, max_papers=None, model=None, batch_size=32, stop_on_consecutive_empty=False, time_limit=None):
        """
        通用论文获取函数，支持单个或多个搜索查询
        
        Args:
            search_queries: 单个查询或查询生成器，每个查询为(query_string, sort_by)元组
            max_papers: 最大获取论文数量
            model: 预加载的SentenceTransformer模型
            batch_size: 处理的批次大小
            stop_on_consecutive_empty: 是否在连续空批次后停止
            time_limit: 可选的时间限制，格式为datetime，只获取该时间后的论文
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        from ..db import session_scope, NatureModel
        from sentence_transformers import SentenceTransformer
        
        # 使用提供的模型或加载新模型
        if model is None:
            model = SentenceTransformer(DEFAULT_MODEL)
            
        # 如果没有指定最大论文数，使用类默认值
        if max_papers is None:
            max_papers = self.MAX_PAPERS_PER_SOURCE
            
        # 确保search_queries是可迭代的
        if not hasattr(search_queries, '__iter__') or isinstance(search_queries, tuple):
            search_queries = [search_queries]
            
        total_new = 0
        total_fetched = 0
        all_journals_count = {}
        
        # 处理每个查询
        for query_idx, (query_string, sort_criterion) in enumerate(search_queries):
            if isinstance(query_string, str):
                self.logger.info(f"执行查询 {query_idx+1}/{len(search_queries)}: {query_string}")
            
            # 创建RSS feed解析器
            feed = feedparser.parse(query_string)
            
            if not feed.entries:
                self.logger.warning(f"RSS feed没有条目: {query_string}")
                continue
            
            self.logger.info(f"从 {query_string} 获取到 {len(feed.entries)} 篇文章")
            
            # 处理结果批次
            batch = []
            query_total = 0
            consecutive_empty_batches = 0
            
            for entry in feed.entries:
                try:
                    # 提取文章URL
                    article_url = entry.link if hasattr(entry, 'link') else None
                    if not article_url:
                        continue
                    
                    # 提取DOI
                    doi = None
                    if hasattr(entry, 'id') and 'doi' in entry.id:
                        doi = entry.id.split('doi.org/')[-1]
                    else:
                        doi = self._extract_doi(article_url)
                    
                    # 提取发布日期
                    published_time = datetime.now()
                    if hasattr(entry, 'published_parsed'):
                        published_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    elif hasattr(entry, 'updated_parsed'):
                        published_time = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                    
                    # 应用时间限制（如果提供）
                    if time_limit and published_time < time_limit:
                        continue
                    
                    # 提取标题和摘要
                    title = entry.title if hasattr(entry, 'title') else ""
                    
                    # 提取摘要
                    abstract = ""
                    if hasattr(entry, 'summary'):
                        abstract = entry.summary
                    elif hasattr(entry, 'description'):
                        abstract = entry.description
                    
                    # 移除HTML标签
                    if abstract:
                        abstract = BeautifulSoup(abstract, 'html.parser').get_text()
                    
                    # 如果没有足够的摘要，尝试获取文章内容
                    if not abstract or len(abstract) < 50:
                        article_data = self._fetch_article_details(article_url)
                        if article_data.get('abstract'):
                            abstract = article_data.get('abstract')
                    
                    # 提取作者信息
                    authors = ""
                    if hasattr(entry, 'authors'):
                        authors = ", ".join([author.name for author in entry.authors])[:800]
                    elif hasattr(entry, 'author'):
                        authors = entry.author[:800]
                    
                    # 如果没有作者信息，尝试从文章页面获取
                    if not authors:
                        article_data = self._fetch_article_details(article_url)
                        authors = article_data.get('authors', '')
                    
                    # 创建新的论文记录
                    if title and abstract and len(abstract) >= 50:
                        # 创建新论文记录
                        new_paper = NatureModel(
                            article_url=article_url,
                            title=title,
                            abstract=abstract,
                            authors=authors,
                            journal=query_string,
                            published_time=published_time,
                            popularity=0,
                            doi=doi,
                            embedding=None
                        )
                        
                        # 生成嵌入向量
                        if model:
                            try:
                                paper_text = f"Title: {new_paper.title}\nAuthors: {new_paper.authors}\nAbstract: {new_paper.abstract}"
                                new_paper.embedding = model.encode(paper_text).astype('float32')
                            except Exception as e:
                                self.logger.error(f"生成嵌入向量失败: {str(e)}")
                        
                        batch.append(new_paper)
                        total_fetched += 1
                        query_total += 1
                    
                    # 达到批次大小或已处理所有结果
                    if len(batch) >= batch_size or total_fetched >= max_papers:
                        with session_scope() as session:
                            # 处理批次
                            batch_new, batch_journals = self._process_batch(session, batch, model)
                            total_new += batch_new
                            
                            # 更新期刊计数
                            for journal, count in batch_journals.items():
                                all_journals_count[journal] = all_journals_count.get(journal, 0) + count
                            
                            # 更新连续空批次计数
                            if batch_new > 0:
                                consecutive_empty_batches = 0
                            else:
                                consecutive_empty_batches += 1
                        
                        batch = []
                        
                        # 停止条件
                        if total_fetched >= max_papers:
                            break
                        
                        if stop_on_consecutive_empty and query_total >= 100 and consecutive_empty_batches >= 3:
                            self.logger.info(f"连续{consecutive_empty_batches}个空批次，停止获取")
                            break
                        
                        # 休息一下，避免过度请求
                        time.sleep(1)
                
                except Exception as e:
                    self.logger.error(f"处理RSS条目时出错: {str(e)}")
            
            # 处理剩余批次
            if batch:
                with session_scope() as session:
                    batch_new, batch_journals = self._process_batch(session, batch, model)
                    total_new += batch_new
                    
                    # 更新期刊计数
                    for journal, count in batch_journals.items():
                        all_journals_count[journal] = all_journals_count.get(journal, 0) + count
        
        # 打印获取统计信息
        self.logger.info(f"Nature论文获取完成。共获取{total_fetched}篇论文，其中新增{total_new}篇。")
        journal_stats = ", ".join([f"{name}: {count}篇" for name, count in all_journals_count.items() if count > 0])
        self.logger.info(f"按期刊分类: {journal_stats if journal_stats else '无新论文'}")
        
        return total_new > 0

    def fetch_new(self, model=None):
        """
        获取最近一天内的Nature论文并存储到数据库。
        
        Args:
            model: 预加载的SentenceTransformer模型
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        self.logger.info(f"开始获取Nature过去24小时内的论文... (最多获取{self.MAX_PAPERS_PER_SOURCE}篇)")
        
        # 设置一周时间限制
        one_week_ago = datetime.now() - timedelta(days=7)
        self.logger.info(f"仅获取{one_week_ago.strftime('%Y-%m-%d')}之后发布的论文")
        
        # 使用预定义的RSS feeds作为查询
        search_queries = []
        for feed in self.rss_feeds:
            search_queries.append((feed["url"], None))  # Nature RSS不需要排序标准
            self.logger.info(f"添加RSS feed: {feed['name']} - {feed['url']}")
        
        # 调用通用获取函数，不使用连续空批次停止，确保获取所有新论文
        return self._fetch(
            search_queries, 
            max_papers=self.MAX_PAPERS_PER_SOURCE,
            model=model,
            batch_size=32,
            stop_on_consecutive_empty=False,  # 确保获取所有符合条件的论文
            time_limit=one_week_ago  # 添加时间限制
        )

    def fetch_all(self, model=None):
        """
        一次性获取大量Nature论文，用于初始填充数据库。
        
        Args:
            model: 预加载的SentenceTransformer模型
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        # 保存并设置更高的最大论文数
        original_max = self.MAX_PAPERS_PER_SOURCE
        max_papers = 100000  # 10万篇论文
        
        self.logger.info(f"开始从Nature大量获取论文... (最大获取量: {max_papers}篇)")
        
        # 创建多个搜索查询，基于期刊
        search_queries = []
        for feed in self.rss_feeds:
            search_queries.append((feed["url"], None))  # Nature RSS不需要排序标准
        
        # 调用通用获取函数，不设置连续空批次停止
        result = self._fetch(
            search_queries, 
            max_papers=max_papers,
            model=model,
            batch_size=100,
            stop_on_consecutive_empty=False
        )
        
        # 恢复原始值
        self.MAX_PAPERS_PER_SOURCE = original_max
        
        return result

    def _fetch_article_details(self, url):
        """获取文章详情（优化版）"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)  # 减少超时时间
            
            if response.status_code != 200:
                return {"title": "", "abstract": "", "authors": "", "journal": "", "published_time": datetime.now(), "doi": ""}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 从JSON-LD中提取信息，通常包含最完整的数据
            article_data = self._extract_jsonld_data(soup)
            
            # 提取摘要
            abstract = article_data.get("abstract", "")
            if not abstract or len(abstract) < 50:
                # 先尝试meta标签
                meta_desc = soup.select_one('meta[name="description"]')
                if meta_desc:
                    abstract = meta_desc.get('content', '').strip()
                
                # 如果仍然没有足够长的摘要，尝试各种选择器
                if not abstract or len(abstract) < 50:
                    for selector in [
                        'div#Abs1-content', 
                        'div.c-article-section__content[data-test="abstract"]',
                        'div.c-article-teaser p',
                        'p.article__teaser',
                        'div.article__teaser',
                        'section.c-article-section[data-title="Abstract"] p',
                        'p.c-article-teaser__text',
                        'div[id^="Abs"]',
                        'div.c-article-body p:first-child',
                        'div.article__body p:first-child'
                    ]:
                        abstract_elems = soup.select(selector)
                        if abstract_elems:
                            abstract = ' '.join([elem.get_text().strip() for elem in abstract_elems])
                            if abstract and len(abstract) > 50:
                                break
                    
                    # 如果仍然没有，尝试提取前几段文本
                    if not abstract or len(abstract) < 50:
                        paragraphs = soup.select('div.c-article-body p, div.article__body p, article p')[:3]
                        if paragraphs:
                            abstract = ' '.join([p.get_text().strip() for p in paragraphs])
            
            # 提取标题
            title = article_data.get("title", "")
            if not title:
                title_elem = (soup.select_one('h1.c-article-title') or 
                             soup.select_one('h1.article-title') or 
                             soup.select_one('meta[name="citation_title"]'))
                if title_elem:
                    title = title_elem.get('content', '') if title_elem.name == 'meta' else title_elem.get_text().strip()
            
            # 提取DOI
            doi = article_data.get("doi") or self._extract_doi(url)
            if not doi:
                doi_elem = (soup.select_one('a[data-track-action="view doi"]') or 
                           soup.select_one('a.c-article-identifiers__doi') or
                           soup.select_one('meta[name="citation_doi"]'))
                
                if doi_elem:
                    if doi_elem.name == 'meta':
                        doi = doi_elem.get('content', '')
                    else:
                        doi_text = doi_elem.get_text().strip()
                        doi = doi_text.replace('https://doi.org/', '') if 'doi.org/' in doi_text else doi_text
            
            # 提取期刊名称
            journal = article_data.get("journal", "")
            if not journal:
                journal_elem = (soup.select_one('meta[name="citation_journal_title"]') or
                               soup.select_one('meta[name="journal"]'))
                if journal_elem:
                    journal = journal_elem.get('content', '')
                else:
                    # 从URL判断
                    if "natmachintell" in url:
                        journal = "Nature Machine Intelligence"
                    elif "natcomputsci" in url:
                        journal = "Nature Computational Science"
                    else:
                        journal = "Nature"
            
            # 提取作者
            authors = article_data.get("authors", "")
            if not authors:
                authors_elements = (soup.select('meta[name="citation_author"]') or
                                  soup.select('ul.c-article-author-list li, span.c-article-author-list__item') or
                                  soup.select('ul.article-authors li'))
                
                if authors_elements:
                    if authors_elements[0].name == 'meta':
                        authors = ", ".join([author.get('content', '') for author in authors_elements])[:800]
                    else:
                        authors = ", ".join([author.get_text().strip() for author in authors_elements])[:800]
            
            # 提取发布日期
            published_time = article_data.get("datePublished") or datetime.now()
            if not isinstance(published_time, datetime):
                date_elem = (soup.select_one('meta[name="citation_publication_date"]') or
                            soup.select_one('time.c-article-identifiers__datetime'))
                if date_elem:
                    date_str = date_elem.get('content', '') or date_elem.get_text().strip()
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%B %d, %Y']:
                        try:
                            published_time = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
            
            return {
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "journal": journal,
                "published_time": published_time,
                "doi": doi
            }
            
        except Exception as e:
            return {"title": "", "abstract": "", "authors": "", "journal": "", "published_time": datetime.now(), "doi": ""}
    
    def _extract_jsonld_data(self, soup):
        """从页面的JSON-LD结构化数据中提取文章信息"""
        try:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    result = {}
                    
                    # 处理可能的各种JSON-LD结构
                    if isinstance(data, dict):
                        # 摘要
                        if 'description' in data:
                            result['abstract'] = data['description']
                        
                        # DOI
                        if 'sameAs' in data and isinstance(data['sameAs'], list):
                            for same_as in data['sameAs']:
                                if isinstance(same_as, str) and 'doi.org' in same_as:
                                    result['doi'] = same_as.split('doi.org/')[-1]
                                    break
                        
                        # 期刊
                        if 'isPartOf' in data and isinstance(data['isPartOf'], dict) and 'name' in data['isPartOf']:
                            result['journal'] = data['isPartOf']['name']
                        
                        # 作者
                        if 'author' in data:
                            if isinstance(data['author'], list):
                                author_names = []
                                for author in data['author']:
                                    if isinstance(author, dict) and 'name' in author:
                                        author_names.append(author['name'])
                                result['authors'] = ', '.join(author_names)[:800]
                            elif isinstance(data['author'], dict) and 'name' in data['author']:
                                result['authors'] = data['author']['name']
                        
                        # 发布日期
                        if 'datePublished' in data:
                            try:
                                result['datePublished'] = datetime.fromisoformat(data['datePublished'].replace('Z', '+00:00'))
                            except (ValueError, TypeError):
                                pass
                    
                    if result:
                        return result
                except:
                    continue
        except Exception as e:
            self.logger.warning(f"从JSON-LD提取数据失败: {str(e)}")
        
        return {} 