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
        
        # 获取当前日期，用于构建日期参数
        current_date = datetime.now()
        current_year = current_date.year
        last_year = current_year - 1
        
        # 直接爬取这些期刊的页面，使用日期过滤
        self.journal_pages = [
            # Nature Machine Intelligence
            {
                "name": "Nature Machine Intelligence",
                "urls": [
                    f"https://www.nature.com/natmachintell/research-articles?date_range={last_year}-{current_year}",
                    f"https://www.nature.com/natmachintell/articles?type=article&date_range={last_year}-{current_year}",
                    f"https://www.nature.com/natmachintell/articles?type=review&date_range={last_year}-{current_year}"
                ]
            },
            # Nature Computational Science
            {
                "name": "Nature Computational Science", 
                "urls": [
                    f"https://www.nature.com/natcomputsci/research-articles?date_range={last_year}-{current_year}",
                    f"https://www.nature.com/natcomputsci/articles?type=article&date_range={last_year}-{current_year}",
                    f"https://www.nature.com/natcomputsci/articles?type=review&date_range={last_year}-{current_year}"
                ]
            },
            # Nature主刊 - 所有计算机科学相关
            {
                "name": "Nature",
                "urls": [
                    # 计算机科学总类
                    f"https://www.nature.com/nature/articles?type=article&subject=computer-science&date_range={last_year}-{current_year}",
                    # AI/ML相关
                    f"https://www.nature.com/nature/articles?type=article&subject=artificial-intelligence&date_range={last_year}-{current_year}",
                    f"https://www.nature.com/nature/articles?type=article&subject=machine-learning&date_range={last_year}-{current_year}",
                    # 机器人和自动化
                    f"https://www.nature.com/nature/articles?type=article&subject=robotics&date_range={last_year}-{current_year}",
                    f"https://www.nature.com/nature/articles?type=article&subject=automation&date_range={last_year}-{current_year}",
                    # 计算机视觉和图形学
                    f"https://www.nature.com/nature/articles?type=article&subject=computer-vision&date_range={last_year}-{current_year}",
                    f"https://www.nature.com/nature/articles?type=article&subject=graphics&date_range={last_year}-{current_year}",
                    # 自然语言处理
                    f"https://www.nature.com/nature/articles?type=article&subject=natural-language-processing&date_range={last_year}-{current_year}",
                    # 人机交互
                    f"https://www.nature.com/nature/articles?type=article&subject=human-computer-interaction&date_range={last_year}-{current_year}",
                    # 软件工程
                    f"https://www.nature.com/nature/articles?type=article&subject=software-engineering&date_range={last_year}-{current_year}",
                    # 分布式系统
                    f"https://www.nature.com/nature/articles?type=article&subject=distributed-computing&date_range={last_year}-{current_year}",
                    # 量子计算
                    f"https://www.nature.com/nature/articles?type=article&subject=quantum-computing&date_range={last_year}-{current_year}"
                ]
            }
        ]
        
        # 注意：根据需求，不再使用RSS获取文章
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.nature.com/"
        }
        
        # 设置最大论文获取数量
        self.MAX_PAPERS_PER_SOURCE = 100
    
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
    
    def _fetch(self, max_nums=None, model=None, batch_size=32, time_limit=None):
        """实现获取文章的方法"""
        from ..db import session_scope, NatureModel
        from sentence_transformers import SentenceTransformer
        
        # 使用提供的模型或加载新模型
        if model is None:
            try:
                model = SentenceTransformer(DEFAULT_MODEL)
                self.logger.info(f"成功加载模型: {DEFAULT_MODEL}")
            except Exception as e:
                self.logger.error(f"加载模型失败: {str(e)}")
                model = None
                
        if max_nums is None:
            max_nums = self.MAX_PAPERS_PER_SOURCE
            
        total_new = 0
        total_fetched = 0
        all_journals_count = {}
        batch = []  # 存储待保存的论文对象
        
        # 获取当前数据库中已有的URL
        with session_scope() as session:
            existing_urls = {url[0] for url in session.query(NatureModel.article_url).all()}
            
        # 从期刊页面获取文章
        try:
            self.logger.info("开始从期刊页面获取论文...")
            articles_data = self._fetch_from_journal_pages(time_limit=time_limit)
            self.logger.info(f"从期刊页面获取到 {len(articles_data)} 篇文章")
            
            # 处理获取到的文章数据
            for article_data in articles_data:
                try:
                    # 如果已经达到最大获取数量，则跳出
                    if total_fetched >= max_nums:
                        break
                        
                    # 构建文章URL - 优先使用article_url，如果没有则使用DOI构建URL
                    article_url = article_data.get("article_url")
                    if not article_url:
                        doi = article_data.get("doi")
                        if doi and not (doi.startswith('http://') or doi.startswith('https://')):
                            article_url = f"https://doi.org/{doi}"
                    
                    # 如果没有URL或URL已存在，则跳过
                    if not article_url or article_url in existing_urls:
                        continue
                        
                    # 提取文章数据
                    title = article_data.get("title", "")
                    abstract = article_data.get("abstract", "")
                    authors = article_data.get("authors", "")
                    journal = article_data.get("journal", "Nature")
                    published_time = article_data.get("published_time")
                    doi = article_data.get("doi", "")
                    
                    # 只保存有标题的文章
                    if title:
                        # 创建新论文记录
                        new_paper = NatureModel(
                            article_url=article_url,
                            title=title,
                            abstract=abstract if abstract else "",
                            authors=authors if authors else "",
                            journal=journal,
                            published_time=published_time or datetime.now(),
                            popularity=0,
                            doi=doi,
                            embedding=None
                        )
                        
                        # 生成嵌入向量 - 只有当有足够的摘要文本时才生成
                        if model and abstract and len(abstract) >= 50:
                            try:
                                paper_text = f"Title: {new_paper.title}\nAuthors: {new_paper.authors}\nAbstract: {new_paper.abstract}"
                                new_paper.embedding = model.encode(paper_text).astype('float32')
                            except Exception as e:
                                self.logger.error(f"生成嵌入向量失败: {str(e)}")
                        
                        batch.append(new_paper)
                        total_fetched += 1
                    
                        # 更新期刊计数
                        if journal not in all_journals_count:
                            all_journals_count[journal] = 0
                        all_journals_count[journal] += 1
                        
                        # 达到批次大小则保存
                        if len(batch) >= batch_size:
                            with session_scope() as session:
                                batch_new, _ = self._process_batch(session, batch, model)
                                total_new += batch_new
                            
                            batch = []
                except Exception as e:
                    self.logger.error(f"获取论文出错: {str(e)}")
            
            # 处理剩余批次
            if batch:
                with session_scope() as session:
                    batch_new, _ = self._process_batch(session, batch, model)
                    total_new += batch_new
                    
        except Exception as e:
            self.logger.error(f"获取论文过程中发生错误: {str(e)}")
        
        # 打印获取统计信息
        self.logger.info(f"Nature论文获取完成。共获取{total_fetched}篇论文，其中新增{total_new}篇。")
        journal_stats = ", ".join([f"{name}: {count}篇" for name, count in all_journals_count.items() if count > 0])
        self.logger.info(f"按期刊分类: {journal_stats if journal_stats else '无新论文'}")
        
        return total_new > 0

    def fetch_all(self, max_nums=None, model=None):
        """获取所有论文（限制为过去三个月的论文，使用URL参数）"""
        self.logger.info("开始获取Nature所有论文（过去三个月）...")
        
        # 设置时间限制为三个月前，仅用于本地过滤（URL参数已经限制了大部分文章）
        three_months_ago = datetime.now() - timedelta(days=90)
        self.logger.info(f"时间限制: {three_months_ago}")
        
        return self._fetch(max_nums=max_nums, model=model, time_limit=three_months_ago)
        
    def fetch_new(self, max_nums=None, model=None):
        """获取最新论文（过去7天内）"""
        self.logger.info("开始获取Nature最新论文（过去7天）...")
        
        # 设置时间限制为一周前
        one_week_ago = datetime.now() - timedelta(days=7)
        self.logger.info(f"时间限制: {one_week_ago}")
        
        return self._fetch(max_nums=max_nums, model=model, time_limit=one_week_ago)

    def _fetch_article_details(self, url):
        """获取文章详情（优化版）"""
        try:
            self.logger.debug(f"获取文章详情: {url}")
            response = requests.get(url, headers=self.headers, timeout=15)  # 增加超时时间
            
            if response.status_code != 200:
                self.logger.warning(f"获取文章失败: {url}, 状态码: {response.status_code}")
                return {"title": "", "abstract": "", "authors": "", "journal": "", "published_time": None, "doi": ""}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 先尝试获取整个页面HTML，用于调试
            # 这对于理解页面结构非常有用
            # 但记得在正式使用时删除这段代码，以减少日志输出
            # html_content = str(soup)[:1000]  # 仅取前1000个字符以避免日志过长
            # self.logger.debug(f"页面HTML片段: {html_content}...")
            
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
                        'div.article__body p:first-child',
                        # 新增选择器
                        'div[aria-labelledby="abstract-heading"]',
                        'section#abstract',
                        '.abstract',
                        'div[role="paragraph"][id*="abs"]',
                        'div[data-component="article-container"] > p:first-child'
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
                             soup.select_one('h1.c-article-magazine-title') or
                             soup.select_one('h1[data-test="article-title"]') or
                             soup.select_one('meta[name="citation_title"]'))
                if title_elem:
                    title = title_elem.get('content', '') if title_elem.name == 'meta' else title_elem.get_text().strip()
            
            # 提取DOI
            doi = article_data.get("doi") or self._extract_doi(url)
            if not doi:
                doi_elem = (soup.select_one('a[data-track-action="view doi"]') or 
                           soup.select_one('a.c-article-identifiers__doi') or
                           soup.select_one('meta[name="citation_doi"]') or
                           soup.select_one('span[data-test="doi-link"]'))
                
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
                               soup.select_one('meta[name="journal"]') or
                               soup.select_one('span[data-test="journal-title"]') or
                               soup.select_one('p.c-article-info-details a[data-track-action="journal name"]'))
                if journal_elem:
                    journal = journal_elem.get('content', '') or journal_elem.get_text().strip()
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
                                  soup.select('ul.article-authors li') or
                                  soup.select('a[data-test="author-name"]') or
                                  soup.select('.c-article-header a[data-track-action="author name"]'))
                
                if authors_elements:
                    if authors_elements[0].name == 'meta':
                        authors = ", ".join([author.get('content', '') for author in authors_elements])[:800]
                    else:
                        authors = ", ".join([author.get_text().strip() for author in authors_elements])[:800]
            
            # 提取发布日期 - 改进日期提取方法
            published_time = article_data.get("datePublished")
            
            # 如果没有找到发布日期，尝试多种方法提取
            if not published_time:
                self.logger.debug(f"从JSON-LD中未找到发布日期，尝试其他方式")
                
                # 记录所有尝试的日期相关元素，供调试
                date_elements = []
                
                # 1. 尝试meta标签
                date_meta_selectors = [
                    'meta[name="citation_publication_date"]',
                    'meta[name="DC.date"]',
                    'meta[name="prism.publicationDate"]',
                    'meta[property="article:published_time"]',
                    'meta[name="dc.Date"]',
                    'meta[name="date"]'
                ]
                
                for selector in date_meta_selectors:
                    date_elem = soup.select_one(selector)
                    if date_elem and date_elem.get('content'):
                        date_str = date_elem.get('content').strip()
                        date_elements.append((selector, date_str))
                        self.logger.debug(f"找到日期元素 {selector}: {date_str}")
                        break
                else:
                    # 2. 尝试显式的日期HTML元素
                    date_selectors = [
                        'time.c-article-identifiers__datetime',
                        'time[datetime]',
                        'span.c-article-identifiers__item time',
                        'p.c-article-info-details time',
                        'time.c-article-publishdate',
                        'span[data-test="published"]',
                        'p.article__published-date',
                        'div.c-meta time',
                        'span.c-article-published',
                        '.c-article-identifiers .c-article-identifiers__item',  # 新布局标识符
                        '.c-article-metrics-bar time',                          # 新布局指标栏
                        'p.c-article-info-details span[data-test="published"]', # 详情页发布日期
                        'header time',                                          # 标题中的时间元素
                        'span.article-info',                                    # 文章信息
                        'p > span.c-article-info-details__list-item',           # 文章信息详情
                        '.app-article-list-row__item *[data-test="published"]'  # 列表页特有格式
                    ]
                    
                    for selector in date_selectors:
                        date_elems = soup.select(selector)
                        for date_elem in date_elems:
                            # 尝试从元素中提取日期文本
                            date_text = None
                            # 优先从datetime属性获取
                            if date_elem.has_attr('datetime'):
                                date_text = date_elem.get('datetime').strip()
                                date_elements.append((f"{selector}[datetime]", date_text))
                            else:
                                # 获取元素的文本内容
                                raw_text = date_elem.get_text().strip()
                                # 查找可能包含日期的文本
                                if any(x in raw_text.lower() for x in ['published', 'date', 'online']):
                                    date_text = raw_text
                                    date_elements.append((selector, date_text))

                            if date_text:
                                # 尝试通过辅助函数解析日期
                                parsed_date = self._parse_date_string(date_text)
                                if parsed_date:
                                    published_time = parsed_date
                                    self.logger.info(f"使用选择器 {selector} 成功提取日期: {date_text} -> {parsed_date}")
                                    break
                        
                        if published_time:
                            break
                    
                    if not published_time:
                        # 3. 尝试在文本内容中查找日期模式
                        # 首先在文章头部区域查找，这里更可能包含发布日期
                        header_section = soup.select_one('header') or soup.select_one('.c-article-header') or soup.select_one('.article__header')
                        if header_section:
                            header_text = header_section.get_text()
                        else:
                            # 如果没有明确的header区域，则在整个页面文本中查找
                            header_text = soup.get_text()
                            
                        # 尝试各种日期格式的正则表达式
                        date_patterns = [
                            r'Published:?\s*([A-Za-z]+ \d{1,2},? \d{4})',  # Published: January 1, 2023
                            r'Published:?\s*(\d{1,2} [A-Za-z]+ \d{4})',    # Published: 1 January 2023
                            r'Published:?\s*(\d{4}-\d{2}-\d{2})',           # Published: 2023-01-01
                            r'Published online:?\s*([A-Za-z]+ \d{1,2},? \d{4})',  # Published online: January 1, 2023
                            r'Published online:?\s*(\d{1,2} [A-Za-z]+ \d{4})',    # Published online: 1 January 2023
                            r'Published online:?\s*(\d{4}-\d{2}-\d{2})',          # Published online: 2023-01-01
                            r'Online:?\s*([A-Za-z]+ \d{1,2},? \d{4})',     # Online: January 1, 2023
                            r'Date:?\s*([A-Za-z]+ \d{1,2},? \d{4})',       # Date: January 1, 2023
                            r'Date:?\s*(\d{1,2} [A-Za-z]+ \d{4})',         # Date: 1 January 2023
                            r'(\d{1,2} [A-Za-z]{3} \d{4})',               # 20 Mar 2025 (Nature格式)
                            r'(\d{1,2} [A-Za-z]+ \d{4})\s*[•·]',          # 1 January 2023 •
                            r'([A-Za-z]+ \d{1,2},? \d{4})\s*[•·]'         # January 1, 2023 •
                        ]
                        
                        date_str = None
                        matched_pattern = None
                        for pattern in date_patterns:
                            match = re.search(pattern, header_text)
                            if match:
                                date_str = match.group(1)
                                matched_pattern = pattern
                                date_elements.append((f"regex: {pattern}", date_str))
                                self.logger.debug(f"通过正则表达式 '{pattern}' 找到日期: {date_str}")
                                
                                # 尝试解析日期
                                parsed_date = self._parse_date_string(date_str)
                                if parsed_date:
                                    published_time = parsed_date
                                    self.logger.info(f"从文本中提取到日期: {date_str} -> {parsed_date}")
                                    break
                
                # 如果所有在线提取方法都失败，尝试从URL中提取年份作为最后的解决方案
                if not published_time:
                    match = re.search(r'(\d{4})-\d+', url)
                    if match:
                        year = int(match.group(1))
                        if 2000 <= year <= datetime.now().year:
                            # 使用URL中的年份和当前的月日作为近似日期
                            current_date = datetime.now()
                            published_time = datetime(year, current_date.month, current_date.day)
                            self.logger.info(f"从URL '{url}' 中提取到日期年份: {year}，使用近似日期: {published_time}")
            
            return {
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "journal": journal,
                "published_time": published_time,
                "doi": doi
            }
            
        except Exception as e:
            self.logger.error(f"获取文章详情失败: {url}, 错误: {str(e)}")
            return {"title": "", "abstract": "", "authors": "", "journal": "", "published_time": None, "doi": ""}
    
    def _extract_jsonld_data(self, soup):
        """从页面的JSON-LD结构化数据中提取文章信息"""
        try:
            script_tags = soup.find_all('script', type='application/ld+json')
            result = {}
            
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    
                    # 处理可能的各种JSON-LD结构
                    if isinstance(data, dict):
                        # 处理@graph结构
                        if '@graph' in data and isinstance(data['@graph'], list):
                            for item in data['@graph']:
                                if isinstance(item, dict) and item.get('@type') in ['ScholarlyArticle', 'Article', 'NewsArticle']:
                                    self._extract_from_jsonld_item(item, result)
                        # 处理单一项
                        elif data.get('@type') in ['ScholarlyArticle', 'Article', 'NewsArticle']:
                            self._extract_from_jsonld_item(data, result)
                except Exception as e:
                    self.logger.debug(f"解析JSON-LD数据块出错: {str(e)}")
                    continue
            
            return result
        except Exception as e:
            self.logger.warning(f"从JSON-LD提取数据失败: {str(e)}")
        
        return {}
        
    def _extract_from_jsonld_item(self, data, result):
        """从单个JSON-LD项中提取信息"""
        # 提取标题
        if 'headline' in data and not result.get('title'):
            result['title'] = data['headline']
        elif 'name' in data and not result.get('title'):
            result['title'] = data['name']
        
        # 提取摘要
        if 'description' in data and (not result.get('abstract') or len(data['description']) > len(result.get('abstract', ''))):
            result['abstract'] = data['description']
        elif 'abstract' in data and (not result.get('abstract') or len(data['abstract']) > len(result.get('abstract', ''))):
            result['abstract'] = data['abstract']
                        
        # 提取DOI
        if 'sameAs' in data and not result.get('doi'):
            if isinstance(data['sameAs'], list):
                for same_as in data['sameAs']:
                    if isinstance(same_as, str) and 'doi.org' in same_as:
                        result['doi'] = same_as.split('doi.org/')[-1]
                        break
            elif isinstance(data['sameAs'], str) and 'doi.org' in data['sameAs']:
                result['doi'] = data['sameAs'].split('doi.org/')[-1]
        
        # 直接从DOI字段提取
        if 'doi' in data and not result.get('doi'):
            result['doi'] = data['doi']
        
        # 提取期刊
        if 'isPartOf' in data and not result.get('journal'):
            if isinstance(data['isPartOf'], dict) and 'name' in data['isPartOf']:
                result['journal'] = data['isPartOf']['name']
            elif isinstance(data['isPartOf'], str):
                result['journal'] = data['isPartOf']
        
        # 提取发布者作为备用期刊名称
        if 'publisher' in data and not result.get('journal'):
            if isinstance(data['publisher'], dict) and 'name' in data['publisher']:
                result['journal'] = data['publisher']['name']
            elif isinstance(data['publisher'], str):
                result['journal'] = data['publisher']
        
        # 提取作者
        if 'author' in data and not result.get('authors'):
            if isinstance(data['author'], list):
                author_names = []
                for author in data['author']:
                    if isinstance(author, dict) and 'name' in author:
                        author_names.append(author['name'])
                    elif isinstance(author, str):
                        author_names.append(author)
                if author_names:
                    result['authors'] = ', '.join(author_names)[:800]
            elif isinstance(data['author'], dict) and 'name' in data['author']:
                result['authors'] = data['author']['name'][:800]
            elif isinstance(data['author'], str):
                result['authors'] = data['author'][:800]
        
        # 提取发布日期
        if 'datePublished' in data and not result.get('datePublished'):
            date_str = data['datePublished']
            try:
                # 尝试ISO格式
                result['datePublished'] = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError, AttributeError):
                try:
                    # 尝试常见日期格式
                    date_formats = [
                        '%Y-%m-%d',
                        '%Y/%m/%d',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%dT%H:%M:%SZ'
                    ]
                    for fmt in date_formats:
                        try:
                            result['datePublished'] = datetime.strptime(date_str, fmt)
                            break
                        except (ValueError, TypeError):
                            continue
                except Exception:
                    pass

    def _fetch_from_journal_pages(self, time_limit=None):
        """从期刊页面抓取文章（支持分页）"""
        results = []
        
        for journal_entry in self.journal_pages:
            # 兼容新旧格式
            if isinstance(journal_entry, dict):
                journal_name = journal_entry.get("name", "Nature")
                journal_urls = journal_entry.get("urls", [])
            else:
                journal_name = "Nature"
                journal_urls = [journal_entry]
                
            for journal_url in journal_urls:
                self.logger.info(f"从期刊页面抓取: {journal_url} ({journal_name})")
                
                # 记录空页面的连续次数
                empty_pages_count = 0
                max_empty_pages = 3  # 如果连续3个页面为空，则停止抓取该期刊
                
                # 分页参数
                page = 1
                max_pages = 5  # 限制最多抓取5页
                
                while page <= max_pages and empty_pages_count < max_empty_pages:
                    try:
                        # 构建分页URL，保留现有的日期参数
                        if '?' in journal_url:
                            page_url = f"{journal_url}&page={page}"
                        else:
                            page_url = f"{journal_url}?page={page}"
                            
                        self.logger.info(f"抓取页面: {page_url}")
                        
                        response = requests.get(page_url, headers=self.headers, timeout=15)
                        if response.status_code != 200:
                            self.logger.warning(f"页面请求失败: {page_url}, 状态码: {response.status_code}")
                            break
                        
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 尝试多种选择器找到文章链接
                        article_links = []
                        article_dates = {}  # 存储文章URL与日期的映射
                        
                        # 尝试各种可能的文章链接选择器
                        selectors = [
                            'li.app-article-list-row h3 a',  # 新版布局
                            'article h3 a',                  # 标准布局
                            'h3.c-card__title a',            # 卡片布局
                            'h3.article-item__title a',      # 旧版布局
                            'h2.c-card__title a',            # 另一种卡片布局
                            'a.c-card__link',                # 直接链接
                            'h2 a.c-card-headline__link',    # 头条样式
                            '.app-article-list-row__item a', # 简化布局
                            '.c-card__link',                 # 通用卡片链接
                            '.c-teaser__link',               # 摘要链接
                            '.article__link',                # 文章链接
                            'a[data-track-action="view article"]', # 通过数据属性查找
                            'a[href*="/articles/"]'          # 通过URL模式查找
                        ]
                        
                        # 1. 首先尝试查找文章容器，这样可以同时提取日期和链接
                        article_containers = soup.select('article, .c-card, .app-article-list-row, .u-list-reset li')
                        
                        # 从文章容器中提取文章链接和日期
                        for container in article_containers:
                            # 提取链接
                            link_elem = container.select_one('a[href*="/articles/"]')
                            if not link_elem or not link_elem.get('href'):
                                continue
                                
                            href = link_elem.get('href')
                            # 处理相对URL
                            if href.startswith('/'):
                                href = f"https://www.nature.com{href}"
                            elif not (href.startswith('http://') or href.startswith('https://')):
                                continue
                                
                            # 提取日期 - 尝试多种日期选择器
                            date_elem = None
                            date_selectors = [
                                'time',                     # 通用time标签
                                '.c-meta time',              # Nature新布局
                                'span[itemprop="datePublished"]', # 带有itemprop属性的span
                                '.c-article-date',           # 文章日期类
                                '.c-article-info',           # 文章信息类
                                'div > span:nth-child(2)',   # 第二个span子元素(常见布局)
                                '.app-article-list-row__item--meta' # 列表页元数据
                            ]
                            
                            for ds in date_selectors:
                                date_elem = container.select_one(ds)
                                if date_elem:
                                    break
                                    
                            # 如果找到日期元素，尝试提取日期文本
                            date_text = None
                            if date_elem:
                                # 优先从datetime属性获取
                                if date_elem.has_attr('datetime'):
                                    date_text = date_elem.get('datetime')
                                else:
                                    date_text = date_elem.get_text().strip()
                                    
                                # 如果找到日期文本，尝试解析
                                if date_text:
                                    # 尝试直接从列表页面解析日期
                                    date_obj = self._parse_date_string(date_text)
                                    if date_obj:
                                        article_dates[href] = date_obj
                                        self.logger.info(f"从列表页提取到日期: {href} -> {date_obj}")
                            
                            # 将链接添加到列表
                            article_links.append(link_elem)
                                
                        # 2. 如果通过容器找不到足够的链接，使用直接的链接选择器
                        if len(article_links) == 0:
                            for selector in selectors:
                                links = soup.select(selector)
                                if links:
                                    article_links.extend(links)
                                    self.logger.debug(f"使用选择器 '{selector}' 找到 {len(links)} 个链接")
                        
                        # 过滤重复的链接，保留唯一URL
                        processed_urls = set()
                        unique_links = []
                        
                        for link in article_links:
                            href = link.get('href')
                            if not href:
                                continue
                                
                            # 处理相对URL
                            if href.startswith('/'):
                                href = f"https://www.nature.com{href}"
                            elif not (href.startswith('http://') or href.startswith('https://')):
                                # 跳过非HTTP链接
                                continue
                                
                            # 确保是文章页面链接
                            if '/articles/' in href and href not in processed_urls:
                                unique_links.append(href)
                                processed_urls.add(href)
                        
                        self.logger.info(f"找到 {len(unique_links)} 个唯一文章链接")
                        
                        # 如果没有找到任何链接，增加空页面计数
                        if not unique_links:
                            empty_pages_count += 1
                            self.logger.warning(f"页面 {page} 未找到文章链接 - 空页面计数: {empty_pages_count}")
                            page += 1
                            continue
                        
                        # 重置空页面计数
                        empty_pages_count = 0
                        
                        # 处理找到的链接
                        article_count = 0
                        date_found_count = 0
                        date_missing_count = 0
                        list_date_count = 0  # 从列表页获取到日期的数量
                        
                        for article_url in unique_links:
                            try:
                                # 获取文章详情
                                article_data = self._fetch_article_details(article_url)
                                
                                # 设置文章URL
                                article_data["article_url"] = article_url
                                
                                # 跳过没有标题或摘要的文章
                                if not article_data.get("title") or not article_data.get("abstract"):
                                    self.logger.debug(f"跳过缺少标题或摘要的文章: {article_url}")
                                    continue
                                
                                # 设置期刊名称
                                article_data["journal"] = journal_name
                                
                                # 如果详情页没有提取到日期，但列表页有，则使用列表页的日期
                                if not article_data.get("published_time") and article_url in article_dates:
                                    article_data["published_time"] = article_dates[article_url]
                                    self.logger.info(f"使用列表页面提取的日期: {article_dates[article_url]}")
                                    list_date_count += 1
                                
                                # 统计日期数据
                                if article_data.get("published_time"):
                                    date_found_count += 1
                                else:
                                    date_missing_count += 1
                                    # 尝试从URL或其他特征提取日期信息
                                    # Nature URL有时包含年份信息，如https://www.nature.com/articles/s41586-023-05881-4
                                    # 其中，2023可以作为发布年份的线索
                                    match = re.search(r'(\d{4})-\d+', article_url)
                                    if match:
                                        year = int(match.group(1))
                                        if 2000 <= year <= datetime.now().year:
                                            # 使用URL中的年份和当前的月日作为近似日期
                                            current_date = datetime.now()
                                            approx_date = datetime(year, current_date.month, current_date.day)
                                            article_data["published_time"] = approx_date
                                            self.logger.info(f"从URL提取到日期年份: {year}，使用近似日期: {approx_date}")
                                            date_found_count += 1
                                            date_missing_count -= 1
                                
                                # 检查时间限制
                                if time_limit and article_data.get("published_time"):
                                    # 只有当有发布日期且早于时间限制时才跳过
                                    if article_data["published_time"] < time_limit:
                                        self.logger.debug(f"跳过较早的文章: {article_data['title']} ({article_data['published_time']})")
                                        continue
                                elif time_limit:
                                    # 如果有时间限制但没有发布日期，需要判断是否应该包含
                                    # 我们选择包含它，但记录一个警告
                                    self.logger.warning(f"文章缺少发布日期，无法应用时间过滤: {article_data['title']}")
                                
                                # 如果没有发布时间，设为当前时间以便保存到数据库
                                if article_data.get("published_time") is None:
                                    article_data["published_time"] = datetime.now()
                                    self.logger.warning(f"文章缺少发布日期，使用当前时间: {article_data['title']}")
                                
                                results.append(article_data)
                                article_count += 1
                                self.logger.info(f"成功获取文章: {article_data['title']}")
                            except Exception as e:
                                self.logger.error(f"处理文章 {article_url} 出错: {str(e)}")
                        
                        self.logger.info(f"页面 {page} 成功获取 {article_count} 篇文章，有日期: {date_found_count}(列表页:{list_date_count})，无日期: {date_missing_count}")
                        
                        # 间隔一段时间，避免请求过于频繁
                        time.sleep(2)
                        
                        # 处理下一页
                        page += 1
                        
                    except Exception as e:
                        self.logger.error(f"抓取期刊页面失败: {str(e)}")
                        break
        
        self.logger.info(f"从期刊页面共抓取到 {len(results)} 篇文章")
        return results
        
    def _parse_date_string(self, date_str):
        """解析日期字符串为datetime对象"""
        if not date_str:
            return None
            
        # 清理日期字符串
        date_str = re.sub(r'\s+', ' ', date_str).strip()
        
        # 尝试多种日期格式解析
        date_formats = [
            '%Y-%m-%d',          # 2023-01-01
            '%Y/%m/%d',          # 2023/01/01
            '%d %B %Y',          # 1 January 2023
            '%d %b %Y',          # 1 Jan 2023 
            '%B %d, %Y',         # January 1, 2023
            '%B %d %Y',          # January 1 2023
            '%d-%b-%Y',          # 01-Jan-2023
            '%b %d, %Y',         # Jan 1, 2023
            '%Y-%m-%dT%H:%M:%S', # 2023-01-01T12:00:00
            '%Y-%m-%dT%H:%M:%SZ', # 2023-01-01T12:00:00Z
            '%a, %d %b %Y %H:%M:%S %z', # RFC 2822 format
            '%Y%m%d'             # 20230101
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
                
        # 尝试处理Nature网站特有的日期格式 (例如 "20 Mar 2025")
        match = re.match(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', date_str)
        if match:
            day, month_abbr, year = match.groups()
            # 映射月份缩写到数字
            month_map = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            if month_abbr in month_map:
                try:
                    return datetime(int(year), month_map[month_abbr], int(day))
                except ValueError:
                    pass
        
        # 如果所有格式都失败，尝试更宽松的正则表达式
        patterns = [
            # "DD Month YYYY" 或 "DD Mon YYYY"
            r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\s+(\d{4})',
            # "Month DD, YYYY" 或 "Mon DD, YYYY"
            r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})',
            # "YYYY-MM-DD"
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            # 简单年份
            r'(\d{4})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    # 根据不同模式处理
                    if re.match(r'\d{4}', groups[0]):  # YYYY-MM-DD 格式
                        year, month, day = groups
                        try:
                            return datetime(int(year), int(month), int(day))
                        except ValueError:
                            continue
                    elif re.match(r'[A-Za-z]+', groups[0]):  # Month DD, YYYY 格式
                        month_name, day, year = groups
                        # 尝试将月份名称转换为数字
                        try:
                            month_num = self._month_name_to_number(month_name)
                            if month_num:
                                return datetime(int(year), month_num, int(day))
                        except ValueError:
                            continue
                    else:  # DD Month YYYY 格式
                        day, month_name, year = groups
                        try:
                            month_num = self._month_name_to_number(month_name)
                            if month_num:
                                return datetime(int(year), month_num, int(day))
                        except ValueError:
                            continue
                elif len(groups) == 1:  # 仅年份
                    year = groups[0]
                    try:
                        return datetime(int(year), 1, 1)  # 默认为该年1月1日
                    except ValueError:
                        continue
        
        return None
    
    def _month_name_to_number(self, month_name):
        """将月份名称转换为数字"""
        month_name = month_name.lower()
        month_map = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12
        }
        
        for name, num in month_map.items():
            if name in month_name or month_name in name:
                return num
        
        return None 