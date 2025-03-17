import urllib.request
import os
import shlex
from subprocess import Popen, PIPE
from threading import Timer

from dlmonitor import settings

def execute_with_timeout(cmd):
    proc = Popen(shlex.split(cmd))
    timer = Timer(5 * 60, proc.kill)
    try:
        timer.start()
        proc.communicate()
    finally:
        timer.cancel()

def build_paper_html(arxiv_id):
    src_path = "{}/{}".format(settings.SOURCE_PATH, arxiv_id)
    html_path = "{}/main.html".format(src_path)
    if os.path.exists(src_path):
        return html_path if os.path.exists(html_path) else None
    opener = urllib.request.build_opener()
    opener.addheaders = [('Referer', 'https://arxiv.org/format/{}'.format(arxiv_id)), ('User-Agent', 'Mozilla/5.0')]
    page = opener.open("https://arxiv.org/e-print/{}".format(arxiv_id))
    meta = page.info()
    file_size = meta.get("Content-Length")
    if file_size and (int(file_size) / 1024. / 1024. > 15):
        # File too big
        os.mkdir(src_path)
        return None
    print("download {}: {}".format(arxiv_id, file_size))
    data = page.read()
    os.mkdir(src_path)
    tgz_path = "{}/source.tgz".format(src_path)
    open(tgz_path, "wb").write(data)
    os.chdir(src_path)
    os.system("tar xzf {} --directory {}".format(tgz_path, src_path))
    texfiles = [fn for fn in os.listdir(src_path) if fn.endswith(".tex")]
    if texfiles:
        select_texfile = texfiles[0]
        if len(texfiles) > 1:
            for fn in texfiles:
                text = open("{}/{}".format(src_path, fn)).read()
                if "begin{document}" in text:
                    select_texfile = fn
                    break
        cmd = "latexml --includestyles --dest=main.xml {}".format(select_texfile.replace(".tex", ""))
        execute_with_timeout(cmd)
        execute_with_timeout("latexmlpost --dest=main.html main.xml")
        execute_with_timeout("latexmlpost --dest=main.html main.xml")
    os.remove(tgz_path)
    open("{}/.loaded".format(src_path), "w").write("loaded")
    return html_path if os.path.exists(html_path) else None

def retrieve_paper_html(arxiv_token):
    src_path = "{}/{}".format(settings.SOURCE_PATH, arxiv_token)
    html_path = "{}/main.html".format(src_path)
    if os.path.exists(src_path) and not os.path.exists("{}/.loaded".format(src_path)):
        html_body = "PROCESSING"
    elif os.path.exists(src_path) and not os.path.exists(html_path):
        html_body = "NOT_AVAILABE"
    elif os.path.exists(src_path) and os.path.exists(html_path):
        html_body = open(html_path, 'r', encoding='utf-8').read()
        html_body = html_body.split("<body>")[-1]
        html_body = html_body.split("</body>")[0]
        html_body = html_body.replace('<img src="', '<img src="/arxiv_files/{}/'.format(arxiv_token))
        html_body = html_body.replace("#0000FF", "#6666FF")
    else:
        html_body = "NOT_EXIST"
    return html_body
