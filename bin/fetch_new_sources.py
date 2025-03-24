import sys
import time
import logging
from argparse import ArgumentParser
from sentence_transformers import SentenceTransformer
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
from dlmonitor.fetcher import fetch_sources
from dlmonitor.settings import DEFAULT_MODEL
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量存储预加载的模型
_model = None

def get_model():
    """获取或加载 SentenceTransformer 模型，避免重复加载"""
    global _model
    if _model is None:
        logger.info("首次加载 SentenceTransformer 模型...")
        _model = SentenceTransformer(DEFAULT_MODEL)
    return _model

def run_fetch(src_name, max_papers=None, fetch_all=False):
    """执行获取新论文的操作"""
    logger.info(f"开始获取 {src_name} 的新内容...")
    
    # 预加载模型，用于需要向量搜索的源
    if src_name not in ['arxiv', 'nature', 'github','all']:
        raise ValueError(f"Invalid source: {src_name}")
    
    model = get_model()
        
    # 执行获取操作
    if src_name == "all":
        # 获取所有来源
        fetch_sources("arxiv", model=model, max_papers=max_papers, fetch_all=fetch_all)
        fetch_sources("nature", model=model, max_papers=max_papers, fetch_all=fetch_all)
        fetch_sources("github", model=model, max_papers=max_papers, fetch_all=fetch_all)
    else:
        fetch_sources(src_name, model=model, max_papers=max_papers, fetch_all=fetch_all)
    
    logger.info(f"{src_name} 的新内容获取完成")

if __name__ == '__main__':
    ap = ArgumentParser(description="获取新的论文、代码仓库和推文")
    ap.add_argument("--src", help="来源名称: arxiv, nature, github,  all")
    ap.add_argument("--forever", action="store_true", help="持续运行，每10分钟执行一次")
    ap.add_argument("--interval", type=int, default=600, help="循环执行的间隔时间（秒），默认600秒（10分钟）")
    ap.add_argument("--max_papers", type=int, help="每个来源最多获取的内容总数")
    ap.add_argument("--fetch_all", action="store_true", help="获取大量历史内容填充数据库")
    args = ap.parse_args()

    if args.forever:
        logger.info(f"启动持续运行模式，每 {args.interval} 秒执行一次...")
        try:
            while True:
                start_time = time.time()
                run_fetch(args.src, max_papers=args.max_papers, fetch_all=args.fetch_all)
                
                # 计算需要等待的时间
                elapsed = time.time() - start_time
                wait_time = max(1, args.interval - elapsed)  # 至少等待1秒
                
                logger.info(f"执行完成，等待 {wait_time:.1f} 秒后再次执行...")
                time.sleep(wait_time)
        except KeyboardInterrupt:
            logger.info("收到中断信号，程序退出")
    else:
        # 单次执行
        run_fetch(args.src, max_papers=args.max_papers, fetch_all=args.fetch_all)
