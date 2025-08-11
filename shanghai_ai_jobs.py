#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
上海AI算法工程师岗位详细分析
"""

import json
from pathlib import Path
import re
from collections import Counter

def analyze_shanghai_ai_jobs():
    """分析上海的AI算法工程师岗位"""
    print("🏙️ 上海AI算法工程师岗位详细分析")
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
    
    # 搜索上海的AI相关岗位
    shanghai_ai_jobs = []
    for job in job_data:
        job_title = str(job.get('职位名称', '')).lower()
        job_skills = str(job.get('技能要求', '')).lower()
        job_duties = str(job.get('岗位职责', '')).lower()
        job_location = str(job.get('工作地点', '')).lower()
        
        # 检查是否在上海且包含AI相关关键词
        if '上海' in job_location or 'shanghai' in job_location:
            for keyword in ai_keywords:
                if (keyword.lower() in job_title or 
                    keyword.lower() in job_skills or 
                    keyword.lower() in job_duties):
                    shanghai_ai_jobs.append(job)
                    break
    
    print(f"🎯 找到 {len(shanghai_ai_jobs)} 个上海AI算法工程师相关岗位")
    print("=" * 60)
    
    # 按职位类型分类
    job_categories = {
        'NLP算法工程师': [],
        '机器学习算法工程师': [],
        '深度学习工程师': [],
        '推荐算法工程师': [],
        '搜索算法工程师': [],
        '计算机视觉工程师': [],
        '数据挖掘工程师': [],
        '其他AI算法工程师': []
    }
    
    for job in shanghai_ai_jobs:
        job_title = job.get('职位名称', '').lower()
        
        if 'nlp' in job_title or '自然语言' in job_title or '语言处理' in job_title:
            job_categories['NLP算法工程师'].append(job)
        elif '机器学习' in job_title or 'ml' in job_title:
            job_categories['机器学习算法工程师'].append(job)
        elif '深度学习' in job_title or 'deep learning' in job_title:
            job_categories['深度学习工程师'].append(job)
        elif '推荐' in job_title:
            job_categories['推荐算法工程师'].append(job)
        elif '搜索' in job_title:
            job_categories['搜索算法工程师'].append(job)
        elif '视觉' in job_title or 'cv' in job_title or '图像' in job_title:
            job_categories['计算机视觉工程师'].append(job)
        elif '数据挖掘' in job_title:
            job_categories['数据挖掘工程师'].append(job)
        else:
            job_categories['其他AI算法工程师'].append(job)
    
    # 显示各类型岗位数量
    print("📊 上海AI算法工程师岗位类型分布")
    print("-" * 40)
    for category, jobs in job_categories.items():
        if jobs:
            print(f"{category}: {len(jobs)}个岗位")
    
    # 按区域分析
    print(f"\n🏢 上海各区域AI算法工程师岗位分布")
    print("-" * 40)
    
    districts = Counter()
    for job in shanghai_ai_jobs:
        location = job.get('工作地点', '')
        # 提取上海区域
        district_match = re.search(r'上海([^区]*区)', location)
        if district_match:
            district = district_match.group(1) + '区'
            districts[district] += 1
        else:
            districts['其他区域'] += 1
    
    for district, count in districts.most_common():
        print(f"{district}: {count}个岗位")
    
    # 显示具体岗位详情
    print(f"\n💼 上海AI算法工程师岗位详情")
    print("=" * 60)
    
    # 按类型显示岗位
    for category, jobs in job_categories.items():
        if jobs:
            print(f"\n🎯 {category} ({len(jobs)}个岗位)")
            print("-" * 50)
            
            for i, job in enumerate(jobs[:3], 1):  # 每个类型显示前3个
                print(f"\n{i}. {job.get('职位名称', '未知职位')}")
                print(f"   公司: {job.get('公司名称', '未知公司')}")
                print(f"   地点: {job.get('工作地点', '未知')}")
                print(f"   薪资: {job.get('薪资范围', '面议')}")
                
                skills = str(job.get('技能要求', '暂无'))
                if len(skills) > 100:
                    skills = skills[:100] + "..."
                print(f"   要求: {skills}")
                
                if i >= 3 and len(jobs) > 3:
                    print(f"   ... 还有 {len(jobs) - 3} 个岗位")
                    break
    
    # 技能要求分析
    print(f"\n🛠️ 上海AI算法工程师技能要求分析")
    print("=" * 50)
    
    skill_stats = Counter()
    for job in shanghai_ai_jobs:
        skills = str(job.get('技能要求', ''))
        if skills:
            # 提取技能关键词
            skill_keywords = [
                'Python', 'C++', 'Java', 'TensorFlow', 'PyTorch', 
                '机器学习', '深度学习', '神经网络', 'NLP', 'CV',
                '算法', '数据结构', '数学', '统计', '概率',
                'SQL', 'Hadoop', 'Spark', 'Git', 'Linux',
                'BERT', 'Transformer', 'GPT', '大模型', 'LLM'
            ]
            
            for skill in skill_keywords:
                if skill in skills:
                    skill_stats[skill] += 1
    
    print("热门技能要求（按出现频率排序）:")
    for skill, count in skill_stats.most_common(15):
        percentage = (count / len(shanghai_ai_jobs)) * 100
        print(f"  {skill}: {count}次 ({percentage:.1f}%)")
    
    # 公司分析
    print(f"\n🏢 上海AI算法工程师招聘公司分析")
    print("=" * 50)
    
    company_stats = Counter()
    for job in shanghai_ai_jobs:
        company = job.get('公司名称', '未知公司')
        company_stats[company] += 1
    
    print("招聘公司（按岗位数量排序）:")
    for company, count in company_stats.most_common(10):
        print(f"  {company}: {count}个岗位")
    
    print(f"\n✅ 分析完成！上海共有 {len(shanghai_ai_jobs)} 个AI算法工程师相关岗位")

if __name__ == "__main__":
    analyze_shanghai_ai_jobs() 