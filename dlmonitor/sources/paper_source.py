"""
Paper source base class for academic paper sources like arXiv, Nature, etc.
"""
from .base import Source
import numpy as np
from datetime import datetime
from dlmonitor.settings import DEFAULT_MODEL

class PaperSource(Source):
    """Base class for academic paper sources"""
    
    # Default parameters for paper sources
    
    def __init__(self):
        super(PaperSource, self).__init__()
        self.source_type = Source.SOURCE_TYPE_PAPER
        self.MAX_PAPERS_PER_SOURCE = 1000  # Maximum number of papers to fetch per source
    
    def get_one_post(self, paper_id):
        """
        Get a single paper by ID.
        
        This is a common implementation that can be overridden by subclasses
        with source-specific logic.
        
        Args:
            paper_id: ID of the paper to retrieve
            
        Returns:
            object: Paper object if found, None otherwise
        """
        from ..db import get_global_session
        
        # Get the appropriate model class for this source
        model_class = self._get_model_class()
        if not model_class:
            return None
            
        session = get_global_session()
        query = session.query(model_class).filter(model_class.id == int(paper_id))
        results = query.all()
        
        return results[0] if results else None
    
    def get_posts(self, keywords=None, since=None, start=0, num=20, model=None, sort_type="time"):
        """
        Get papers matching search criteria.
        
        This is a common implementation with vector search support
        that can be overridden by subclasses with source-specific logic.
        
        Args:
            keywords (str): Keywords to search for
            since (str): Date string to filter content
            start (int): Start index for pagination
            num (int): Number of posts to return
            model: Optional pre-loaded model for embeddings
            sort_type (str): Sorting method to use ("time", "relevance", "popularity")
            
        Returns:
            list: List of paper objects
        """
        # Get the appropriate model class and session for this source
        model_class = self._get_model_class()
        if not model_class:
            return []
            
        from ..db import get_global_session
        from sqlalchemy import desc
        
        session = get_global_session()
        query = session.query(model_class)
        
        # 首先进行日期过滤 - 使用published_time字段
        if since and hasattr(model_class, 'published_time'):
            # 转换日期字符串并过滤
            assert isinstance(since, str)
            self.logger.info(f"过滤日期 >= {since}")
            query = query.filter(model_class.published_time >= since)

        # 如果有关键词，进行向量搜索或关键词搜索
        if keywords and keywords.strip():
            # 首先尝试向量搜索 - 无论排序类型如何，都先获取最相关的结果
            vector_results = None
            if hasattr(model_class, 'embedding'):
                try:
                    vector_results = self._search_by_vector(session, model_class, keywords, 0, num * 3, model, date_filtered_query=query)
                    self.logger.info(f"向量搜索返回 {len(vector_results) if vector_results else 0} 条结果")
                except Exception as e:
                    self.logger.error(f"向量搜索失败: {str(e)}")
            
            if vector_results:
                # 根据排序类型对向量搜索结果进行排序
                if sort_type == "time" and hasattr(model_class, 'published_time'):
                    # 对向量搜索结果按时间排序
                    sorted_results = sorted(vector_results, key=lambda x: getattr(x, 'published_time', ''), reverse=True)
                    self.logger.info("向量搜索结果已按时间排序")
                    return sorted_results[start:start+num]
                elif sort_type == "popularity" and hasattr(model_class, 'popularity'):
                    # 对向量搜索结果按热度排序
                    sorted_results = sorted(vector_results, key=lambda x: getattr(x, 'popularity', 0), reverse=True)
                    self.logger.info("向量搜索结果已按热度排序")
                    return sorted_results[start:start+num]
                else:
                    # 默认情况下返回已按相关性排序的结果
                    self.logger.info("返回按相关性排序的向量搜索结果")
                    return vector_results[start:start+num]
            
            # 如果向量搜索不可用或失败，回退到传统关键词搜索
            self.logger.info("回退到关键词搜索")
            from sqlalchemy import or_
            search_terms = keywords.split()
            filters = []
            
            searchable_fields = []
            # 动态确定可搜索字段
            for field_name in ['title', 'abstract', 'authors', 'tag']:
                if hasattr(model_class, field_name):
                    searchable_fields.append(getattr(model_class, field_name))
            
            for term in search_terms:
                term_filters = []
                for field in searchable_fields:
                    term_filters.append(field.ilike(f'%{term}%'))
                if term_filters:
                    filters.append(or_(*term_filters))
            
            if filters:
                query = query.filter(*filters)
        
        # 根据排序类型确定排序方式（针对关键词搜索）
        if sort_type == "time":
            # 按发布时间排序
            if hasattr(model_class, 'published_time'):
                query = query.order_by(desc(model_class.published_time))
        elif sort_type == "popularity":
            # 按热度排序
            if hasattr(model_class, 'popularity'):
                query = query.order_by(desc(model_class.popularity))
        
        # 获取结果
        results = query.offset(start).limit(num).all()
        
        # 如果没有结果且使用了排序，尝试不排序
        if not results and (sort_type == "popularity"):
            if hasattr(model_class, 'published_time'):
                query = query.order_by(desc(model_class.published_time))
                results = query.offset(start).limit(num).all()
        
        return results
    
    def _search_by_vector(self, session, model_class, keywords, start, num, model, date_filtered_query=None):
        """
        Search using vector embeddings if available.
        
        Args:
            session: Database session
            model_class: SQLAlchemy model class
            keywords: Search keywords
            start: Start index
            num: Number of results
            model: Optional pre-loaded model for embeddings
            date_filtered_query: Optional pre-filtered query with date constraints
            
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
            from sentence_transformers import SentenceTransformer
            if model is None:
                model = SentenceTransformer(DEFAULT_MODEL)
            
            query_embedding = model.encode(keywords).astype(np.float32)
            
            # 使用已经过滤的查询（如果提供），否则创建新查询
            base_query = date_filtered_query if date_filtered_query is not None else session.query(model_class)
            
            # Use cosine distance method for vector search
            results = (base_query
                      .filter(model_class.embedding != None)
                      .order_by(model_class.embedding.cosine_distance(query_embedding))
                      .offset(start).limit(num).all())
            return results
        except Exception as e:
            self.logger.error(f"Vector search failed: {str(e)}")
            return []
    
    def _process_paper_metadata(self, paper_data, embedding_model=None):
        """
        Process paper metadata and generate embedding if model is provided.
        
        Args:
            paper_data: Dictionary with paper metadata
            embedding_model: Optional model to generate embeddings
            
        Returns:
            tuple: (processed_data, embedding)
        """
        # Process text fields
        title = paper_data.get('title', '').replace("\n", "").replace("  ", " ")
        abstract = paper_data.get('abstract', '').replace("\n", "").replace("  ", " ")
        authors = paper_data.get('authors', '')[:800]
        
        # Generate embedding if model is provided
        embedding = None
        if embedding_model and title and abstract:
            try:
                paper_text = f"Title: {title}\nAuthors: {authors}\nAbstract: {abstract}"
                embedding = embedding_model.encode(paper_text).astype(np.float32)
            except Exception as e:
                self.logger.error(f"Failed to generate embedding: {str(e)}")
        
        # Update paper_data with processed fields
        paper_data['title'] = title
        paper_data['abstract'] = abstract
        paper_data['authors'] = authors
        
        return paper_data, embedding
    
    def _get_model_class(self):
        """
        Get the appropriate SQLAlchemy model class for this source.
        Should be implemented by subclasses.
        
        Returns:
            class: SQLAlchemy model class
        """
        return None 