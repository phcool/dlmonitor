"""
A class for fetching all sources.
"""

from .sources.arxivsrc import ArxivSource
from .sources.naturesrc import NatureSource
from .sources.gitsrc import GitSource
from .db import Base, engine
from dlmonitor.settings import DEFAULT_MODEL,NUMBER_EACH_PAGE
import logging

NUMBER_EACH_PAGE = 100
# 获取当前模块的logger
logger = logging.getLogger(__name__)

# 声明全局变量
global_model = None

def get_source(src):
    """获取数据源实例"""
    if src == "arxiv":
        from dlmonitor.sources.arxivsrc import ArxivSource
        return ArxivSource()
    elif src == "nature":
        from dlmonitor.sources.naturesrc import NatureSource
        return NatureSource()
    elif src == "github":
        from dlmonitor.sources.gitsrc import GitSource
        return GitSource()
    return None

def get_posts(src, keywords, since=None, start=0, num=NUMBER_EACH_PAGE, sort_type="time"):
    """获取指定源的数据，处理不同源的特殊需求"""
    # 设置默认日期
    if since is None:
        import datetime as DT
        today = DT.date.today()
        two_weeks_ago = today - DT.timedelta(days=14)
        since = two_weeks_ago.strftime("%Y-%m-%d")
    
    logger.info(f"从 {src} 获取数据: 关键词={keywords}, 过滤日期>={since}, 排序方式={sort_type}")
    
    try:
        # 根据不同的源使用不同的获取方法
        global global_model
        if not global_model:
            from sentence_transformers import SentenceTransformer
            global_model=SentenceTransformer(DEFAULT_MODEL)

        posts = get_source(src).get_posts(
            keywords=keywords, 
            since=since, 
                start=start, 
                num=num, 
                model=global_model,
                sort_type=sort_type  # 传递排序类型参数
            )
        
        logger.info(f"{src} 返回 {len(posts)} 条结果")
        # 直接返回已排序的结果
        return posts
    except Exception as e:
        logger.error(f"Error fetching data from {src}: {str(e)}", exc_info=True)
        raise

def fetch_sources(src, model=None, max_papers=None, fetch_all=False):
    """执行获取新论文的操作"""
    logger.info(f"开始获取 {src} 的新内容...")
    
    # 预加载模型，用于需要向量搜索的源
    global global_model
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(DEFAULT_MODEL)

    if src not in ['arxiv', 'nature', 'github', 'all']:
        raise ValueError(f"Invalid source: {src}")
    

    
    