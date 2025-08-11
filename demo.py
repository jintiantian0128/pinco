#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
求职辅导Agent演示脚本
演示agent的各项功能
"""

from career_agent import CareerAgent
import json

def demo_chat():
    """演示聊天功能"""
    print("=" * 50)
    print("🎯 智能对话演示")
    print("=" * 50)
    
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    # 测试问题列表
    test_questions = [
        "我想转行做算法工程师，需要学习什么？",
        "北京有哪些Python开发岗位？",
        "如何准备算法工程师面试？",
        "我想了解数据科学家的职业发展路径",
        "深圳的机器学习岗位薪资怎么样？"
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n📝 问题 {i}: {question}")
        print("-" * 40)
        
        try:
            response = agent.chat(question)
            print(f"🤖 回答: {response}")
        except Exception as e:
            print(f"❌ 错误: {e}")
        
        print("-" * 40)

def demo_job_recommendations():
    """演示岗位推荐功能"""
    print("\n" + "=" * 50)
    print("💼 岗位推荐演示")
    print("=" * 50)
    
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    # 测试用户档案
    test_profiles = [
        {
            "skills": ["Python", "机器学习", "深度学习"],
            "experience": "1-3年",
            "location": "北京",
            "education": "硕士",
            "salary_expectation": "20k-30k"
        },
        {
            "skills": ["Java", "Spring", "MySQL"],
            "experience": "3-5年",
            "location": "上海",
            "education": "本科",
            "salary_expectation": "30k-50k"
        },
        {
            "skills": ["算法", "数据结构", "C++"],
            "experience": "应届生",
            "location": "深圳",
            "education": "本科",
            "salary_expectation": "10k-20k"
        }
    ]
    
    for i, profile in enumerate(test_profiles, 1):
        print(f"\n👤 用户档案 {i}:")
        print(f"   技能: {', '.join(profile['skills'])}")
        print(f"   经验: {profile['experience']}")
        print(f"   地点: {profile['location']}")
        print(f"   学历: {profile['education']}")
        print(f"   期望薪资: {profile['salary_expectation']}")
        print("-" * 40)
        
        try:
            recommendations = agent.get_job_recommendations(profile)
            print(f"📋 推荐岗位数量: {len(recommendations)}")
            
            for j, job in enumerate(recommendations[:3], 1):  # 只显示前3个
                print(f"\n   {j}. {job.get('职位名称', '未知职位')}")
                print(f"      公司: {job.get('公司名称', '未知公司')}")
                print(f"      地点: {job.get('工作地点', '未知')}")
                print(f"      薪资: {job.get('薪资范围', '面议')}")
                print(f"      要求: {job.get('技能要求', '暂无')[:50]}...")
                
        except Exception as e:
            print(f"❌ 错误: {e}")
        
        print("-" * 40)

def demo_career_advice():
    """演示求职建议功能"""
    print("\n" + "=" * 50)
    print("💡 求职建议演示")
    print("=" * 50)
    
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    # 测试建议主题
    test_topics = [
        "简历制作",
        "面试技巧",
        "技能提升",
        "职业规划",
        "转行建议"
    ]
    
    for i, topic in enumerate(test_topics, 1):
        print(f"\n📚 建议主题 {i}: {topic}")
        print("-" * 40)
        
        try:
            advice = agent.get_career_advice(topic)
            print(f"💡 建议内容:")
            print(advice[:300] + "..." if len(advice) > 300 else advice)
        except Exception as e:
            print(f"❌ 错误: {e}")
        
        print("-" * 40)

def demo_knowledge_base():
    """演示知识库加载"""
    print("\n" + "=" * 50)
    print("📚 知识库信息")
    print("=" * 50)
    
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    print(f"📋 岗位信息数量: {len(agent.job_knowledge_base)}")
    print(f"📝 问答信息数量: {len(agent.career_knowledge_base)}")
    
    # 显示一些示例数据
    if agent.job_knowledge_base:
        print(f"\n🏢 岗位信息示例:")
        sample_job = agent.job_knowledge_base[0]
        print(f"   职位: {sample_job.get('职位名称', '未知')}")
        print(f"   公司: {sample_job.get('公司名称', '未知')}")
        print(f"   地点: {sample_job.get('工作地点', '未知')}")
    
    if agent.career_knowledge_base:
        print(f"\n❓ 问答信息示例:")
        sample_qa = agent.career_knowledge_base[0]
        print(f"   问题: {sample_qa.get('question', '未知')}")
        if sample_qa.get('answers'):
            print(f"   回答: {sample_qa['answers'][0][:100]}...")

def demo_query_classification():
    """演示查询分类功能"""
    print("\n" + "=" * 50)
    print("🔍 查询分类演示")
    print("=" * 50)
    
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    # 测试查询
    test_queries = [
        "我想做职业规划",
        "推荐一些算法工程师岗位",
        "如何提升编程技能",
        "北京有哪些公司招聘",
        "面试技巧有哪些"
    ]
    
    for query in test_queries:
        query_type = agent._classify_query(query)
        print(f"📝 查询: {query}")
        print(f"🏷️  分类: {query_type}")
        print("-" * 30)

def main():
    """主函数"""
    print("🚀 求职辅导Agent功能演示")
    print("=" * 60)
    
    try:
        # 演示知识库加载
        demo_knowledge_base()
        
        # 演示查询分类
        demo_query_classification()
        
        # 演示聊天功能
        demo_chat()
        
        # 演示岗位推荐
        demo_job_recommendations()
        
        # 演示求职建议
        demo_career_advice()
        
        print("\n" + "=" * 60)
        print("✅ 演示完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        print("请检查API密钥和网络连接")

if __name__ == "__main__":
    main() 