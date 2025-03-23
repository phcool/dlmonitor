import os, sys
from os import path
import inspect
from dotenv import load_dotenv


PROJECT_ROOT = os.environ.get(
    'PROJECT_ROOT',
    path.dirname(path.dirname(inspect.getfile(inspect.currentframe()))))

load_dotenv(path.join(PROJECT_ROOT, '.env'))

DATABASE_ADDR = os.environ.get('DATABASE_ADDR', 'localhost')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'dlmonitor')
DATABASE_USER = os.environ.get('DATABASE_USER', "user")
DATABASE_PASSWD = os.environ.get('DATABASE_PASSWD', "pass")

DATABASE_URL = os.environ.get('DATABASE_URL', "postgresql://{}:{}@{}/{}".format(
    DATABASE_USER, DATABASE_PASSWD, DATABASE_ADDR, DATABASE_NAME))

DEFAULT_MODEL = os.environ.get('DEFAULT_MODEL', "all-MiniLM-L6-v2")
NUMBER_EACH_PAGE = os.environ.get('NUMBER_EACH_PAGE', 100)


SESSION_KEY = os.environ.get("SESSION_KEY", "DEEPLEARN.ORG SECRET KEY")
