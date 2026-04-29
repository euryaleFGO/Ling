#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 VLM (视觉语言模型) 功能

使用方法:
    python scripts/test_vlm.py --image path/to/image.jpg
    python scripts/test_vlm.py --image path/to/image.jpg --prompt "描述这张图片"
    python scripts/test_vlm.py --image path/to/image.jpg --chat
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import argparse
from backend.vision.models.vlm import VLMModel


def test_basic(image_path: str, model_path: str = None):
    """测试基本功能"""
    print("=" * 60)
    print("测试 VLM 基本功能")
    print("=" * 60)
    
    # 初始化模型
    print("\n[1] 初始化模型...")
    vlm = VLMModel(
        model_path=model_path,
        device="auto",
        use_fp16=True
    )
    
    # 生成图像描述（中文）
    print("\n[2] 生成图像描述（中文）...")
    desc_zh = vlm.describe_image(image_path, language="zh")
    print(f"中文描述: {desc_zh}")
    
    # 生成图像描述（英文）
    print("\n[3] 生成图像描述（英文）...")
    desc_en = vlm.describe_image(image_path, language="en")
    print(f"English: {desc_en}")
    
    # 卸载模型
    print("\n[4] 卸载模型...")
    vlm.unload()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_qa(image_path: str, model_path: str = None):
    """测试视觉问答"""
    print("=" * 60)
    print("测试 VLM 视觉问答")
    print("=" * 60)
    
    # 初始化模型
    print("\n[1] 初始化模型...")
    vlm = VLMModel(
        model_path=model_path,
        device="auto",
        use_fp16=True
    )
    
    # 预定义问题
    questions = [
        "这张图片里有什么？",
        "图片中有几个人？",
        "背景是什么地方？",
        "图片的整体氛围如何？"
    ]
    
    print("\n[2] 回答问题...")
    for i, q in enumerate(questions, 1):
        print(f"\n问题 {i}: {q}")
        answer = vlm.answer_question(image_path, q)
        print(f"回答: {answer}")
    
    # 卸载模型
    print("\n[3] 卸载模型...")
    vlm.unload()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_chat(image_path: str, model_path: str = None):
    """测试多轮对话"""
    print("=" * 60)
    print("测试 VLM 多轮对话")
    print("=" * 60)
    
    # 初始化模型
    print("\n[1] 初始化模型...")
    vlm = VLMModel(
        model_path=model_path,
        device="auto",
        use_fp16=True
    )
    
    # 对话历史
    conversation = []
    
    print("\n[2] 开始对话...")
    print("输入 'quit' 退出对话\n")
    
    while True:
        # 用户输入
        user_input = input("你: ").strip()
        
        if user_input.lower() in ['quit', 'exit', '退出']:
            break
        
        if not user_input:
            continue
        
        # 添加到对话历史
        conversation.append({"role": "user", "content": user_input})
        
        # 生成回复
        print("AI: ", end="", flush=True)
        result = vlm.chat(image_path, conversation)
        print(result.text)
        
        # 添加到对话历史
        conversation.append({"role": "assistant", "content": result.text})
        print()
    
    # 卸载模型
    print("\n[3] 卸载模型...")
    vlm.unload()
    
    print("\n" + "=" * 60)
    print("对话结束！")
    print("=" * 60)


def test_custom_prompt(image_path: str, prompt: str, model_path: str = None):
    """测试自定义提示词"""
    print("=" * 60)
    print("测试 VLM 自定义提示词")
    print("=" * 60)
    
    # 初始化模型
    print("\n[1] 初始化模型...")
    vlm = VLMModel(
        model_path=model_path,
        device="auto",
        use_fp16=True
    )
    
    # 生成回复
    print(f"\n[2] 提示词: {prompt}")
    print("\n回复: ", end="", flush=True)
    result = vlm.generate(image_path, prompt)
    print(result.text)
    
    # 卸载模型
    print("\n[3] 卸载模型...")
    vlm.unload()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def test_vision_engine(image_path: str, model_path: str = None):
    """测试通过视觉引擎使用 VLM"""
    print("=" * 60)
    print("测试视觉引擎集成")
    print("=" * 60)
    
    from backend.vision import VisionEngine, VisionConfig
    
    # 配置
    print("\n[1] 配置视觉引擎...")
    config = VisionConfig(
        enable_vlm=True,
        enable_ocr=True,
        enable_detector=True,
        vlm_model_path=model_path,
        device="auto"
    )
    
    # 初始化引擎
    print("\n[2] 初始化引擎...")
    vision = VisionEngine(config)
    
    # 综合分析
    print("\n[3] 综合分析图像...")
    result = vision.analyze(image_path)
    print("\n" + result.to_context("detailed"))
    
    # 卸载
    print("\n[4] 卸载模块...")
    vision.unload()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="测试 VLM 功能")
    parser.add_argument("--image", required=True, help="图像路径")
    parser.add_argument("--model", help="模型路径（可选）")
    parser.add_argument("--prompt", help="自定义提示词")
    parser.add_argument("--chat", action="store_true", help="多轮对话模式")
    parser.add_argument("--qa", action="store_true", help="问答模式")
    parser.add_argument("--engine", action="store_true", help="测试视觉引擎集成")
    
    args = parser.parse_args()
    
    # 检查图像文件
    if not Path(args.image).exists():
        print(f"错误: 图像文件不存在: {args.image}")
        return
    
    # 根据参数选择测试模式
    if args.chat:
        test_chat(args.image, args.model)
    elif args.qa:
        test_qa(args.image, args.model)
    elif args.engine:
        test_vision_engine(args.image, args.model)
    elif args.prompt:
        test_custom_prompt(args.image, args.prompt, args.model)
    else:
        test_basic(args.image, args.model)


if __name__ == "__main__":
    main()
