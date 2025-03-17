# DLMonitor: Monitoring all things happening in deep learning

### Purpose

This project aims to save time and energy for deep learning folks.
It monitors new things on multiple sources and find out those important to you.
Currently, the data sources include:

- Arxiv papers
- Tweets
- Reddit posts

Take a look at the public server: https://deeplearn.org

### Install

1. Install postgres server
2. `pip install -r requirements.txt`
3. `sudo apt-get install poppler-utils`

### Setup database

1. Create a `.env` file in the project root.

```
DATABASE_USER=dlmonitor
DATABASE_PASSWD=something

TWITTER_CONSUMER_KEY=something
TWITTER_CONSUMER_SECRET=something
TWITTER_ACCESS_TOKEN=something
TWITTER_ACCESS_SECRET=something

SUPERVISORD_PASSWD=something
```

2. Create database

Run `bash bin/create_db.sh`


### Install Quick Read dependencies

1. install cpan
2. install text::Unidecode in cpan
3. git clone https://github.com/brucemiller/LaTeXML
4. perl Makefile.PL; make; make install

### Fetch resources

Fetch Arxiv papers and tweets.

```bash
python bin/fetch_new_sources.py all
```

### Run test server

```bash
PYTHONPATH="." python dlmonitor/webapp/app.py
```

### Setup production server

1. Install nginx

2. Copy configuration files for supervisord and nignx

```bash
bash bin/config_server.sh
```

3. Start Gunicorn processes through supervisord

```bash
bash bin/start_supervisord.sh
```
4. Start arxiv source loading worker

```bash
PYTHONPATH="." python bin/auto_load_arxiv.py --forever
```

# DL Monitor 项目升级：向量搜索功能

本项目已升级为使用基于向量的搜索，提供更精确的论文搜索结果。

## 主要更新

1. **向量表示**：使用 sentence-transformers 为论文生成向量表示
2. **PostgreSQL pgvector 扩展**：使用 pgvector 扩展在数据库中存储和查询向量
3. **混合搜索策略**：结合向量相似度和传统文本搜索，提供更好的搜索结果
4. **自动向量生成**：在获取新论文时自动生成向量表示

## 设置步骤

1. **安装依赖**:
   ```bash
   pip install sentence-transformers faiss-cpu pgvector psycopg2-binary scikit-learn
   ```

2. **在 PostgreSQL 中添加 pgvector 扩展**:
   使用 `reset_database.py` 脚本一键完成，或手动执行:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

3. **重置数据库**:
   ```bash
   python reset_database.py
   ```
   这将删除旧数据库并创建一个新的，包含向量列。

4. **重新获取论文**:
   ```bash
   python bin/fetch_new_sources.py arxiv
   ```
   这将获取论文并自动生成向量表示。

5. **为现有论文生成向量**（如果你跳过了重置数据库）:
   ```bash
   python generate_embeddings.py
   ```

## 使用方法

无需更改任何现有代码即可使用新的搜索功能。系统将自动检测是否存在向量数据，并选择适当的搜索方法：

- 如果存在向量数据，将使用向量相似度搜索
- 如果向量搜索结果不足，将自动补充使用传统文本搜索
- 如果没有向量数据，将回退到传统文本搜索

## 技术细节

- 使用了 "all-MiniLM-L6-v2" 模型，维度为 384，提供了良好的性能和质量平衡
- 向量搜索使用余弦相似度来衡量文档相关性
- 为提高效率，批量处理论文和向量生成
- 自动处理 arXiv API 的错误和限制

## 性能提示

- 第一次生成向量可能需要一些时间，特别是对于大型数据库
- 向量搜索通常比传统文本搜索更快，特别是对于大型数据库
