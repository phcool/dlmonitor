"""
A class for fetching all sources.
"""

from .sources.arxivsrc import ArxivSource
from .sources.twittersrc import TwitterSource
from .sources.naturesrc import NatureSource
from .sources.gitsrc import GitSource
from .db import Base, engine
import logging

# 获取当前模块的logger
logger = logging.getLogger(__name__)

def get_source(src_name):
    if src_name == 'arxiv':
        return ArxivSource()
    elif src_name == 'twitter':
        return TwitterSource()
    elif src_name == 'nature':
        return NatureSource()
    elif src_name == 'github':
        return GitSource()
    else:
        raise NotImplementedError(f"Unsupported source: {src_name}")

def fetch_sources(src_name, fetch_all=False, model=None, max_papers=None):
    global Base, engine
    Base.metadata.create_all(engine)
    src = get_source(src_name)
    
    # 设置自定义参数（如果提供）
    if max_papers is not None:
        src.MAX_PAPERS_PER_SOURCE = max_papers
    
    if fetch_all:
        if hasattr(src, 'fetch_all'):
            logger.info(f"为 {src_name} 执行大量数据获取...")
            return src.fetch_all(model=model if src_name in ['arxiv', 'nature', 'github'] else None)
        else:
            logger.warning(f"{src_name} 不支持fetch_all操作，使用正常fetch_new代替")
            if src_name in ['arxiv', 'nature', 'github'] and model is not None:
                return src.fetch_new(model=model)
            else:
                return src.fetch_new()
    else:
        if src_name in ['arxiv', 'nature', 'github'] and model is not None:
            return src.fetch_new(model=model)
        else:
            return src.fetch_new()

def get_posts(src_name, keywords=None, since=None, start=0, num=100):
    src = get_source(src_name)
    return src.get_posts(keywords=keywords, since=since, start=start, num=num)
