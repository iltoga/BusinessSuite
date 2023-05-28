# load_env.py
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

os.system(os.getenv("SHELL"))
