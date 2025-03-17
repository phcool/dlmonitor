import sys
import os
import time
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# 添加项目根目录到 Python 路径
sys.path.append(".")
from dlmonitor.db import session_scope, ArxivModel

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_embeddings():
    """为所有论文生成向量表示并存储到数据库中"""
    
    # 加载模型
    logger.info("Loading sentence transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')  # 使用较小的模型以提高性能
    
    batch_size = 32  # 批处理大小，可以根据内存情况调整
    
    with session_scope() as session:
        # 获取所有没有向量表示的论文
        papers = session.query(ArxivModel).filter(ArxivModel.embedding == None).all()
        total_papers = len(papers)
        
        if total_papers == 0:
            logger.info("No papers found without embeddings. All papers already have embeddings.")
            return
        
        logger.info(f"Found {total_papers} papers without embeddings. Generating embeddings...")
        
        # 分批处理
        for i in tqdm(range(0, total_papers, batch_size)):
            batch = papers[i:i+batch_size]
            
            # 为每篇论文准备文本
            texts = []
            for paper in batch:
                # 合并标题、作者和摘要作为嵌入的输入
                text = f"Title: {paper.title}\nAuthors: {paper.authors}\nAbstract: {paper.abstract}"
                texts.append(text)
            
            # 生成嵌入
            embeddings = model.encode(texts)
            
            # 更新数据库
            for j, paper in enumerate(batch):
                paper.embedding = embeddings[j].astype(np.float32)  # 转换为 float32 以兼容 pgvector
            
            # 提交这一批次的更改
            session.commit()
            
            # 休息一下，避免内存问题
            if i % (batch_size * 10) == 0 and i > 0:
                logger.info(f"Processed {i}/{total_papers} papers. Taking a short break...")
                time.sleep(1)
        
        logger.info(f"Successfully generated embeddings for {total_papers} papers.")

if __name__ == "__main__":
    generate_embeddings() 