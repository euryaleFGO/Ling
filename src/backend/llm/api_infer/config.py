import os
from dotenv import load_dotenv

#加载环境变量
load_dotenv()

#获取密钥
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
#获取基础URL
BASE_URL = os.getenv('BASE_URL')
#获取模型名称
MODEL = os.getenv('MODEL')