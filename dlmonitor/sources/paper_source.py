"""
Paper source base class for academic paper sources like arXiv, Nature, etc.
"""
from .base import Source
import numpy as np
from datetime import datetime

class PaperSource(Source):
    """Base class for academic paper sources"""
    
    # Default parameters for paper sources
    MAX_PAPERS_PER_SOURCE = 1000  # Maximum number of papers to fetch per source
    
    def __init__(self):
        super(PaperSource, self).__init__()
        self.source_type = Source.SOURCE_TYPE_PAPER
    
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
    
    def get_posts(self, keywords=None, since=None, start=0, num=20, model=None):
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
        
        if since:
            # Filter date
            assert isinstance(since, str)
            query = query.filter(model_class.published_time >= since)

            # Vector search if embedding field exists
        results = self._search_by_vector(session, model_class, keywords, start, num, model)
        
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