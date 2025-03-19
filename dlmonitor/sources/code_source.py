"""
Code source base class for code repositories like GitHub, GitLab, etc.
"""
from .base import Source
import numpy as np
from datetime import datetime
import time
from sentence_transformers import SentenceTransformer

class CodeSource(Source):
    """Base class for code repository sources"""
    
    def __init__(self):
        super(CodeSource, self).__init__()
        self.source_type = Source.SOURCE_TYPE_CODE
        self.MAX_REPOS_PER_SOURCE = 100  # 默认最大获取数量
    
    def get_one_post(self, repo_id):
        """
        Get a single code repository by ID.
        
        Args:
            repo_id: ID of the repository to retrieve
            
        Returns:
            object: Repository object if found, None otherwise
        """
        if not repo_id:
            self.logger.error("Invalid repository ID")
            return None
            
        try:
            # 第一步：尝试从数据库获取
            repo = self._get_repo_from_db(repo_id)
            if repo:
                return repo
            
            # 第二步：如果数据库中没有，从外部源获取
            repo = self._fetch_repo_from_external_source(repo_id)
            if repo:
                return repo
                
            return None
        except Exception as e:
            self.logger.error(f"Error in get_one_post: {str(e)}")
            return None
            
    def _get_repo_from_db(self, repo_id):
        """
        从数据库获取仓库数据
        
        Args:
            repo_id: 仓库ID
            
        Returns:
            object: 仓库对象，如果未找到则返回None
        """
        from ..db import get_global_session
        
        # Get the appropriate model class for this source
        model_class = self._get_model_class()
        if not model_class:
            return None
            
        session = get_global_session()
        
        # 使用正确的主键字段进行查询
        primary_key = getattr(model_class, 'repo_id', None) or getattr(model_class, 'id', None)
        if primary_key is None:
            self.logger.error("Could not determine primary key field for repository")
            return None
            
        try:
            query = session.query(model_class).filter(primary_key == repo_id)
            results = query.all()
            
            return results[0] if results else None
        except Exception as e:
            self.logger.error(f"Error querying database for repository {repo_id}: {str(e)}")
            return None
            
    def _fetch_repo_from_external_source(self, repo_id):
        """
        从外部源获取仓库数据（如GitHub API等）
        这是一个钩子方法，默认返回None，子类应该根据需要重写
        
        Args:
            repo_id: 仓库ID
            
        Returns:
            object: 仓库对象，如果未找到则返回None
        """
        return None
        
    def _save_repo_to_db(self, repo):
        """
        将仓库对象保存到数据库
        
        Args:
            repo: 仓库对象
            
        Returns:
            bool: 保存成功返回True，否则返回False
        """
        try:
            from ..db import get_global_session
            session = get_global_session()
            session.add(repo)
            session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Failed to save repository to database: {str(e)}")
            try:
                session.rollback()
            except:
                pass
            return False
    
    def get_posts(self, keywords=None, since=None, start=0, num=20, model=None):
        """
        Get code repositories matching search criteria.
        
        Args:
            keywords (str): Keywords to search for
            since (str): Date string to filter content
            start (int): Start index for pagination
            num (int): Number of posts to return
            model: Optional pre-loaded model for embeddings
            
        Returns:
            list: List of repository objects
        """
        # Get the appropriate model class and session for this source
        model_class = self._get_model_class()
        if not model_class:
            return []
            
        from ..db import get_global_session
        from sqlalchemy import desc
        
        session = get_global_session()
        query = session.query(model_class)
        
        # 确定使用哪个日期字段
        date_field = getattr(model_class, 'updated_at', None)
        if date_field is None:
            date_field = getattr(model_class, 'published_time', None)
        
        if since and date_field is not None:
            # Filter date
            assert isinstance(since, str)
            query = query.filter(date_field >= since)
        
        # Perform keyword search if provided
        if keywords and keywords.strip():
            # Try vector search if available
            results = self._search_by_vector(session, model_class, keywords, start, num, model)
            
            # Fall back to traditional search if vector search is not available
            if not results:
                # Text search based on available fields
                from sqlalchemy import or_
                search_terms = keywords.split()
                filters = []
                
                searchable_fields = []
                
                # 动态确定可搜索字段
                for field_name in ['repo_name', 'description', 'readme', 'title', 'abstract', 'full_name', 'topics']:
                    if hasattr(model_class, field_name):
                        searchable_fields.append(getattr(model_class, field_name))
                    
                for term in search_terms:
                    term_filters = []
                    for field in searchable_fields:
                        term_filters.append(field.ilike(f'%{term}%'))
                    if term_filters:
                        filters.append(or_(*term_filters))
                
                if filters:
                    if date_field is not None:
                        results = (query.filter(*filters)
                                 .order_by(desc(date_field))
                                 .offset(start).limit(num).all())
                    else:
                        results = (query.filter(*filters)
                                 .offset(start).limit(num).all())
                else:
                    results = []
        else:
            # Return recent repositories if no search keywords
            if date_field is not None:
                results = (query.order_by(desc(date_field))
                          .offset(start).limit(num).all())
            else:
                results = query.offset(start).limit(num).all()
        
        return results
    
    def _search_by_vector(self, session, model_class, keywords, start, num, model):
        """
        Search using vector embeddings if available.
        
        Args:
            session: Database session
            model_class: SQLAlchemy model class
            keywords: Search keywords
            start: Start index
            num: Number of results
            model: Optional pre-loaded model for embeddings
            
        Returns:
            list: Search results or empty list if vector search is not available
        """
        # Check if vector search is available
        if not hasattr(model_class, 'embedding'):
            return []
            
        has_embeddings = session.query(model_class).filter(model_class.embedding != None).limit(1).count() > 0
        if not has_embeddings:
            return []
        
        # Generate query embedding
        try:
            if model is None:
                model = SentenceTransformer('all-MiniLM-L6-v2')
            query_embedding = model.encode(keywords).astype(np.float32)
            
            # Use cosine distance method for vector search
            results = (session.query(model_class)
                      .filter(model_class.embedding != None)
                      .order_by(model_class.embedding.cosine_distance(query_embedding))
                      .offset(start).limit(num).all())
            return results
        except Exception as e:
            self.logger.error(f"Vector search failed: {str(e)}")
            return []
    
    def _process_repo_data(self, repo_data, embedding_model=None):
        """
        Process repository data and generate embedding if model is provided.
        基类方法，子类应根据自己的需求重写
        
        Args:
            repo_data: Dictionary with repository metadata
            embedding_model: Optional model to generate embeddings
            
        Returns:
            tuple: (processed_data, embedding)
        """
        # Process text fields with safe handling of None values
        repo_name = repo_data.get('repo_name', '') or ''
        repo_name = repo_name.strip()
        
        description = repo_data.get('description', '') or ''
        description = description.replace("\n", " ").replace("  ", " ")
        
        readme = repo_data.get('readme', '') or ''
        readme = readme.replace("\n", " ").replace("  ", " ")
        
        # Generate embedding if model is provided
        embedding = None
        if embedding_model and (repo_name or description or readme):
            try:
                repo_text = f"Repository: {repo_name}\nDescription: {description}\nReadme: {readme}"
                embedding = embedding_model.encode(repo_text).astype(np.float32)
            except Exception as e:
                self.logger.error(f"Failed to generate embedding: {str(e)}")
        
        # Update repo_data with processed fields
        processed_data = {
            'repo_name': repo_name,
            'description': description,
            'readme': readme
        }
        
        return processed_data, embedding
    
    def _process_batch(self, session, batch, model, existing_ids=None):
        """
        处理仓库批次并添加到数据库
        基类方法，子类应根据自己的需求重写
        
        Args:
            session: 数据库会话
            batch: 仓库数据批次
            model: 嵌入模型
            existing_ids: 已存在的仓库ID集合
            
        Returns:
            int: 新增仓库数量
        """
        self.logger.warning("_process_batch() not implemented in base class")
        return 0
        
    def _fetch(self, search_queries, max_repos=None, model=None, batch_size=10):
        """
        通用仓库获取函数，支持单个或多个搜索查询
        基类方法，子类应根据自己的需求重写
        
        Args:
            search_queries: 单个查询或查询列表
            max_repos: 最大获取仓库数量
            model: 预加载的嵌入模型
            batch_size: 处理的批次大小
            
        Returns:
            int: 获取的新仓库数量
        """
        self.logger.warning("_fetch() not implemented in base class")
        return 0
    
    def fetch_new(self, model=None):
        """
        Fetch new repositories.
        
        Args:
            model: Optional pre-loaded model for embeddings
            
        Returns:
            int: Number of new repositories fetched
        """
        self.logger.warning("fetch_new() not implemented")
        return 0
        
    def fetch_all(self, model=None):
        """
        Fetch a large number of historical repositories.
        
        Args:
            model: Optional pre-loaded model for embeddings
            
        Returns:
            int: Total number of repositories fetched
        """
        self.logger.warning("fetch_all() not implemented")
        return 0
        
    def _link_paper_to_code(self, paper_url, repo_url):
        """
        Create a link between a paper and a code repository.
        
        Args:
            paper_url: URL of the paper
            repo_url: URL of the repository
            
        Returns:
            bool: True if link was created, False otherwise
        """
        # Implementation depends on database structure
        return False
    
    def _get_model_class(self):
        """
        Get the appropriate SQLAlchemy model class for this source.
        Should be implemented by subclasses.
        
        Returns:
            class: SQLAlchemy model class
        """
        return None 