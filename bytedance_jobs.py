#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
字节跳动算法工程师岗位详细分析
"""

import json
from pathlib import Path
import re
from collections import Counter

def analyze_bytedance_jobs():
    """分析字节跳动的算法工程师岗位"""
    print("🎯 字节跳动算法工程师岗位详细分析")
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
    
    # 搜索字节跳动相关岗位
    bytedance_jobs = []
    for job in job_data:
        company_name = str(job.get('公司名称', '')).lower()
        job_title = str(job.get('职位名称', '')).lower()
        
        # 字节跳动相关公司名称关键词
        bytedance_keywords = [
            '字节跳动', 'bytedance', '字节', '抖音', '今日头条', 
            'tiktok', 'douyin', 'toutiao', '火山引擎', '飞书'
        ]
        
        # 算法工程师相关关键词
        algorithm_keywords = [
            '算法工程师', '算法', '机器学习', '深度学习', 'ai', '人工智能',
            'nlp', '自然语言处理', '推荐算法', '搜索算法', '计算机视觉',
            'cv', '数据挖掘', '模式识别', '智能算法'
        ]
        
        # 检查是否是字节跳动公司且包含算法相关关键词
        is_bytedance = any(keyword in company_name for keyword in bytedance_keywords)
        is_algorithm_job = any(keyword in job_title for keyword in algorithm_keywords)
        
        if is_bytedance and is_algorithm_job:
            bytedance_jobs.append(job)
    
    print(f"🎯 找到 {len(bytedance_jobs)} 个字节跳动算法工程师相关岗位")
    print("=" * 60)
    
    if not bytedance_jobs:
        print("❌ 未找到字节跳动的算法工程师岗位")
        return
    
    # 按职位类型分类
    job_categories = {
        '推荐算法工程师': [],
        '搜索算法工程师': [],
        'NLP算法工程师': [],
        '机器学习算法工程师': [],
        '深度学习工程师': [],
        '计算机视觉工程师': [],
        '数据挖掘工程师': [],
        '其他算法工程师': []
    }
    
    for job in bytedance_jobs:
        job_title = job.get('职位名称', '').lower()
        
        if '推荐' in job_title:
            job_categories['推荐算法工程师'].append(job)
        elif '搜索' in job_title:
            job_categories['搜索算法工程师'].append(job)
        elif 'nlp' in job_title or '自然语言' in job_title or '语言处理' in job_title:
            job_categories['NLP算法工程师'].append(job)
        elif '机器学习' in job_title or 'ml' in job_title:
            job_categories['机器学习算法工程师'].append(job)
        elif '深度学习' in job_title or 'deep learning' in job_title:
            job_categories['深度学习工程师'].append(job)
        elif '视觉' in job_title or 'cv' in job_title or '图像' in job_title:
            job_categories['计算机视觉工程师'].append(job)
        elif '数据挖掘' in job_title:
            job_categories['数据挖掘工程师'].append(job)
        else:
            job_categories['其他算法工程师'].append(job)
    
    # 显示各类型岗位数量
    print("📊 字节跳动算法工程师岗位类型分布")
    print("-" * 40)
    for category, jobs in job_categories.items():
        if jobs:
            print(f"{category}: {len(jobs)}个岗位")
    
    # 按城市分析
    print(f"\n🏙️ 字节跳动算法工程师岗位城市分布")
    print("-" * 40)
    
    cities = Counter()
    for job in bytedance_jobs:
        location = job.get('工作地点', '')
        # 提取城市名
        city_match = re.search(r'([北京上海深圳杭州广州成都西安武汉南京苏州天津重庆])', location)
        if city_match:
            city = city_match.group(1)
            cities[city] += 1
        else:
            cities['其他城市'] += 1
    
    for city, count in cities.most_common():
        print(f"{city}: {count}个岗位")
    
    # 显示具体岗位详情
    print(f"\n💼 字节跳动算法工程师岗位详情")
    print("=" * 60)
    
    # 按类型显示岗位
    for category, jobs in job_categories.items():
        if jobs:
            print(f"\n🎯 {category} ({len(jobs)}个岗位)")
            print("-" * 50)
            
            for i, job in enumerate(jobs, 1):
                print(f"\n{i}. {job.get('职位名称', '未知职位')}")
                print(f"   公司: {job.get('公司名称', '未知公司')}")
                print(f"   地点: {job.get('工作地点', '未知')}")
                print(f"   薪资: {job.get('薪资范围', '面议')}")
                
                skills = str(job.get('技能要求', '暂无'))
                if len(skills) > 150:
                    skills = skills[:150] + "..."
                print(f"   要求: {skills}")
                
                duties = str(job.get('岗位职责', '暂无'))
                if len(duties) > 100:
                    duties = duties[:100] + "..."
                print(f"   职责: {duties}")
    
    # 技能要求分析
    print(f"\n🛠️ 字节跳动算法工程师技能要求分析")
    print("=" * 50)
    
    skill_stats = Counter()
    for job in bytedance_jobs:
        skills = str(job.get('技能要求', ''))
        if skills:
            # 提取技能关键词
            skill_keywords = [
                'Python', 'C++', 'Java', 'Go', 'Scala', 'TensorFlow', 'PyTorch', 
                '机器学习', '深度学习', '神经网络', 'NLP', 'CV', '计算机视觉',
                '算法', '数据结构', '数学', '统计', '概率', '线性代数',
                'SQL', 'Hadoop', 'Spark', 'Hive', 'Git', 'Linux', 'Docker',
                'BERT', 'Transformer', 'GPT', '大模型', 'LLM', '推荐系统',
                '搜索', '广告', '风控', '反作弊', 'AB测试'
            ]
            
            for skill in skill_keywords:
                if skill in skills:
                    skill_stats[skill] += 1
    
    print("热门技能要求（按出现频率排序）:")
    for skill, count in skill_stats.most_common(20):
        percentage = (count / len(bytedance_jobs)) * 100
        print(f"  {skill}: {count}次 ({percentage:.1f}%)")
    
    # 工作经验要求分析
    print(f"\n📈 字节跳动算法工程师工作经验要求分析")
    print("=" * 50)
    
    experience_stats = Counter()
    for job in bytedance_jobs:
        experience = str(job.get('工作经验', ''))
        if experience and experience != '未提及':
            experience_stats[experience] += 1
    
    if experience_stats:
        for exp, count in experience_stats.most_common():
            percentage = (count / len(bytedance_jobs)) * 100
            print(f"  {exp}: {count}个岗位 ({percentage:.1f}%)")
    else:
        print("  大部分岗位未明确工作经验要求")
    
    # 学历要求分析
    print(f"\n🎓 字节跳动算法工程师学历要求分析")
    print("=" * 50)
    
    education_stats = Counter()
    for job in bytedance_jobs:
        education = str(job.get('学历要求', ''))
        if education and education != '未提及':
            education_stats[education] += 1
    
    if education_stats:
        for edu, count in education_stats.most_common():
            percentage = (count / len(bytedance_jobs)) * 100
            print(f"  {edu}: {count}个岗位 ({percentage:.1f}%)")
    else:
        print("  大部分岗位未明确学历要求")
    
    # 薪资分析
    print(f"\n💰 字节跳动算法工程师薪资分析")
    print("=" * 50)
    
    salary_stats = Counter()
    for job in bytedance_jobs:
        salary = str(job.get('薪资范围', ''))
        if salary and salary != '未提及':
            salary_stats[salary] += 1
    
    if salary_stats:
        for salary, count in salary_stats.most_common():
            percentage = (count / len(bytedance_jobs)) * 100
            print(f"  {salary}: {count}个岗位 ({percentage:.1f}%)")
    else:
        print("  大部分岗位薪资面议")
    
    print(f"\n✅ 分析完成！字节跳动共有 {len(bytedance_jobs)} 个算法工程师相关岗位")
    
    # 求职建议
    print(f"\n💡 字节跳动算法工程师求职建议")
    print("=" * 50)
    print("1. 重点掌握Python、C++、Java等编程语言")
    print("2. 深入学习机器学习和深度学习算法")
    print("3. 熟悉TensorFlow、PyTorch等深度学习框架")
    print("4. 了解推荐系统、搜索算法、NLP等业务场景")
    print("5. 掌握大数据技术栈（Hadoop、Spark、Hive等）")
    print("6. 具备扎实的算法和数据结构基础")
    print("7. 熟悉Linux、Git等开发工具")
    print("8. 关注大模型、LLM等前沿技术")

if __name__ == "__main__":
    analyze_bytedance_jobs() 