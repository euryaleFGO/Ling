"""修复 MongoDB 旧数据中的"主人"硬编码"""
from pymongo import MongoClient

c = MongoClient('localhost', 27017)
db = c['liying_db']

# 1. 更新 user_profiles
r1 = db['user_profiles'].update_one(
    {'user_id': 'default_user'},
    {'$set': {'nickname': '用户', 'preferences.call_me': '用户'}}
)
print(f'user_profiles 更新: {r1.modified_count} 条')

# 2. 更新 character_settings
doc = db['character_settings'].find_one({'name': '玲'})
if doc:
    prompt = doc.get('system_prompt', '')
    # 替换所有"主人"为通用表述
    replacements = [
        ('称呼用户为"主人"', '用用户设定的称呼来称呼用户'),
        ('【必须】称呼用户为"主人"，不要说"Master"', '【必须】用用户设定的称呼来称呼用户，不要说"Master"'),
        ('关心主人的生活和情绪', '关心用户的生活和情绪'),
        ('当主人夸奖时会害羞', '当用户夸奖时会害羞'),
        ('记住主人告诉你的信息', '记住用户告诉你的信息'),
        ('根据主人的情绪调整语气', '根据用户的情绪调整语气'),
    ]
    for old, new in replacements:
        prompt = prompt.replace(old, new)

    r2 = db['character_settings'].update_one(
        {'name': '玲'},
        {'$set': {
            'system_prompt': prompt,
            'greeting': '你好呀~ 今天过得怎么样呀？'
        }}
    )
    print(f'character_settings 更新: {r2.modified_count} 条')
    print()
    print('=== 更新后 system_prompt ===')
    print(prompt)
else:
    print('未找到角色"玲"')

# 3. 验证
print('\n=== 验证 ===')
profile = db['user_profiles'].find_one({'user_id': 'default_user'})
print(f"user_profiles.nickname: {profile.get('nickname')}")
print(f"user_profiles.call_me: {profile.get('preferences', {}).get('call_me')}")

char = db['character_settings'].find_one({'name': '玲'})
print(f"greeting: {char.get('greeting')}")
has_master = '主人' in char.get('system_prompt', '')
print(f"system_prompt 仍含\"主人\": {has_master}")
