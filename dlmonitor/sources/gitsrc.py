"""
GitHub source implementation for fetching code repositories.
"""
import os
import requests
from datetime import datetime, timedelta
from .code_source import CodeSource
from ..db_models import GitHubModel
import numpy as np
import time
import base64
from dlmonitor.settings import DEFAULT_MODEL

class GitSource(CodeSource):
    """GitHub source implementation"""
    
    def __init__(self):
        super(GitSource, self).__init__()
        self.api_base = "https://api.github.com"
        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable is not set")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 定义基础搜索查询模板
        self.base_search_queries = [
            # 计算机科学总类
            "topic:computer-science",
            # 人工智能和机器学习
            "(topic:artificial-intelligence OR topic:ai OR topic:ml OR topic:machine-learning)",
            # 深度学习和大模型
            "(topic:deep-learning OR topic:llm OR topic:large-language-model)",
            # 计算机视觉
            "(topic:computer-vision OR topic:cv OR topic:image-processing)",
            # 自然语言处理
            "(topic:nlp OR topic:natural-language-processing)",
            # 机器人
            "(topic:robotics OR topic:robot OR topic:automation)",
            # 软件工程
            "(topic:software-engineering OR topic:devops OR topic:ci-cd)",
            # 分布式系统
            "(topic:distributed-systems OR topic:cloud OR topic:microservices)",
            # 量子计算
            "(topic:quantum-computing OR topic:quantum)",
            # 数据科学
            "(topic:data-science OR topic:big-data OR topic:analytics)"
        ]
    
    def _get_model_class(self):
        """Get the GitHub model class"""
        return GitHubModel
    
    
    def _process_repo_data(self, repo_data, embedding_model=None):
        """
        Process GitHub repository data and generate embedding.
        
        Args:
            repo_data: Dictionary with repository metadata from GitHub API
            embedding_model: Optional model to generate embeddings
            
        Returns:
            tuple: (processed_data, embedding)
        """
        # Get README content
        readme = ""
        try:
            readme_response = requests.get(
                f"{self.api_base}/repos/{repo_data['full_name']}/readme",
                headers=self.headers
            )
            if readme_response.status_code == 200:
                readme_data = readme_response.json()
                if 'content' in readme_data:
                    content = readme_data.get('content', '')
                    try:
                        # README 内容是 Base64 编码的
                        decoded_content = base64.b64decode(content).decode('utf-8')
                        readme = decoded_content[:10000]  # 限制长度避免过大
                    except Exception as e:
                        self.logger.error(f"Failed to decode README: {str(e)}")
                        readme = ""
        except Exception as e:
            self.logger.error(f"Failed to fetch README: {str(e)}")
        
        # Process text fields - 确保非空
        repo_name = repo_data.get('name', '') or ''
        repo_name = repo_name.strip()
        
        description = repo_data.get('description') or ''
        description = description.replace("\n", " ").replace("  ", " ")
        
        full_name = repo_data.get('full_name', '') or ''
        
        # 安全地处理主题标签
        topics = repo_data.get('topics', [])
        if topics and isinstance(topics, list):
            topics_str = ','.join(topics)
        else:
            topics_str = ''
        
        # Generate embedding if model is provided
        embedding = None
        if embedding_model and (repo_name or description or readme or topics_str):
            try:
                repo_text = f"Repository: {repo_name}\nDescription: {description}\nTopics: {topics_str}\nReadme: {readme}"
                embedding = embedding_model.encode(repo_text).astype(np.float32)
            except Exception as e:
                self.logger.error(f"Failed to generate embedding: {str(e)}")
        
        # Update repo_data with processed fields
        processed_data = {
            'repo_name': repo_name,
            'full_name': full_name,
            'description': description,
            'readme': readme,
            'topics': topics_str
        }
        
        return processed_data, embedding
    
    def _filter_repo(self, repo_data, processed_data):
        """
        过滤低质量或不活跃的仓库
        
        Args:
            repo_data: 原始仓库数据
            processed_data: 处理后的仓库数据
            
        Returns:
            bool: 如果仓库应该被保留返回True，否则返回False
            str: 过滤原因，如果没有被过滤则为None
        """
        # 1. 内容质量过滤
        
        # 检查README长度 - README太短的仓库往往是低质量的
        readme = processed_data.get('readme', '')
        if len(readme) < 200:  # 少于200字符的README通常是不完整的
            return False, "README too short"
        
        # 检查描述 - 没有描述或描述太短的仓库通常是不完整的
        description = processed_data.get('description', '')
        if not description or len(description) < 10:
            return False, "Description too short or missing"
        
        # 检查仓库名称是否包含示例、测试等关键词 - 这些往往是临时项目
        name_lower = processed_data.get('repo_name', '').lower()
        full_name_lower = processed_data.get('full_name', '').lower()
        low_quality_keywords = ['example', 'test', 'demo', 'sample', 'temp', 'tutorial', 'starter']
        if any(keyword in name_lower for keyword in low_quality_keywords):
            return False, f"Repository name suggests low quality: {name_lower}"
        
        # 2. 活跃度过滤
        
        # 检查最近更新时间 - 使用repo_data中的更新时间
        try:
            updated_at = datetime.strptime(repo_data.get('updated_at', ''), '%Y-%m-%dT%H:%M:%SZ')
            created_at = datetime.strptime(repo_data.get('created_at', ''), '%Y-%m-%dT%H:%M:%SZ')
            
            # 计算仓库年龄（天数）
            repo_age_days = (datetime.now() - created_at).days
            
            # 计算最后更新距今时间（天数）
            days_since_update = (datetime.now() - updated_at).days
            
            # 对于较老的仓库（超过1年），如果最近6个月没有更新，认为不够活跃
            if repo_age_days > 365 and days_since_update > 180:
                return False, f"Repository inactive: last updated {days_since_update} days ago"
                
            # 对于新仓库，如果创建后从未更新过，可能是低质量的
            if repo_age_days > 30 and abs((updated_at - created_at).total_seconds()) < 3600:
                return False, "Repository not maintained after creation"
                
        except (ValueError, TypeError):
            # 如果日期解析失败，默认通过这项检查
            pass
            
        # 检查提交频率 - 可以通过API额外获取，但这里暂时依赖更新时间和创建时间的比例
        
        # 3. 相对质量过滤
        
        # 看星标数和仓库年龄的比例 - 年龄越大，应该有更多星标
        stars = repo_data.get('stargazers_count', 0)
        
        if repo_age_days > 0:
            stars_per_day = stars / repo_age_days
            
            # 对于较老的仓库（超过2年），如果星标增长率太低，可能不够优质
            if repo_age_days > 730 and stars < 100 and stars_per_day < 0.05:
                return False, f"Low popularity: {stars} stars over {repo_age_days} days"
        
        # 通过所有过滤条件
        return True, None

    def _process_batch(self, session, batch, model, existing_ids=None):
        """
        处理仓库批次并添加到数据库
        
        Args:
            session: 数据库会话
            batch: 仓库数据批次
            model: 嵌入模型
            existing_ids: 已存在的仓库ID集合（如果为None则会查询）
            
        Returns:
            int: 新增仓库数量
        """
        from ..db_models import GitHubModel
        
        # 如果没有提供现有ID，则查询数据库
        if existing_ids is None:
            repo_ids = [str(repo.get('id', '')) for repo in batch]
            repo_ids = [id for id in repo_ids if id]  # 过滤空ID
            if repo_ids:
                existing_ids = {id[0] for id in session.query(GitHubModel.repo_id).filter(GitHubModel.repo_id.in_(repo_ids)).all()}
            else:
                existing_ids = set()
        
        # 处理批次
        new_count = 0
        filtered_count = 0
        filter_reasons = {}
        
        for repo_data in batch:
            try:
                # 检查是否已存在
                repo_id = str(repo_data.get('id', ''))
                if not repo_id or repo_id in existing_ids:
                    continue
                
                # 处理仓库数据
                processed_data, embedding = self._process_repo_data(repo_data, model)
                
                # 质量过滤 - 过滤掉低质量仓库
                should_keep, filter_reason = self._filter_repo(repo_data, processed_data)
                if not should_keep:
                    self.logger.info(f"Filtered repository {processed_data['full_name']}: {filter_reason}")
                    filtered_count += 1
                    filter_reasons[filter_reason] = filter_reasons.get(filter_reason, 0) + 1
                    continue
                
                # 安全地获取值，防止KeyError
                stars = repo_data.get('stargazers_count', 0)
                forks = repo_data.get('forks_count', 0)
                language = repo_data.get('language') or ''
                html_url = repo_data.get('html_url', '')
                clone_url = repo_data.get('clone_url', '')
                
                # 解析日期，确保日期字段存在
                try:
                    updated_at = datetime.strptime(repo_data.get('updated_at', ''), '%Y-%m-%dT%H:%M:%SZ')
                    created_at = datetime.strptime(repo_data.get('created_at', ''), '%Y-%m-%dT%H:%M:%SZ')
                except (ValueError, TypeError):
                    # 如果日期解析失败，使用当前时间
                    self.logger.warning(f"Failed to parse date for repository {processed_data['full_name']}, using current time")
                    updated_at = datetime.now()
                    created_at = datetime.now()
                
                # 创建新仓库对象
                repo = GitHubModel(
                    repo_id=repo_id,
                    repo_name=processed_data['repo_name'],
                    full_name=processed_data['full_name'],
                    description=processed_data['description'],
                    html_url=html_url,
                    clone_url=clone_url,
                    stars=stars,
                    forks=forks,
                    language=language,
                    topics=processed_data['topics'],
                    readme=processed_data['readme'],
                    updated_at=updated_at,
                    created_at=created_at,
                    embedding=embedding
                )
                
                # 添加到数据库会话
                session.add(repo)
                new_count += 1
                self.logger.info(f"Added new repository: {repo.full_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to process repository {repo_data.get('full_name', 'unknown')}: {str(e)}")
                continue
        
        # 记录过滤统计
        if filtered_count > 0:
            self.logger.info(f"Filtered {filtered_count} repositories")
            self.logger.info(f"Filter reasons: {filter_reasons}")
        
        return new_count
    
    def _fetch(self, search_queries, max_nums=None, model=None, batch_size=30):
        """
        通用仓库获取函数，支持单个或多个搜索查询
        
        Args:
            search_queries: 单个查询或查询列表，每个查询为(query_string, sort, order)元组
            max_nums: 最大获取仓库数量
            model: 预加载的SentenceTransformer模型
            batch_size: 处理的批次大小
            
        Returns:
            int: 获取的新仓库数量
        """
        from ..db import get_global_session
        from sentence_transformers import SentenceTransformer
        
        # 使用提供的模型或加载新模型
        if model is None:
            model = SentenceTransformer(DEFAULT_MODEL)
            
        # 如果没有指定最大仓库数，使用类默认值
        if max_nums is None:
            max_nums = self.MAX_REPOS_PER_SOURCE
            
        # 确保search_queries是可迭代的
        if not hasattr(search_queries, '__iter__') or isinstance(search_queries, tuple):
            search_queries = [search_queries]
            
        total_new = 0
        total_fetched = 0
        
        # 用于累积新仓库的列表
        accumulated_repos = []
        
        # 处理每个查询
        for query_idx, (query_string, sort, order) in enumerate(search_queries):
            self.logger.info(f"执行查询 {query_idx+1}/{len(search_queries)}: {query_string}")
            
            # GitHub API 支持的最大每页数量
            per_page = min(100, batch_size)
            
            # 跟踪已处理的仓库ID，避免重复
            processed_ids = set()
            
            # 分页获取所有结果
            page = 1
            while total_fetched < max_nums:
                remaining = max_nums - total_fetched
                
                try:
                    # 获取当前页的结果
                    self.logger.info(f"查询: {query_string}, 页码: {page}, 每页数量: {per_page}")
                    repos = self.search_repos(
                        query_string, 
                        sort=sort, 
                        order=order, 
                        per_page=per_page,
                        page=page
                    )
                    
                    # 如果没有更多结果，跳出循环
                    if not repos:
                        self.logger.info(f"查询 {query_string} 没有更多结果")
                        break
                    
                    # 过滤掉已处理过的仓库
                    new_repos = []
                    for repo in repos:
                        repo_id = str(repo.get('id', ''))
                        if repo_id and repo_id not in processed_ids:
                            processed_ids.add(repo_id)
                            new_repos.append(repo)
                    
                    # 将新仓库添加到累积列表中
                    accumulated_repos.extend(new_repos)
                    
                    # 当累积的仓库数量达到批处理大小时，进行处理
                    if len(accumulated_repos) >= batch_size:
                        with get_global_session() as session:
                            batch_new = self._process_batch(session, accumulated_repos, model)
                            total_new += batch_new
                            total_fetched += len(accumulated_repos)
                            
                            # 提交更改
                            try:
                                session.commit()
                                self.logger.info(f"成功保存 {batch_new} 个新仓库，当前总计: {total_new}")
                            except Exception as e:
                                self.logger.error(f"提交数据库更改时出错: {str(e)}")
                                session.rollback()
                        
                        # 清空累积列表
                        accumulated_repos = []
                    
                    # 如果这一页的结果少于每页数量，说明没有更多结果了
                    if len(repos) < per_page:
                        self.logger.info(f"查询 {query_string} 返回结果 ({len(repos)}) 少于每页数量 ({per_page})，停止获取")
                        break
                    
                    # 进入下一页
                    page += 1
                    
                    # 避免触发 GitHub API 限制
                    time.sleep(2)
                    
                except Exception as e:
                    self.logger.error(f"获取GitHub仓库时出错: {str(e)}")
                    break
            
            # 如果已经获取足够的仓库，跳出查询循环
            if total_fetched >= max_nums:
                self.logger.info(f"已达到最大获取数量 {max_nums}，停止获取")   
                break
        
        # 处理剩余的仓库
        if accumulated_repos:
            with get_global_session() as session:
                batch_new = self._process_batch(session, accumulated_repos, model)
                total_new += batch_new
                total_fetched += len(accumulated_repos)
                
                # 提交更改
                try:
                    session.commit()
                    self.logger.info(f"成功保存最后一批 {batch_new} 个新仓库，当前总计: {total_new}")
                except Exception as e:
                    self.logger.error(f"提交数据库更改时出错: {str(e)}")
                    session.rollback()
                
        self.logger.info(f"GitHub仓库获取完成。共获取{total_fetched}个仓库，其中新增{total_new}个。")
        return total_new
    
    def search_repos(self, query, sort='stars', order='desc', per_page=30, page=1):
        """
        Search GitHub repositories.
        
        Args:
            query: Search query string
            sort: Sort field (stars, forks, updated)
            order: Sort order (asc or desc)
            per_page: Number of results per page
            page: Page number for pagination
            
        Returns:
            list: List of repository data dictionaries
        """
        try:
            response = requests.get(
                f"{self.api_base}/search/repositories",
                params={
                    'q': query,
                    'sort': sort,
                    'order': order,
                    'per_page': per_page,
                    'page': page
                },
                headers=self.headers
            )
            response.raise_for_status()
            self.logger.info(f"GitHub API 请求成功: {response.url}")
            # 检查 API 限制信息
            if 'X-RateLimit-Remaining' in response.headers:
                remaining = response.headers['X-RateLimit-Remaining']
                self.logger.info(f"GitHub API 剩余请求数: {remaining}")
            return response.json().get('items', [])
        except Exception as e:
            self.logger.error(f"Failed to search repositories: {str(e)}")
            return []
    
    def fetch_new(self, max_nums=None, model=None):
        """
        Fetch new repositories from GitHub (last week).
        
        Args:
            model: Optional pre-loaded model for embeddings
            
        Returns:
            int: Number of new repositories fetched
        """
        # 计算一周前的日期
        one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # 构建搜索查询
        search_queries = [
            (f"{query} stars:>100 pushed:>{one_week_ago}", "updated", "desc")
            for query in self.base_search_queries
        ]
        return self._fetch(search_queries, model=model)
    
    def fetch_all(self, max_nums=None, model=None):
        """
        Fetch repositories updated in the last month.
        
        Args:
            model: Optional pre-loaded model for embeddings
            
        Returns:
            int: Total number of repositories fetched
        """
        # 计算一个月前的日期
        one_month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 构建搜索查询
        search_queries = [
            (f"{query} stars:>100 pushed:{one_month_ago}..{today}", "stars", "desc")
            for query in self.base_search_queries
        ]
        
        # 指定 fetch_all 获取更多仓库，每个查询获取更多结果
        return self._fetch(search_queries, model=model, max_nums=max_nums, batch_size=50)   