import os
import sys

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

NUMBER_EACH_PAGE = 30
DEFAULT_KEYWORDS = "arxiv:reinforcement learning,twitter:machine learning,arxiv:language,twitter:AI news"
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
    column_list = []
    
    for kw in keywords.split(","):
        if ":" in kw:
            # 新格式：platform:query
            parts = kw.split(":", 1)
            src = parts[0].strip().lower()
            query = parts[1].strip()
        else:
            # 兼容旧格式
            if "tweets" in kw.lower():
                src = "twitter"
                query = kw
            else:
                src = "arxiv"
                query = kw

        # 检查源平台是否有效
        valid_sources = ["arxiv", "twitter", "nature"]
        if src not in valid_sources:
            continue
            
        num_page = 80 if src == "twitter" else NUMBER_EACH_PAGE
        
        # 对于需要向量搜索的源，使用预加载的模型
        if src in ["arxiv", "nature"] and global_model and query not in ["Hot Papers", "Fresh Papers"]:
            if src == "arxiv":
                from dlmonitor.sources.arxivsrc import ArxivSource
                source_instance = ArxivSource()
            elif src == "nature":
                from dlmonitor.sources.naturesrc import NatureSource
                source_instance = NatureSource()
                
            posts = source_instance.get_posts(keywords=query, since=target_date, start=0, num=num_page, model=global_model)
        else:
            # 对于其他源或模型未加载的情况，使用常规的get_posts函数
            posts = get_posts(src, keywords=query, since=target_date, start=0, num=num_page)
            
        column_list.append((src, kw, posts))

    return render_template("index.html", columns=column_list)

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
    
    if src is None or start is None:
        # Error if 'src' or 'start' parameter is not found
        return ""
    assert "." not in src  # Just for security
    start = int(start)
    
    # Get target date string
    target_date = get_date_str(datetoken)

    num_page = 80 if src == "twitter" else NUMBER_EACH_PAGE

    # 提取实际查询内容
    if ":" in kw:
        # 新格式：platform:query
        parts = kw.split(":", 1)
        query = parts[1].strip()
    else:
        query = kw
    
    # 对于需要向量搜索的源，使用预加载的模型
    if src in ["arxiv", "nature"] and global_model and query not in ["Hot Papers", "Fresh Papers"]:
        if src == "arxiv":
            from dlmonitor.sources.arxivsrc import ArxivSource
            source_instance = ArxivSource()
        elif src == "nature":
            from dlmonitor.sources.naturesrc import NatureSource
            source_instance = NatureSource()
            
        posts = source_instance.get_posts(keywords=query, since=target_date, start=start, num=num_page, model=global_model)
    else:
        # 对于其他源或模型未加载的情况，使用常规的get_posts函数
        posts = get_posts(src, keywords=query, since=target_date, start=start, num=num_page)

    return render_template("post_{}.html".format(src), posts=posts)

@app.route("/arxiv/<int:arxiv_id>/<paper_str>")
def arxiv(arxiv_id, paper_str):
    from dlmonitor.sources.arxivsrc import ArxivSource
    from dlmonitor.latex import retrieve_paper_html
    post = ArxivSource().get_one_post(arxiv_id)
    arxiv_token = post.arxiv_url.split("/")[-1]

    # Check the HTML page
    html_body = retrieve_paper_html(arxiv_token)
    return render_template("single.html",
        post=post, arxiv_token=arxiv_token, html_body=html_body)

@app.route("/nature/<int:nature_id>/<paper_str>")
def nature(nature_id, paper_str):
    from dlmonitor.sources.naturesrc import NatureSource
    post = NatureSource().get_one_post(nature_id)
    return render_template("single.html",
        post=post, html_body="<p>Nature article full text is not available.</p>")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/search")
def search():
    return render_template("search.html")

@app.route("/load_fulltext/<arxiv_token>")
def load_fulltext(arxiv_token):
    from dlmonitor.db_models import WorkingQueueModel
    db_session = get_global_session()
    job = WorkingQueueModel(
        type="load_arxiv",
        param=arxiv_token
    )
    db_session.add(job)
    db_session.commit()
    return "OK"

@app.route("/retrieve_fulltext/<arxiv_token>")
def retrieve_fulltext(arxiv_token):
    from dlmonitor.db_models import WorkingQueueModel
    db_session = get_global_session()
    job = db_session.query(WorkingQueueModel).filter_by(
        type="load_arxiv",
        param=arxiv_token
    ).first()
    if job and job.status == "done":
        return job.result
    return ""

if __name__ == '__main__':
    app.run(debug=True)
