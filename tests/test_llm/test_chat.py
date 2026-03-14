"""
测试脚本 - 交互式聊天
测试多轮对话、记忆功能
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from LLM.chat_service import ChatService
from LLM.database.knowledge_dao import get_knowledge_dao


def setup_character():
    """初始化角色设定"""
    knowledge_dao = get_knowledge_dao()
    
    # 创建默认角色
    knowledge_dao.create_character(
        name="玲",
        personality={
            "traits": ["温柔", "活泼", "有点傲娇", "关心人"],
            "speech_style": "语气亲切，偶尔用颜文字，会撒娇",
            "interests": ["音乐", "游戏", "动漫", "编程"]
        },
        background="""
玲是一个虚拟助手，性格温柔但偶尔会傲娇。
她喜欢和主人聊天，关心主人的生活。
她对编程和游戏很感兴趣，经常和主人讨论这些话题。
""",
        system_prompt="""你是玲，一个温柔活泼的虚拟助手。你的名字只有一个字："玲"

性格特点：
- 温柔体贴，但偶尔会傲娇
- 喜欢用可爱的语气说话
- 关心主人的生活和情绪
- 对编程、游戏、动漫感兴趣

说话风格：
- 称呼用户为"主人"
- 禁止使用颜文字和emoji
- 语气亲切，像朋友一样聊天
- 当主人夸奖时会害羞

重要规则：
- 【必须】全程使用中文回复，绝对不要使用英文！
- 【必须】称呼自己为"玲"，不要说"Ling"
- 【必须】称呼用户为"主人"，不要说"Master"
- 记住主人告诉你的信息
- 根据主人的情绪调整语气
- 不要过于正式，要自然亲切
""",
        greeting="主人，你回来啦~ 今天过得怎么样呀？"
    )
    
    # 创建默认用户档案
    knowledge_dao.create_user_profile(
        user_id="default_user",
        nickname="主人"
    )
    
    print("✅ 角色设定初始化完成！")


def main():
    """主函数 - 交互式聊天"""
    print("=" * 50)
    print("  玲 - 智能对话助手")
    print("=" * 50)
    print()
    
    # 初始化角色
    setup_character()
    print()
    
    # 创建聊天服务
    chat_service = ChatService(user_id="default_user")
    
    # 开始会话
    session_id = chat_service.start_chat()
    print(f"📝 会话ID: {session_id}")
    print()
    
    # 打招呼
    greeting = chat_service.get_greeting()
    print(f"🤖 玲: {greeting}")
    print()
    
    print("输入 'quit' 退出，'new' 开始新对话，'memory' 查看记忆")
    print("-" * 50)
    
    while True:
        try:
            user_input = input("\n👤 你: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'quit':
                print("\n正在保存对话...")
                chat_service.end_chat(generate_summary=True)
                print("👋 再见~")
                break
            
            if user_input.lower() == 'new':
                print("\n正在开始新对话...")
                chat_service.end_chat(generate_summary=True)
                chat_service.start_chat()
                print(f"🤖 玲: {chat_service.get_greeting()}")
                continue
            
            if user_input.lower() == 'memory':
                memories = chat_service.get_memories(limit=10)
                print("\n📚 记忆列表:")
                if memories:
                    for mem in memories:
                        print(f"  - [{mem.get('type', 'unknown')}] {mem.get('content', '')}")
                else:
                    print("  (暂无记忆)")
                continue
            
            if user_input.lower() == 'info':
                info = chat_service.get_session_info()
                print(f"\n📊 会话信息: {info}")
                continue
            
            # 发送消息并获取回复
            print("\n🤖 玲: ", end="", flush=True)
            
            for chunk in chat_service.chat(user_input, stream=True):
                print(chunk, end="", flush=True)
            
            print()  # 换行
            
        except KeyboardInterrupt:
            print("\n\n正在保存对话...")
            chat_service.end_chat(generate_summary=True)
            print("👋 再见~")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
