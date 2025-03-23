import os
import sys
import json
import logging
import datetime as DT
from urllib.parse import unquote
from flask import Flask, request, render_template

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from dlmonitor.fetcher import get_posts
from dlmonitor.settings import DEFAULT_MODEL, SESSION_KEY

# 预加载模型
try:
    from sentence_transformers import SentenceTransformer
    global_model = SentenceTransformer(DEFAULT_MODEL)
    logging.info("SentenceTransformer模型已预加载")
except Exception as e:
    logging.warning(f"无法预加载SentenceTransformer模型: {str(e)}")
    global_model = None

app = Flask(__name__, static_url_path='/static')
app.secret_key = SESSION_KEY
app.config['SESSION_TYPE'] = 'filesystem'


# 常量定义      
DEFAULT_KEYWORDS = "arxiv:large language model,nature:machine learning,github:deep learning"
DATE_TOKEN_MAP = {
    '1-week': 7,
    '2-week': 14,
    '1-month': 31
}
VALID_SOURCES = ["arxiv", "nature", "github"]

def get_date_str(token):
    """将时间标记转换为日期字符串，例如'1-week' -> '2023-01-01'"""
    if token not in DATE_TOKEN_MAP:
        logger.warning(f"无效的日期token: {token}，使用默认值 '2-week'")
        token = '2-week'
    
    days = DATE_TOKEN_MAP[token]
    target_date = DT.date.today() - DT.timedelta(days=days)
    result = target_date.strftime("%Y-%m-%d")
    logger.info(f"时间筛选: {token} 转换为 {result} (过去 {days} 天)")
    return result

@app.route('/')
def index():
    # 获取关键词和日期范围
    logger.info("开始处理首页请求...")
    logger.info(f"请求方法: {request.method}, 路径: {request.path}, 远程地址: {request.remote_addr}")
    logger.info(f"请求cookies: {request.cookies}")
    
    keywords = unquote(request.cookies.get('keywords', DEFAULT_KEYWORDS))
    logger.info(f"解析到关键词: {keywords}")
    
    target_date = get_date_str(request.cookies.get('datetoken'))
    
    # 解析排序偏好
    try:
        sort_preferences = json.loads(request.cookies.get('sortPreferences', '{}'))
    except:
        sort_preferences = {}
    
    # 解析关键词
    columns = []
    for kw in keywords.split(","):
        if ":" not in kw:
            continue
            
        src, query = kw.split(":", 1)
        src = src.strip().lower()
        query = query.strip()
        
        # 跳过无效源
        if src not in VALID_SOURCES:
            continue
            
        # 获取排序类型
        sort_type = sort_preferences.get(kw, "time")
        
        # 获取数据
        try:
            logger.info(f"正在获取源数据: {src}, 关键词: {query}")
            posts = get_posts(src, query, target_date, sort_type=sort_type)
            columns.append([src, kw, posts, sort_type])
            logger.info(f"成功获取数据, 结果数量: {len(posts)}")
        except Exception as ex:
            logging.exception(ex)
            columns.append([src, kw, [], sort_type])
    
    logger.info(f"完成首页数据准备, 返回结果列数: {len(columns)}")
    return render_template('index.html', columns=columns)

@app.route('/fetch', methods=['POST'])
def fetch():
    # 获取参数
    kw = unquote(request.form.get('keyword', ''))
    src = request.form.get("src")
    start = request.form.get("start", "0")
    datetoken = request.form.get("datetoken", "2-week")
    sort_type = request.form.get("sort", "time")
    
    # 参数验证
    if not src or not kw or "." in src:
        return "", 400
    if src not in VALID_SOURCES:
        logger.warning(f"Invalid source: {src}")
        return "", 400
        
    # 转换参数
    start = int(start)
    target_date = get_date_str(datetoken)
    logger.info(f"请求数据: 源={src}, 关键词={kw}, 日期范围={datetoken}, 目标日期={target_date}, 排序={sort_type}")
    
    # 提取查询内容
    query = kw.split(":", 1)[1].strip() if ":" in kw else kw
    
    try:
        # 获取数据，直接传递排序类型
        posts = get_posts(src, query, target_date, start, sort_type=sort_type)
        logger.info(f"获取到 {len(posts)} 条结果")
        return render_template("post_list.html", posts=posts)
    except Exception as e:
        logger.error(f"Error fetching data: {str(e)}", exc_info=True)
        return f"Error: {str(e)}", 500


if __name__ == '__main__':
    app.run(debug=True,port=5000)
