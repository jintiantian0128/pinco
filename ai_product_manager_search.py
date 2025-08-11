#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI产品经理职位搜索工具
专门用于在上海寻找AI产品经理相关的工作机会
"""

import json
import os
import re
from typing import List, Dict, Any

class AIProductManagerJobSearch:
    def __init__(self, data_dir: str = "boss招聘信息"):
        self.data_dir = data_dir
        self.shanghai_dir = os.path.join(data_dir, "上海")
        
    def search_ai_product_manager_jobs(self) -> List[Dict[str, Any]]:
        """搜索AI产品经理相关职位"""
        ai_jobs = []
        
        # 定义AI产品经理相关的关键词
        ai_keywords = [
            "AI产品经理", "人工智能产品经理", "智能产品经理", 
            "机器学习产品经理", "深度学习产品经理", "大模型产品经理",
            "算法产品经理", "AI算法产品经理", "智能算法产品经理"
        ]
        
        # 定义可能包含AI产品经理的职位类型
        related_positions = [
            "产品经理", "项目经理", "需求分析工程师", "技术经理",
            "算法工程师", "机器学习", "深度学习", "大模型算法"
        ]
        
        # 搜索所有相关职位
        for position in related_positions:
            position_dir = os.path.join(self.shanghai_dir, position)
            if os.path.exists(position_dir):
                jobs = self._search_in_position_dir(position_dir, ai_keywords)
                ai_jobs.extend(jobs)
        
        return ai_jobs
    
    def _search_in_position_dir(self, position_dir: str, ai_keywords: List[str]) -> List[Dict[str, Any]]:
        """在指定职位目录中搜索AI相关职位"""
        jobs = []
        
        for filename in os.listdir(position_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(position_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        job_data = json.load(f)
                        
                    # 检查是否包含AI相关关键词
                    if self._is_ai_related_job(job_data, ai_keywords):
                        jobs.append(job_data)
                        
                except Exception as e:
                    print(f"读取文件 {file_path} 时出错: {e}")
        
        return jobs
    
    def _is_ai_related_job(self, job_data: Dict[str, Any], ai_keywords: List[str]) -> bool:
        """判断职位是否与AI相关"""
        # 检查职位名称
        job_title = job_data.get("职位名称", "").lower()
        
        # 检查岗位职责
        job_responsibilities = job_data.get("岗位职责", "")
        if isinstance(job_responsibilities, list):
            job_responsibilities = " ".join(job_responsibilities)
        job_responsibilities = job_responsibilities.lower()
        
        # 检查技能要求
        skill_requirements = job_data.get("技能要求", "")
        if isinstance(skill_requirements, list):
            skill_requirements = " ".join(skill_requirements)
        skill_requirements = skill_requirements.lower()
        
        # 检查其他要求
        other_requirements = job_data.get("其他要求", "")
        if isinstance(other_requirements, list):
            other_requirements = " ".join(other_requirements)
        other_requirements = other_requirements.lower()
        
        # 合并所有文本进行搜索
        all_text = f"{job_title} {job_responsibilities} {skill_requirements} {other_requirements}"
        
        # 检查是否包含AI相关关键词
        for keyword in ai_keywords:
            if keyword.lower() in all_text:
                return True
        
        # 检查是否包含AI技术相关词汇
        ai_tech_keywords = [
            "机器学习", "深度学习", "神经网络", "自然语言处理", "nlp",
            "计算机视觉", "cv", "语音识别", "asr", "推荐算法", "大模型",
            "gpt", "bert", "transformer", "算法", "模型", "ai", "人工智能"
        ]
        
        for keyword in ai_tech_keywords:
            if keyword.lower() in all_text:
                return True
        
        return False
    
    def display_jobs(self, jobs: List[Dict[str, Any]]):
        """展示找到的职位信息"""
        if not jobs:
            print("很抱歉，在当前数据中没有找到明确的AI产品经理职位。")
            print("\n不过，我为您找到了一些相关的职位信息：")
            return
        
        print(f"找到 {len(jobs)} 个AI产品经理相关职位：")
        print("=" * 80)
        
        for i, job in enumerate(jobs, 1):
            print(f"\n{i}. {job.get('职位名称', '未知职位')}")
            print(f"   公司：{job.get('公司名称', '未知公司')}")
            print(f"   地点：{job.get('工作地点', '未知地点')}")
            print(f"   经验：{job.get('工作经验', '未提及')}")
            print(f"   学历：{job.get('学历要求', '未提及')}")
            
            # 显示岗位职责
            responsibilities = job.get('岗位职责', '')
            if responsibilities:
                if isinstance(responsibilities, list):
                    print("   职责：")
                    for resp in responsibilities[:3]:  # 只显示前3条
                        print(f"     • {resp}")
                else:
                    print(f"   职责：{responsibilities[:100]}...")
            
            # 显示技能要求
            skills = job.get('技能要求', '')
            if skills:
                if isinstance(skills, list):
                    print("   技能：")
                    for skill in skills[:5]:  # 只显示前5条
                        print(f"     • {skill}")
                else:
                    print(f"   技能：{skills[:100]}...")
            
            print("-" * 80)
    
    def get_job_recommendations(self) -> List[Dict[str, Any]]:
        """获取职位推荐"""
        print("正在搜索AI产品经理相关职位...")
        ai_jobs = self.search_ai_product_manager_jobs()
        
        if not ai_jobs:
            # 如果没有找到明确的AI产品经理职位，返回一些相关职位
            print("未找到明确的AI产品经理职位，为您推荐一些相关职位：")
            return self._get_related_jobs()
        
        return ai_jobs
    
    def _get_related_jobs(self) -> List[Dict[str, Any]]:
        """获取相关职位推荐"""
        related_jobs = []
        
        # 搜索产品经理职位
        pm_dir = os.path.join(self.shanghai_dir, "需求分析工程师")
        if os.path.exists(pm_dir):
            for filename in os.listdir(pm_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(pm_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            job_data = json.load(f)
                            if "产品经理" in job_data.get("职位名称", ""):
                                related_jobs.append(job_data)
                    except:
                        continue
        
        return related_jobs[:5]  # 返回前5个相关职位

def main():
    """主函数"""
    print("🤖 AI产品经理职位搜索工具")
    print("=" * 50)
    
    searcher = AIProductManagerJobSearch()
    jobs = searcher.get_job_recommendations()
    
    if jobs:
        searcher.display_jobs(jobs)
        
        print("\n💡 求职建议：")
        print("1. 重点关注包含'AI'、'机器学习'、'深度学习'等关键词的职位")
        print("2. 查看岗位职责中是否涉及算法、模型、数据分析等内容")
        print("3. 关注技能要求中是否包含Python、SQL、数据分析等技能")
        print("4. 建议同时关注'产品经理'、'项目经理'等相近职位")
        print("5. 可以尝试搜索'算法工程师'、'机器学习'等职位，了解技术趋势")
        
        print("\n🔍 扩展搜索建议：")
        print("• 在BOSS直聘、拉勾网等平台搜索'AI产品经理'")
        print("• 关注字节跳动、百度、阿里、腾讯等大厂的AI产品岗位")
        print("• 查看AI初创公司的产品经理职位")
        print("• 关注传统企业数字化转型中的AI产品机会")
    else:
        print("未找到相关职位信息。")
        print("建议您：")
        print("1. 在主流招聘平台搜索'AI产品经理'")
        print("2. 关注AI技术公司的产品经理职位")
        print("3. 考虑从传统产品经理转型到AI产品经理")

if __name__ == "__main__":
    main() 