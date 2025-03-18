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

class TwitterModel(Base):

    __tablename__ = 'twitter'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tweet_id = Column(String(20), primary_key=True)
    popularity = Column(Integer)
    pic_url = Column(String(255), nullable=True)
    published_time = Column(DateTime())
    user = Column(Unicode(255))
    text = Column(Text())

    # For full text search
    search_vector = Column(TSVectorType('text'))

    def __repr__(self):
        template = '<Twitter(id="{0}", user_name="{1}")>'
        return template.format(self.id, self.user)

class WorkingQueueModel(Base):

    __tablename__ = "working"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(255), nullable=True)
    param = Column(String(255), nullable=True)

    def __repr__(self):
        return __tablename__ + self.id
