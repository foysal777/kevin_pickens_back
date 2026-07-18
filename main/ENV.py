
import os
import environ
from dotenv import load_dotenv


load_dotenv()


BASE_DIR = os.path.abspath('.')


env = environ.Env(
    DEBUG=(bool, False),
    DATABASE_URL=(str, f'sqlite:///{BASE_DIR}/db.sqlite3'),
)

DB = env.db('DATABASE_URL')

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

HEYGEN_API_KEY = env("HEYGEN_API_KEY")
ELEVENLABS_API_KEY= env("ELEVENLABS_API_KEY")