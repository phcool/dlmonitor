"""
Code source base class for code repositories like GitHub, GitLab, etc.
"""
from .base import Source
import numpy as np
from datetime import datetime

class CodeSource(Source):
    """Base class for code repository sources"""
    
    def __init__(self):
        super(CodeSource, self).__init__()
        self.source_type = Source.SOURCE_TYPE_CODE
    
    def get_one_post(self, repo_id):
        """
        Get a single code repository by ID.
        
        Args:
            repo_id: ID of the repository to retrieve
            
        Returns:
            object: Repository object if found, None otherwise
        """
        from ..db import get_global_session
        
        # Get the appropriate model class for this source
        model_class = self._get_model_class()
        if not model_class:
            return None
            
        session = get_global_session()
        query = session.query(model_class).filter(model_class.id == int(repo_id))
        results = query.all()
        
        return results[0] if results else None
    
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
        
        if since:
            # Filter date
            assert isinstance(since, str)
            query = query.filter(model_class.updated_at >= since)
        
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
                if hasattr(model_class, 'repo_name'):
                    searchable_fields.append(model_class.repo_name)
                if hasattr(model_class, 'description'):
                    searchable_fields.append(model_class.description)
                if hasattr(model_class, 'readme'):
                    searchable_fields.append(model_class.readme)
                    
                for term in search_terms:
                    term_filters = []
                    for field in searchable_fields:
                        term_filters.append(field.ilike(f'%{term}%'))
                    if term_filters:
                        filters.append(or_(*term_filters))
                
                if filters:
                    results = (query.filter(*filters)
                             .order_by(desc(model_class.updated_at))
                             .offset(start).limit(num).all())
                else:
                    results = []
        else:
            # Return recent repositories if no search keywords
            results = (query.order_by(desc(model_class.updated_at))
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
    
    def _process_repo_data(self, repo_data, embedding_model=None):
        """
        Process repository data and generate embedding if model is provided.
        
        Args:
            repo_data: Dictionary with repository metadata
            embedding_model: Optional model to generate embeddings
            
        Returns:
            tuple: (processed_data, embedding)
        """
        # Process text fields
        repo_name = repo_data.get('repo_name', '').strip()
        description = repo_data.get('description', '').replace("\n", " ").replace("  ", " ")
        readme = repo_data.get('readme', '').replace("\n", " ").replace("  ", " ")
        
        # Generate embedding if model is provided
        embedding = None
        if embedding_model and (repo_name or description or readme):
            try:
                repo_text = f"Repository: {repo_name}\nDescription: {description}\nReadme: {readme}"
                embedding = embedding_model.encode(repo_text).astype(np.float32)
            except Exception as e:
                self.logger.error(f"Failed to generate embedding: {str(e)}")
        
        # Update repo_data with processed fields
        repo_data['repo_name'] = repo_name
        repo_data['description'] = description
        repo_data['readme'] = readme
        
        return repo_data, embedding
    
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