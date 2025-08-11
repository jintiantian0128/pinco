#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI算法工程师岗位搜索脚本
"""

import json
from pathlib import Path
import re

def search_ai_jobs():
    """搜索AI算法工程师相关岗位"""
    print("🔍 正在搜索AI算法工程师岗位...")
    print("=" * 60)
    
    # 加载所有岗位数据
    job_data = []
    job_dir = Path("boss招聘信息")
    
    if not job_dir.exists():
        print("❌ Boss招聘信息目录不存在")
        return
    
    # 遍历所有JSON文件
    for json_file in job_dir.rglob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                job_info = json.load(f)
                job_data.append(job_info)
        except Exception as e:
            continue
    
    print(f"📋 总共加载了 {len(job_data)} 条岗位信息")
    
    # 定义AI算法工程师相关关键词
    ai_keywords = [
        'AI', '人工智能', '算法工程师', '机器学习', '深度学习', 
        '自然语言处理', 'NLP', '计算机视觉', 'CV', '推荐算法',
        '大模型', 'LLM', 'GPT', 'BERT', 'Transformer', '神经网络',
        '数据挖掘', '模式识别', '智能算法', 'AI算法'
    ]
    
    # 搜索匹配的岗位
    ai_jobs = []
    for job in job_data:
        job_title = str(job.get('职位名称', '')).lower()
        job_skills = str(job.get('技能要求', '')).lower()
        job_duties = str(job.get('岗位职责', '')).lower()
        
        # 检查是否包含AI相关关键词
        for keyword in ai_keywords:
            if (keyword.lower() in job_title or 
                keyword.lower() in job_skills or 
                keyword.lower() in job_duties):
                ai_jobs.append(job)
                break
    
    print(f"🎯 找到 {len(ai_jobs)} 个AI算法工程师相关岗位")
    print("=" * 60)
    
    # 按城市分组显示
    cities = {}
    for job in ai_jobs:
        city = job.get('工作地点', '未知')
        # 提取城市名
        city_match = re.search(r'([北京上海深圳杭州广州成都西安武汉南京苏州天津重庆])', city)
        if city_match:
            city = city_match.group(1)
        else:
            city = '其他'
        
        if city not in cities:
            cities[city] = []
        cities[city].append(job)
    
    # 显示结果
    for city, jobs in sorted(cities.items()):
        print(f"\n🏙️  {city} ({len(jobs)}个岗位)")
        print("-" * 40)
        
        for i, job in enumerate(jobs[:5], 1):  # 每个城市最多显示5个
            print(f"\n{i}. {job.get('职位名称', '未知职位')}")
            print(f"   公司: {job.get('公司名称', '未知公司')}")
            print(f"   地点: {job.get('工作地点', '未知')}")
            print(f"   薪资: {job.get('薪资范围', '面议')}")
            print(f"   要求: {job.get('技能要求', '暂无')[:100]}...")
            
            if i >= 5:
                print(f"   ... 还有 {len(jobs) - 5} 个岗位")
                break
    
    # 显示技能要求统计
    print(f"\n📊 AI算法工程师技能要求统计")
    print("=" * 40)
    
    skill_stats = {}
    for job in ai_jobs:
        skills = str(job.get('技能要求', ''))
        if skills:
            # 提取技能关键词
            skill_keywords = [
                'Python', 'C++', 'Java', 'TensorFlow', 'PyTorch', 
                '机器学习', '深度学习', '神经网络', 'NLP', 'CV',
                '算法', '数据结构', '数学', '统计', '概率',
                'SQL', 'Hadoop', 'Spark', 'Git', 'Linux'
            ]
            
            for skill in skill_keywords:
                if skill in skills:
                    skill_stats[skill] = skill_stats.get(skill, 0) + 1
    
    # 按出现频率排序
    sorted_skills = sorted(skill_stats.items(), key=lambda x: x[1], reverse=True)
    
    print("热门技能要求（按出现频率排序）:")
    for skill, count in sorted_skills[:10]:
        percentage = (count / len(ai_jobs)) * 100
        print(f"  {skill}: {count}次 ({percentage:.1f}%)")
    
    print(f"\n✅ 搜索完成！共找到 {len(ai_jobs)} 个AI算法工程师相关岗位")

if __name__ == "__main__":
    search_ai_jobs() 