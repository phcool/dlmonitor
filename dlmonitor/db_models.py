import sys
import numpy as np
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Unicode, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_searchable import make_searchable
from sqlalchemy_utils.types import TSVectorType
from pgvector.sqlalchemy import Vector

if 'Base' not in globals():
    Base = declarative_base()
    make_searchable(Base.metadata)

class ArxivModel(Base):

    __tablename__ = 'arxiv'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer)
    popularity = Column(Integer)
    title = Column(Unicode(800, collation=''))
    arxiv_url = Column(String(255), primary_key=True)
    pdf_url = Column(String(255))
    published_time = Column(DateTime())
    authors = Column(Unicode(800, collation=''))
    abstract = Column(Text(collation=''))
    journal_link = Column(Text(collation=''), nullable=True)
    tag = Column(String(255))
    introduction = Column(Text(collation=''))
    conclusion = Column(Text(collation=''))
    analyzed = Column(Boolean, server_default='false', default=False)
    
    # 向量表示，使用 pgvector 扩展
    embedding = Column(Vector(384), nullable=True)  # 使用 sentence-transformers 的默认维度 (384)

    # For full text search
    search_vector = Column(
        TSVectorType('title', 'abstract', 'authors', weights={'title': 'A', 'abstract': 'B', 'authors': 'C'}))

    def __repr__(self):
        template = '<Arxiv(id="{0}", url="{1}")>'
        return template.format(self.id, self.arxiv_url)

class NatureModel(Base):

    __tablename__ = 'nature'

    id = Column(Integer, primary_key=True, autoincrement=True)
    popularity = Column(Integer)
    title = Column(Unicode(800, collation=''))
    article_url = Column(String(255), primary_key=True)
    pdf_url = Column(String(255), nullable=True)
    published_time = Column(DateTime())
    authors = Column(Unicode(800, collation=''))
    abstract = Column(Text(collation=''))
    journal = Column(String(255))
    doi = Column(String(255), nullable=True)
    
    # 向量表示，使用 pgvector 扩展
    embedding = Column(Vector(384), nullable=True)  # 使用 sentence-transformers 的默认维度 (384)

    # For full text search
    search_vector = Column(
        TSVectorType('title', 'abstract', 'authors', weights={'title': 'A', 'abstract': 'B', 'authors': 'C'}))

    def __repr__(self):
        template = '<Nature(id="{0}", url="{1}")>'
        return template.format(self.id, self.article_url)

class GitHubModel(Base):

    __tablename__ = 'github'

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String(255), primary_key=True)  # GitHub API 返回的仓库 ID
    repo_name = Column(String(255))  # 仓库名称
    full_name = Column(String(255))  # 完整仓库名称 (owner/repo)
    description = Column(Text(collation=''))
    html_url = Column(String(255))  # GitHub 仓库页面 URL
    clone_url = Column(String(255))  # Git 克隆 URL
    stars = Column(Integer)  # 星标数
    forks = Column(Integer)  # 分支数
    language = Column(String(50))  # 主要编程语言
    topics = Column(Text(collation=''))  # 仓库主题标签
    readme = Column(Text(collation=''))  # README 内容
    updated_at = Column(DateTime())  # 最后更新时间
    created_at = Column(DateTime())  # 创建时间
    
    # 向量表示，使用 pgvector 扩展
    embedding = Column(Vector(384), nullable=True)  # 使用 sentence-transformers 的默认维度 (384)

    # For full text search
    search_vector = Column(
        TSVectorType('repo_name', 'description', 'readme', 'topics', 
                    weights={'repo_name': 'A', 'description': 'B', 'readme': 'C', 'topics': 'D'}))

    def __repr__(self):
        template = '<GitHub(id="{0}", name="{1}")>'
        return template.format(self.id, self.full_name)
