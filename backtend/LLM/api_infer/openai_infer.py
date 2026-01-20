from openai import OpenAI
from .config import DEEPSEEK_API_KEY, BASE_URL, MODEL
from typing import List, Dict, Optional
import os

class APIInfer:
    def __init__(self, url, api_key, model_name):
        self.url = url
        self.api_key = api_key
        self.model_name = model_name
        self.client = OpenAI(api_key=self.api_key, base_url=self.url)

    def infer(
        self,
        messages: List[Dict],
        stream: bool = True,
        temperature: float = 1.0,
        top_p: float = 1,
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto"
    ):
        """
        调用 LLM 进行推理
        
        Args:
            messages: 消息列表
            stream: 是否流式返回
            temperature: 温度参数
            top_p: top_p 参数
            tools: 工具列表 (OpenAI Function Calling 格式)
            tool_choice: 工具选择策略 ("auto", "none", 或指定工具)
        """
        kwargs = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "top_p": top_p,
        }
        
        # 添加工具参数（如果提供）
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
            # 工具调用时不支持流式
            kwargs["stream"] = False
        
        response = self.client.chat.completions.create(**kwargs)
        return response
    


if __name__ == "__main__":
    
    url = BASE_URL
    api_key = DEEPSEEK_API_KEY
    model_name = MODEL
    apiinfer = APIInfer(url=url,api_key=api_key,model_name=model_name)
    
    while True:
        query = input()
        messages = [
            {"role": "system", "content": "你是豆包，请用中文回答"},
            {"role": "user", "content": query}
        ]

        response = apiinfer.infer(messages=messages)
        for res in response:
            result = res.choices[0].delta.content
            if result:
                print(result,end="",flush=True)
                
        print("\n")
        