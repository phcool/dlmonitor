"""
Social media source base class for platforms like Twitter, Reddit, etc.
"""
from .base import Source
import numpy as np
from datetime import datetime

class SocialMediaSource(Source):
    """Base class for social media sources"""
    
    def __init__(self):
        super(SocialMediaSource, self).__init__()
        self.source_type = Source.SOURCE_TYPE_SOCIAL
    
    def get_one_post(self, post_id):
        """
        Get a single social media post by ID.
        
        Args:
            post_id: ID of the post to retrieve
            
        Returns:
            object: Post object if found, None otherwise
        """
        from ..db import get_global_session
        
        # Get the appropriate model class for this source
        model_class = self._get_model_class()
        if not model_class:
            return None
            
        session = get_global_session()
        query = session.query(model_class).filter(model_class.id == int(post_id))
        results = query.all()
        
        return results[0] if results else None
    
    def get_posts(self, keywords=None, since=None, start=0, num=80, model=None):
        """
        Get social media posts matching search criteria.
        
        Args:
            keywords (str): Keywords to search for
            since (str): Date string to filter content
            start (int): Start index for pagination
            num (int): Number of posts to return
            model: Optional pre-loaded model for embeddings
            
        Returns:
            list: List of post objects
        """
        # Get the appropriate model class and session for this source
        model_class = self._get_model_class()
        if not model_class:
            return []
            
        from ..db import get_global_session
        from sqlalchemy import desc
        
        session = get_global_session()
        query = session.query(model_class)
        
        if since:
            # Filter date
            assert isinstance(since, str)
            query = query.filter(model_class.created_at >= since)
        
        # Perform keyword search if provided
        if keywords and keywords.strip():
            # Try vector search if available
            results = self._search_by_vector(session, model_class, keywords, start, num, model)
            
            # Fall back to traditional search if vector search is not available
            if not results and hasattr(model_class, 'content'):
                from sqlalchemy import or_
                search_terms = keywords.split()
                filters = []
                for term in search_terms:
                    filters.append(model_class.content.ilike(f'%{term}%'))
                
                results = (query.filter(or_(*filters))
                          .order_by(desc(model_class.created_at))
                          .offset(start).limit(num).all())
        else:
            # Return recent posts if no search keywords
            results = (query.order_by(desc(model_class.created_at))
                      .offset(start).limit(num).all())
        
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
            from sentence_transformers import SentenceTransformer
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
    
    def _process_post_content(self, post_data, embedding_model=None):
        """
        Process post content and generate embedding if model is provided.
        
        Args:
            post_data: Dictionary with post metadata
            embedding_model: Optional model to generate embeddings
            
        Returns:
            tuple: (processed_data, embedding)
        """
        # Process text content
        content = post_data.get('content', '').replace("\n", " ").replace("  ", " ")
        author = post_data.get('author', '')
        
        # Generate embedding if model is provided
        embedding = None
        if embedding_model and content:
            try:
                post_text = f"{content}"
                if author:
                    post_text = f"Author: {author}\nContent: {content}"
                embedding = embedding_model.encode(post_text).astype(np.float32)
            except Exception as e:
                self.logger.error(f"Failed to generate embedding: {str(e)}")
        
        # Update post_data with processed fields
        post_data['content'] = content
        
        return post_data, embedding
    
    def _get_model_class(self):
        """
        Get the appropriate SQLAlchemy model class for this source.
        Should be implemented by subclasses.
        
        Returns:
            class: SQLAlchemy model class
        """
        return None 