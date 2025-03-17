import os
from flask import Flask, request, redirect, session, send_from_directory
from flask import render_template, send_from_directory
from dlmonitor.db import close_global_session, get_global_session
from dlmonitor.fetcher import get_posts
from dlmonitor import settings
from urllib.parse import unquote
import datetime as DT
import logging

from mendeley import Mendeley
from mendeley.session import MendeleySession
import oauthlib

# 预加载模型
try:
    from sentence_transformers import SentenceTransformer
    global_model = SentenceTransformer('all-MiniLM-L6-v2')
    logging.info("SentenceTransformer model preloaded successfully")
except Exception as e:
    logging.warning(f"Could not preload SentenceTransformer model: {str(e)}")
    global_model = None

app = Flask(__name__, static_url_path='/static')
app.secret_key = settings.SESSION_KEY
app.config['SESSION_TYPE'] = 'filesystem'


NUMBER_EACH_PAGE = 30
DEFAULT_KEYWORDS = "arxiv:reinforcement learning,twitter:machine learning,arxiv:language,twitter:AI news"
DATE_TOKEN_SET = set(['1-week', '2-week', '1-month'])

# Mendeley
MENDELEY_REDIRECT = "{}/oauth".format(settings.HOME_URL)
mendeley = Mendeley(settings.MENDELEY_CLIENTID, settings.MENDELEY_SECRET, MENDELEY_REDIRECT)

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
        valid_sources = ["arxiv", "twitter"]
        if src not in valid_sources:
            continue
            
        num_page = 80 if src == "twitter" else NUMBER_EACH_PAGE
        
        # 对于Arxiv搜索，使用预加载的模型
        if src == "arxiv" and global_model and query not in ["Hot Papers", "Fresh Papers"]:
            # 从sources/arxivsrc.py中直接获取ArxivSource实例并调用get_posts
            from dlmonitor.sources.arxivsrc import ArxivSource
            arxiv_src = ArxivSource()
            posts = arxiv_src.get_posts(keywords=query, since=target_date, start=0, num=num_page, model=global_model)
        else:
            # 对于其他源或模型未加载的情况，使用常规的get_posts函数
            posts = get_posts(src, keywords=query, since=target_date, start=0, num=num_page)
            
        column_list.append((src, kw, posts))

    # Mendeley
    auth = mendeley.start_authorization_code_flow()
    if "ma_token" in session and session["ma_token"] is not None:
        ma_session = MendeleySession(mendeley, session['ma_token'])
        try:
            ma_firstname = ma_session.profiles.me.first_name
        except:
            session['ma_token'] = None
            ma_session =None
            ma_firstname = None
    else:
        ma_session = None
        ma_firstname = None

    ma_authorized = ma_session is not None and ma_session.authorized
    return render_template(
        "index.html", columns=column_list, mendeley_login=auth.get_login_url(),
        ma_session=ma_session, ma_authorized=ma_authorized, ma_firstname=ma_firstname
    )

@app.route('/fetch', methods=['POST'])
def fetch():
    # Get keywords
    kw = request.form.get('keyword')
    if kw is not None:
        kw = unquote(kw)
    # Get parameters
    src = request.form.get("src")
    start = request.form.get("start")
    if src is None or start is None:
        # Error if 'src' or 'start' parameter is not found
        return ""
    assert "." not in src  # Just for security
    start = int(start)
    # Get target date string
    target_date = get_date_str(request.cookies.get('datetoken'))

    num_page = 80 if src == "twitter" else NUMBER_EACH_PAGE

    # 提取实际查询内容
    if ":" in kw:
        # 新格式：platform:query
        parts = kw.split(":", 1)
        query = parts[1].strip()
    else:
        query = kw
    
    # 对于Arxiv搜索，使用预加载的模型
    if src == "arxiv" and global_model and query not in ["Hot Papers", "Fresh Papers"]:
        # 从sources/arxivsrc.py中直接获取ArxivSource实例并调用get_posts
        from dlmonitor.sources.arxivsrc import ArxivSource
        arxiv_src = ArxivSource()
        posts = arxiv_src.get_posts(keywords=query, since=target_date, start=start, num=num_page, model=global_model)
    else:
        # 对于其他源或模型未加载的情况，使用常规的get_posts函数
        posts = get_posts(src, keywords=query, since=target_date, start=start, num=num_page)

    # Mendeley
    ma_authorized = "ma_token" in session and session["ma_token"] is not None

    return render_template(
        "post_{}.html".format(src),
        posts=posts,
        ma_authorized=ma_authorized)

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

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/search")
def search():
    return render_template("search.html")

@app.route('/oauth')
def auth_return():
    auth = mendeley.start_authorization_code_flow(state=request.args.get("state"))
    mendeley_session = auth.authenticate(request.url)

    session["ma_token"] = mendeley_session.token
    session["ma_state"] = request.args.get("state")

    return redirect('/')

@app.route("/save_mendeley")
def save_mendeley():
    import urllib
    if "ma_token" in session and session["ma_token"] is not None:
        ma_session = MendeleySession(mendeley, session['ma_token'])
    else:
        ma_session = None

    ma_authorized = ma_session is not None and ma_session.authorized
    if not ma_authorized:
        return "Please log in into Mendeley."

    pdf_url = request.args.get('url')
    # Retrieve pdf file
    arxiv_id = pdf_url.split("/")[-1].replace(".pdf", "")
    local_pdf = "{}/{}.pdf".format(settings.PDF_PATH, arxiv_id)
    remote_pdf = "http://arxiv.org/pdf/{}.pdf".format(arxiv_id)
    if not os.path.exists(local_pdf):
        urllib.urlretrieve(remote_pdf, local_pdf)

    # Create file
    ma_session.documents.create_from_file(local_pdf)

    return "{} is saved into Mendeley".format(os.path.basename(local_pdf))

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
    from dlmonitor.latex import retrieve_paper_html
    return retrieve_paper_html(arxiv_token)

@app.route("/arxiv_files/<arxiv_token>/<path:fp>")
def arxiv_files(arxiv_token, fp):
    fp = "{}/{}/{}".format(settings.SOURCE_PATH, arxiv_token, fp)
    if os.path.exists(fp):
        return send_from_directory(os.path.dirname(fp), os.path.basename(fp))
    else:
        return ""

@app.route("/logout")
def logout():
    session["ma_token"] = None
    return redirect("/")

if __name__ == '__main__':
    # app.run(host='0.0.0.0', debug=True, ssl_context='adhoc')
    app.run(host='0.0.0.0', debug=True)
