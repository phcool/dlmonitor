import os, sys
from ..db import create_engine
from .paper_source import PaperSource
from sqlalchemy_searchable import search
from sqlalchemy import desc, func
import time
from time import mktime
from datetime import datetime, timedelta
import logging
import arxiv
from sentence_transformers import SentenceTransformer
import numpy as np
from pgvector.sqlalchemy import Vector
from dlmonitor.settings import DEFAULT_MODEL

SEARCH_KEY = "cat:cs+OR+cat:stat.ML"

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

    def _process_batch(self, session, batch, model):
        """
        处理论文批次并添加到数据库
        
        Args:
            session: 数据库会话
            batch: 论文批次
            model: 嵌入模型
            existing_urls: 已存在的URL集合（如果为None则会查询）
            
        Returns:
            tuple: (新增论文数量, 每个类别的论文数量字典)
        """
        from ..db import ArxivModel
        
        # 如果没有提供现有URL，则查询数据库
        arxiv_urls = [paper.entry_id for paper in batch]
        existing_urls = {url[0] for url in session.query(ArxivModel.arxiv_url).filter(ArxivModel.arxiv_url.in_(arxiv_urls)).all()}
        
        # 准备新论文数据
        new_papers = []
        batch_new_count = 0
        papers_per_category = {}
        
        for paper in batch:
            arxiv_url = paper.entry_id
            
            # 跟踪每个类别的论文数量
            for category in paper.categories:
                if category not in papers_per_category:
                    papers_per_category[category] = 0
                papers_per_category[category] += 1
            
            # 只处理新论文
            if arxiv_url not in existing_urls:
                batch_new_count += 1
                
                # 准备论文数据
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
                
                # 处理论文数据并生成嵌入
                processed_data, embedding = self._process_paper_metadata(paper_data, model)
                
                # 创建新论文记录
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
        
        # 将新论文添加到会话
        if new_papers:
            for new_paper in new_papers:
                session.add(new_paper)
            session.commit()
        
        return batch_new_count, papers_per_category
    
    def _fetch(self, search_queries, max_nums=None, model=None, batch_size=32, stop_on_consecutive_empty=False, time_limit=None):
        """
        通用论文获取函数，支持单个或多个搜索查询
        
        Args:
            search_queries: 单个查询或查询生成器，每个查询为(query_string, sort_by)元组
            max_nums: 最大获取论文数量
            model: 预加载的SentenceTransformer模型
            batch_size: 处理的批次大小
            stop_on_consecutive_empty: 是否在连续空批次后停止
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        from ..db import session_scope, ArxivModel
        
        # 使用提供的模型或加载新模型
        if model is None:
            model = SentenceTransformer(DEFAULT_MODEL)
            
        if max_nums is None:
            max_nums = self.MAX_PAPERS_PER_SOURCE
            
        # 确保search_queries是可迭代的
        if not hasattr(search_queries, '__iter__') or isinstance(search_queries, tuple):
            search_queries = [search_queries]
            
        total_new = 0
        total_fetched = 0
        all_categories_count = {}
        
        # 处理每个查询
        for query_idx, (query_string, sort_criterion) in enumerate(search_queries):
            if isinstance(query_string, str):
                self.logger.info(f"执行查询 {query_idx+1}/{len(search_queries)}: {query_string}")
            
            # 创建客户端
            client = arxiv.Client(
                page_size=100,
                delay_seconds=3,
                num_retries=3
            )
            
            # 创建搜索查询
            search_query = arxiv.Search(
                query=query_string,
                max_results=min(max_nums, 2000),  # arXiv API限制
                sort_by=sort_criterion
            )
            
            try:
                # 获取结果
                results_iterator = client.results(search_query)
                
                # 处理结果批次
                batch = []
                query_total = 0
                consecutive_empty_batches = 0
                
                for result in results_iterator:
                    # 添加到当前批次
                    batch.append(result)
                    total_fetched += 1
                    query_total += 1
                    
                    # 达到批次大小或已处理所有结果
                    if len(batch) >= batch_size or total_fetched >= max_nums:
                        with session_scope() as session:
                            # 处理批次
                            batch_new, batch_categories = self._process_batch(session, batch, model)
                            total_new += batch_new
                            
                            # 更新类别计数
                            for cat, count in batch_categories.items():
                                all_categories_count[cat] = all_categories_count.get(cat, 0) + count
                            
                            # 更新连续空批次计数
                            if batch_new > 0:
                                consecutive_empty_batches = 0
                            else:
                                consecutive_empty_batches += 1
                        
                        batch = []
                        
                        # 停止条件
                        if total_fetched >= max_nums:
                            break
                        
                        if stop_on_consecutive_empty and query_total >= 100 and consecutive_empty_batches >= 3:
                            self.logger.info(f"连续{consecutive_empty_batches}个空批次，停止获取")
                            break
                        
                        # 休息一下，避免过度请求
                        time.sleep(1)
                
                # 处理剩余批次
                if batch:
                    with session_scope() as session:
                        batch_new, batch_categories = self._process_batch(session, batch, model)
                        total_new += batch_new
                        
                        # 更新类别计数
                        for cat, count in batch_categories.items():
                            all_categories_count[cat] = all_categories_count.get(cat, 0) + count
                
            except arxiv.UnexpectedEmptyPageError as e:
                self.logger.warning(f"获取arXiv数据时出现空页面错误: {str(e)}")
                
                # 处理任何剩余的论文
                if batch:
                    with session_scope() as session:
                        batch_new, batch_categories = self._process_batch(session, batch, model)
                        total_new += batch_new
                        
                        # 更新类别计数
                        for cat, count in batch_categories.items():
                            all_categories_count[cat] = all_categories_count.get(cat, 0) + count
            
            except Exception as e:
                self.logger.error(f"获取arXiv论文时出错: {str(e)}")
                if batch:
                    with session_scope() as session:
                        batch_new, batch_categories = self._process_batch(session, batch, model)
                        total_new += batch_new
        
        # 简单统计主要类别的论文数量
        main_cats = ["cs.CV", "cs.AI", "cs.LG", "cs.CL", "cs.NE", "stat.ML"]
        
        self.logger.info(f"arXiv论文获取完成。共获取{total_fetched}篇论文，其中新增{total_new}篇。")
        self.logger.info(f"cs.CV:{all_categories_count.get('cs.CV', 0)}, cs.AI:{all_categories_count.get('cs.AI', 0)}, cs.LG:{all_categories_count.get('cs.LG', 0)}, cs.CL:{all_categories_count.get('cs.CL', 0)}, cs.NE:{all_categories_count.get('cs.NE', 0)}, stat.ML:{all_categories_count.get('stat.ML', 0)}")        
        return total_new > 0

    def fetch_new(self, max_nums=None, model=None):
        """
        获取最近一天内的arXiv论文并存储到数据库。
        
        Args:
            model: 预加载的SentenceTransformer模型
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        # 获取当前日期和昨天日期
        today = datetime.now()
        yesterday = today - timedelta(days=7)
        
        # 格式化日期为arXiv查询格式 YYYYMMDD
        today_str = today.strftime("%Y%m%d")
        yesterday_str = yesterday.strftime("%Y%m%d")
        
        # 基础分类查询
        categories = SEARCH_KEY.replace("+OR+", " OR ")
        
        # 创建带有日期范围的查询
        date_range_query = f"({categories}) AND submittedDate:[{yesterday_str}0000 TO {today_str}2359]"
        
        # 创建查询元组
        search_query = (date_range_query, arxiv.SortCriterion.SubmittedDate)
        
        self.logger.info(f"开始获取arXiv过去24小时内的论文... (最多获取{self.MAX_PAPERS_PER_SOURCE}篇)")
        self.logger.info(f"查询条件: {date_range_query}")
        
        # 调用通用获取函数，不使用连续空批次停止，确保获取所有新论文
        return self._fetch(
            search_query, 
            max_nums=max_nums,
            model=model,
            batch_size=32,
            stop_on_consecutive_empty=False  # 确保获取所有符合条件的论文
        )

    def fetch_all(self,max_nums=None, model=None):
        """
        一次性获取大量arXiv论文，用于初始填充数据库。
        
        Args:
            model: 预加载的SentenceTransformer模型
            
        Returns:
            bool: 如果获取了新论文返回True，否则返回False
        """
        # 保存并设置更高的最大论文数
        original_max = self.MAX_PAPERS_PER_SOURCE
        if max_nums is None:
            max_nums = 10000  # 1万篇论文
        
        self.logger.info(f"开始从arXiv大量获取论文... (最大获取量: {max_nums}篇)")
        
        # 创建多个搜索查询，基于类别和时间范围
        categories = ["cs.CV", "cs.AI", "cs.LG", "cs.CL", "cs.NE", "stat.ML"]
        
        # 获取当前年份
        current_year = datetime.now().year
        
        # 定义时间范围（从当前年份）
        year_ranges = []
        for year in range(current_year, current_year + 1):
            # 每年按季度分
            year_ranges.append((f"{year}01", f"{year}03"))  # Q1
            year_ranges.append((f"{year}04", f"{year}06"))  # Q2
            year_ranges.append((f"{year}07", f"{year}09"))  # Q3
            year_ranges.append((f"{year}10", f"{year}12"))  # Q4
        
        # 创建所有查询
        search_queries = []
        for category in categories:
            for start_date, end_date in year_ranges:
                # 创建带有日期范围的查询字符串
                date_query = f"cat:{category} AND submittedDate:[{start_date}0000 TO {end_date}2359]"
                # 按提交日期排序
                search_queries.append((date_query, arxiv.SortCriterion.SubmittedDate))
        
        # 调用通用获取函数，不设置连续空批次停止
        result = self._fetch(
            search_queries, 
            max_nums=max_nums,
            model=model,
            batch_size=100,
            stop_on_consecutive_empty=False
        )
        
        # 恢复原始值
        self.MAX_PAPERS_PER_SOURCE = original_max
        
        return result
