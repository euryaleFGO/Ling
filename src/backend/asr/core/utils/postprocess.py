# -*- coding: utf-8 -*-
"""
文本后处理工具
简化自 FunASR runtime/python/onnxruntime/funasr_onnx/utils/postprocess_utils.py
"""

from typing import Any, List, Union


def is_chinese(ch: str) -> bool:
    """判断字符是否为中文或数字"""
    if "\u4e00" <= ch <= "\u9fff" or "\u0030" <= ch <= "\u0039":
        return True
    return False


def is_all_chinese(word: Union[List[Any], str]) -> bool:
    """判断是否全为中文字符"""
    word_lists = []
    for i in word:
        cur = i.replace(" ", "")
        cur = cur.replace("</s>", "")
        cur = cur.replace("<s>", "")
        word_lists.append(cur)

    if len(word_lists) == 0:
        return False

    for ch in word_lists:
        if not is_chinese(ch):
            return False
    return True


def is_all_alpha(word: Union[List[Any], str]) -> bool:
    """判断是否全为英文字母"""
    word_lists = []
    for i in word:
        cur = i.replace(" ", "")
        cur = cur.replace("</s>", "")
        cur = cur.replace("<s>", "")
        word_lists.append(cur)

    if len(word_lists) == 0:
        return False

    for ch in word_lists:
        if not ch.isalpha() and ch != "'":
            return False
        elif ch.isalpha() and is_chinese(ch):
            return False
    return True


def abbr_dispose(words: List[Any], time_stamp: List[List] = None) -> List[Any]:
    """处理缩写词"""
    words_size = len(words)
    word_lists = []
    abbr_begin = []
    abbr_end = []
    last_num = -1
    ts_lists = []
    ts_nums = []
    ts_index = 0
    
    for num in range(words_size):
        if num <= last_num:
            continue

        if len(words[num]) == 1 and words[num].encode("utf-8").isalpha():
            if (
                num + 1 < words_size
                and words[num + 1] == " "
                and num + 2 < words_size
                and len(words[num + 2]) == 1
                and words[num + 2].encode("utf-8").isalpha()
            ):
                abbr_begin.append(num)
                num += 2
                abbr_end.append(num)
                while True:
                    num += 1
                    if num < words_size and words[num] == " ":
                        num += 1
                        if (
                            num < words_size
                            and len(words[num]) == 1
                            and words[num].encode("utf-8").isalpha()
                        ):
                            abbr_end.pop()
                            abbr_end.append(num)
                            last_num = num
                        else:
                            break
                    else:
                        break

    for num in range(words_size):
        if words[num] == " ":
            ts_nums.append(ts_index)
        else:
            ts_nums.append(ts_index)
            ts_index += 1
    
    last_num = -1
    for num in range(words_size):
        if num <= last_num:
            continue

        if num in abbr_begin:
            if time_stamp is not None:
                begin = time_stamp[ts_nums[num]][0]
            word_lists.append(words[num].upper())
            num += 1
            while num < words_size:
                if num in abbr_end:
                    word_lists.append(words[num].upper())
                    last_num = num
                    break
                else:
                    if words[num].encode("utf-8").isalpha():
                        word_lists.append(words[num].upper())
                num += 1
            if time_stamp is not None:
                end = time_stamp[ts_nums[num]][1]
                ts_lists.append([begin, end])
        else:
            word_lists.append(words[num])
            if time_stamp is not None and words[num] != " ":
                begin = time_stamp[ts_nums[num]][0]
                end = time_stamp[ts_nums[num]][1]
                ts_lists.append([begin, end])

    if time_stamp is not None:
        return word_lists, ts_lists
    else:
        return word_lists


def sentence_postprocess(words: List[Any], time_stamp: List[List] = None):
    """
    句子后处理
    
    Args:
        words: Token 列表
        time_stamp: 时间戳列表（可选）
        
    Returns:
        处理后的句子文本
    """
    middle_lists = []
    word_lists = []
    word_item = ""
    ts_lists = []

    # 清洗词列表
    for i in words:
        word = ""
        if isinstance(i, str):
            word = i
        else:
            word = i.decode("utf-8")

        if word in ["<s>", "</s>", "<unk>"]:
            continue
        else:
            middle_lists.append(word)

    # 全中文字符
    if is_all_chinese(middle_lists):
        for i, ch in enumerate(middle_lists):
            word_lists.append(ch.replace(" ", ""))
        if time_stamp is not None:
            ts_lists = time_stamp

    # 全英文字符
    elif is_all_alpha(middle_lists):
        ts_flag = True
        begin = 0
        end = 0
        for i, ch in enumerate(middle_lists):
            if ts_flag and time_stamp is not None:
                begin = time_stamp[i][0]
                end = time_stamp[i][1]
            
            if "@@" in ch:
                word = ch.replace("@@", "")
                word_item += word
                if time_stamp is not None:
                    ts_flag = False
                    end = time_stamp[i][1]
            else:
                word_item += ch
                word_lists.append(word_item)
                word_lists.append(" ")
                word_item = ""
                if time_stamp is not None:
                    ts_flag = True
                    end = time_stamp[i][1]
                    ts_lists.append([begin, end])

    # 中英混合字符
    else:
        alpha_blank = False
        ts_flag = True
        begin = -1
        end = -1
        
        for i, ch in enumerate(middle_lists):
            if ts_flag and time_stamp is not None:
                begin = time_stamp[i][0]
                end = time_stamp[i][1]
            
            if is_all_chinese(ch):
                if alpha_blank:
                    word_lists.pop()
                word_lists.append(ch)
                alpha_blank = False
                if time_stamp is not None:
                    ts_flag = True
                    ts_lists.append([begin, end])
            elif "@@" in ch:
                word = ch.replace("@@", "")
                word_item += word
                alpha_blank = False
                if time_stamp is not None:
                    ts_flag = False
                    end = time_stamp[i][1]
            elif is_all_alpha(ch):
                word_item += ch
                word_lists.append(word_item)
                word_lists.append(" ")
                word_item = ""
                alpha_blank = True
                if time_stamp is not None:
                    ts_flag = True
                    end = time_stamp[i][1]
                    ts_lists.append([begin, end])

    if time_stamp is not None:
        word_lists, ts_lists = abbr_dispose(word_lists, ts_lists)
        real_word_lists = []
        for ch in word_lists:
            if ch != " ":
                real_word_lists.append(ch)
        sentence = " ".join(real_word_lists).strip()
        return sentence, ts_lists, real_word_lists
    else:
        word_lists = abbr_dispose(word_lists)
        real_word_lists = []
        for ch in word_lists:
            if ch != " ":
                real_word_lists.append(ch)
        sentence = "".join(word_lists).strip()
        return sentence, real_word_lists
