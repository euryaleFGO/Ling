"""
简单的 HTTP 服务器，用于 Java 和 Python 之间的消息传递
- Java 轮询 GET /api/message 获取 AI 回复
- Python 通过 POST /api/message 发送 AI 回复片段
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from queue import Queue
import time
import sys
import os
from pathlib import Path

# 确保日志立即输出
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 消息队列（存储消息片段）
message_queue = Queue()
# 当前消息缓冲区（用于流式发送）
current_message_buffer = []
last_buffer_update = 0

# message_server 只负责 Java 和 Python 之间的消息传递
# 不需要 Agent，用户消息由 send_user_message.py 直接处理

class MessageHandler(BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        """重写日志方法，确保能看到请求"""
        print(f"[Message Server] {self.command} {self.path} - {code}")
        sys.stdout.flush()
    
    def do_GET(self):
        """获取消息（流式）"""
        global current_message_buffer, last_buffer_update
        
        print(f"[Message Server] GET 请求: {self.path}")
        sys.stdout.flush()
        
        if self.path == '/api/message':
            # 检查队列中是否有新消息片段
            new_chunks = []
            while not message_queue.empty():
                new_chunks.append(message_queue.get())
            
            # 如果有新片段，添加到缓冲区
            if new_chunks:
                current_message_buffer.extend(new_chunks)
                last_buffer_update = time.time()
            
            # 如果缓冲区有内容，返回最新的累积消息
            if current_message_buffer:
                # 返回所有累积的文本
                accumulated_text = ''.join(current_message_buffer)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'text': accumulated_text, 
                    'hasMore': not message_queue.empty()
                }).encode('utf-8'))
            else:
                # 如果超过1秒没有更新，清空缓冲区
                if time.time() - last_buffer_update > 1.0 and current_message_buffer:
                    current_message_buffer.clear()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'text': '', 'hasMore': False}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """发送消息"""
        global current_message_buffer, last_buffer_update
        
        print(f"[Message Server] ========== 收到 POST 请求 ==========")
        print(f"[Message Server] 路径: {self.path}")
        print(f"[Message Server] 客户端: {self.client_address}")
        sys.stdout.flush()
        
        if self.path == '/api/message':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                text = data.get('text', '')
                is_new_message = data.get('new', False)  # 是否是新消息（清空之前的）
                
                # message_server 只负责接收 AI 回复并放入队列（Java 会轮询获取）
                # 用户消息由 send_user_message.py 直接调用 Agent，不经过这里
                    
            except Exception as e:
                print(f"[Message Server] ❌ 处理 POST 请求时出错: {e}")
                import traceback
                traceback.print_exc()
                # 出错也要返回，避免继续处理
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
                return
            
            # 非用户消息的处理（AI 回复片段）
            if is_new_message:
                # 新消息，清空缓冲区
                current_message_buffer.clear()
                while not message_queue.empty():
                    try:
                        message_queue.get_nowait()
                    except:
                        pass
            
            if text:
                # 将消息片段添加到队列（只有 AI 回复会到这里）
                message_queue.put(text)
                last_buffer_update = time.time()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # 禁用默认日志输出
        pass

def start_server(port=8765):
    """启动消息服务器"""
    server = HTTPServer(('localhost', port), MessageHandler)
    print(f"消息服务器启动在 http://localhost:{port}")
    server.serve_forever()

def send_message(text, is_new=True):
    """发送消息到 Live2D 窗口"""
    import requests
    try:
        requests.post('http://localhost:8765/api/message', 
                     json={'text': text, 'new': is_new},
                     timeout=1)
    except:
        pass

def send_message_stream(text, delay=0.05):
    """流式发送消息（逐字符）"""
    import requests
    try:
        # 先发送新消息标记
        requests.post('http://localhost:8765/api/message', 
                     json={'text': '', 'new': True},
                     timeout=1)
        
        # 逐字符发送
        for char in text:
            requests.post('http://localhost:8765/api/message', 
                         json={'text': char, 'new': False},
                         timeout=1)
            time.sleep(delay)
    except:
        pass

if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    
    # 打印 Python 环境信息
    print("=" * 60)
    print("[Message Server] 启动信息")
    print("=" * 60)
    print(f"[Message Server] Python 路径: {sys.executable}")
    print(f"[Message Server] Python 版本: {sys.version}")
    print(f"[Message Server] 工作目录: {os.getcwd()}")
    print("=" * 60)
    sys.stdout.flush()
    
    # message_server 只负责消息传递，不需要初始化 Agent
    print("[Message Server] 消息服务器已就绪，等待 AI 回复消息...")
    sys.stdout.flush()
    
    print()
    print("=" * 60)
    sys.stdout.flush()
    
    # start_server 函数内部会打印启动信息
    start_server(port)

