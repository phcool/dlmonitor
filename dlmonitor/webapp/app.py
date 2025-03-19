import os
import sys
import json

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from flask import Flask, request, redirect, session, send_from_directory
from flask import render_template, send_from_directory
from dlmonitor.db import close_global_session, get_global_session
from dlmonitor.fetcher import get_posts
from dlmonitor import settings
from urllib.parse import unquote
import datetime as DT
import logging

# 预加载模型
try:
    from sentence_transformers import SentenceTransformer
    global_model = SentenceTransformer('all-MiniLM-L6-v2')
    logging.info("SentenceTransformer模型已预加载")
except Exception as e:
    logging.warning(f"无法预加载SentenceTransformer模型: {str(e)}")
    global_model = None

app = Flask(__name__, static_url_path='/static')
app.secret_key = settings.SESSION_KEY
app.config['SESSION_TYPE'] = 'filesystem'

NUMBER_EACH_PAGE = 100
DEFAULT_KEYWORDS = "arxiv:large language model,nature:machine learning"
DATE_TOKEN_SET = set(['1-week', '2-week', '1-month'])

def get_date_str(token):
    """
    Convert token to date string.
    For example, '1-week' ---> '2017-04-03'.
    """
    today = DT.date.today()
    if token not in DATE_TOKEN_SET:
        token = '2-week'
    if token == '1-week':
        target_date = today - DT.timedelta(days=7)
    elif token == '2-week':
        target_date = today - DT.timedelta(days=14)
    else:
        target_date = today - DT.timedelta(days=31)
    return target_date.strftime("%Y-%m-%d")

@app.route('/')
def index():
    keywords = request.cookies.get('keywords')
    if not keywords:
        keywords = DEFAULT_KEYWORDS
    else:
        keywords = unquote(keywords)
    target_date = get_date_str(request.cookies.get('datetoken'))
    
    # 解析关键词
    kws = []
    for kw in keywords.split(","):
        if ":" in kw:
            # 新格式：platform:query
            parts = kw.split(":", 1)
            src = parts[0].strip()
            query = parts[1].strip()
            kws.append((src, query))
    
    # 获取排序偏好
    sort_preferences = request.cookies.get('sortPreferences', '{}')
    try:
        sort_preferences = json.loads(sort_preferences)
    except:
        sort_preferences = {}
    
    columns = []
    context = {'columns': columns}

    for i, (src, kw) in enumerate(kws):
        # 在try外定义默认排序类型
        sort_type = sort_preferences.get(f"{src}:{kw}", "time")
        try:
            posts = fetch_source_data(src.lower(), kw, sort_type=sort_type)
            add_column(columns, src, kw, posts, sort_type)
        except Exception as ex:
            logging.exception(ex)
            add_empty_column(columns, src, kw, sort_type=sort_type)

    return render_template('index.html', **context)

@app.route('/fetch', methods=['POST'])
def fetch():
    # Get keywords
    kw = request.form.get('keyword')
    if kw is not None:
        kw = unquote(kw)
    # Get parameters
    src = request.form.get("src")
    start = request.form.get("start")
    datetoken = request.form.get("datetoken", "2-week")  # Get date range from request
    sort_type = request.form.get("sort", "time")  # 获取排序类型，默认按时间
    
    if src is None or start is None:
        # Error if 'src' or 'start' parameter is not found
        return ""
    assert "." not in src  # Just for security
    start = int(start)
    
    # Get target date string
    target_date = get_date_str(datetoken)
    # 提取实际查询内容
    if ":" in kw:
        # 新格式：platform:query
        parts = kw.split(":", 1)
        query = parts[1].strip()
    else:
        query = kw
    
    try:
        # 获取数据
        posts = fetch_source_data(src, query, target_date, start, NUMBER_EACH_PAGE, sort_type)
        
        # 使用统一的模板
        return render_template("post_list.html", posts=posts)
    except Exception as e:
        app.logger.error(f"Error fetching data: {str(e)}")
        return f"Error: {str(e)}", 500

def fetch_source_data(src, keywords, since=None, start=0, num=NUMBER_EACH_PAGE, sort_type="time"):
    """获取指定源的数据，处理不同源的特殊需求"""
    # 检查源平台是否有效
    valid_sources = ["arxiv", "twitter", "nature", "github"]
    if src not in valid_sources:
        app.logger.warning(f"Invalid source: {src}")
        return []
    
    # 设置默认日期如果没有提供
    if since is None:
        since = get_date_str("2-week")
    
    try:
        # 对于需要向量搜索的源，使用预加载的模型
        if src in ["arxiv", "nature", "github"] and global_model:
            if src == "arxiv":
                from dlmonitor.sources.arxivsrc import ArxivSource
                source_instance = ArxivSource()
            elif src == "nature":
                from dlmonitor.sources.naturesrc import NatureSource
                source_instance = NatureSource()
            elif src == "github":
                from dlmonitor.sources.gitsrc import GitSource
                source_instance = GitSource()
                
            posts = source_instance.get_posts(keywords=keywords, since=since, start=start, num=num, model=global_model)
            
            # 根据排序参数处理结果
            if sort_type == "time":
                # 按时间排序
                if posts and hasattr(posts[0], 'published_time'):
                    posts = sorted(posts, key=lambda x: x.published_time, reverse=True)
                elif posts and hasattr(posts[0], 'updated_at'):
                    posts = sorted(posts, key=lambda x: x.updated_at, reverse=True)
            elif sort_type == "popularity":
                # 按热度排序 - 使用不同字段处理不同源
                if src == "github" and posts:
                    # GitHub 使用 stars 作为热度指标
                    posts = sorted(posts, key=lambda x: x.stars, reverse=True)
                elif posts and hasattr(posts[0], 'popularity'):
                    # 其他源使用 popularity 字段
                    posts = sorted(posts, key=lambda x: x.popularity or 0, reverse=True)
            # 对于 "relevance"，我们使用 API 返回的原始排序，不做处理
        else:
            # 对于其他源或模型未加载的情况，使用常规的get_posts函数
            from dlmonitor.fetcher import get_posts as fetcher_get_posts
            posts = fetcher_get_posts(src, keywords=keywords, since=since, start=start, num=num)
            
            # 尝试排序
            if sort_type == "time":
                if posts and hasattr(posts[0], 'published_time'):
                    posts = sorted(posts, key=lambda x: x.published_time, reverse=True)
                elif posts and hasattr(posts[0], 'updated_at'):
                    posts = sorted(posts, key=lambda x: x.updated_at, reverse=True)
            elif sort_type == "popularity" and posts:
                if src == "github":
                    posts = sorted(posts, key=lambda x: x.stars, reverse=True)
                elif posts and hasattr(posts[0], 'popularity'):
                    posts = sorted(posts, key=lambda x: x.popularity or 0, reverse=True)
        
        return posts
    except Exception as e:
        app.logger.error(f"Error fetching data from {src}: {str(e)}")
        raise

def add_column(columns, src, kw, posts, sort_type="time"):
    if type(posts) == tuple:
        posts = list(posts)
    columns.append([src, kw, posts, sort_type])

def add_empty_column(columns, src, kw, sort_type="time"):
    columns.append([src, kw, [], sort_type])

if __name__ == '__main__':
    app.run(debug=True)
