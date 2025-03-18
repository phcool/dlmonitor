"""
Base class of all sources.
"""

from abc import ABCMeta, abstractmethod
import logging
from datetime import datetime

class Source(object):
    """Base class for all data sources"""
    
    __metaclass__ = ABCMeta
    
    # Common source types
    SOURCE_TYPE_PAPER = "paper"
    SOURCE_TYPE_SOCIAL = "social"
    SOURCE_TYPE_CODE = "code"
    
    def __init__(self):
        self.source_type = None
        self.source_name = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_posts(self, keywords=None, since=None, start=0, num=100, model=None):
        """
        Get recent posts.
        
        Args:
            keywords (str): Keywords to search for
            since (str): Date string to filter content
            start (int): Start index for pagination
            num (int): Number of posts to return
            model: Optional pre-loaded model for embeddings
            
        Returns:
            list: List of post objects
        """
        return []
    
    def get_one_post(self, post_id):
        """
        Get a single post by ID.
        
        Args:
            post_id: ID of the post to retrieve
            
        Returns:
            object: Post object if found, None otherwise
        """
        return None
    
    @abstractmethod
    def fetch_new(self, model=None):
        """
        Fetch new resources from the source.
        
        Args:
            model: Optional pre-loaded model for embeddings
            
        Returns:
            bool: True if new content was found, False otherwise
        """
        pass
    
    def fetch_all(self):
        """
        Fetch all resources from the source.
        
        Returns:
            bool: True if operation was successful, False otherwise
        """
        return False
    
    def _current_time(self):
        """Get current timestamp string"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _check_source_available(self):
        """Check if the source is available"""
        return True

