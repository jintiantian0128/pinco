#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
求职辅导Agent测试版本
不依赖外部API，用于验证基本功能
"""

import json
import logging
from typing import List, Dict, Any
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestCareerAgent:
    def __init__(self):
        """初始化测试版本的求职辅导agent"""
        # 初始化知识库
        self.job_knowledge_base = self._load_job_knowledge()
        self.career_knowledge_base = self._load_career_knowledge()
        
        # 预设的回答模板
        self.response_templates = {
            'career_planning': {
                '转行': '转行需要系统性的规划：\n1. 评估当前技能与目标岗位的差距\n2. 制定学习计划和时间表\n3. 积累相关项目经验\n4. 建立行业人脉网络\n5. 准备面试和简历',
                '职业规划': '职业规划建议：\n1. 明确短期和长期目标\n2. 分析行业发展趋势\n3. 持续学习新技能\n4. 建立个人品牌\n5. 定期评估和调整计划',
                '发展路径': '职业发展路径：\n1. 初级工程师（0-2年）\n2. 中级工程师（2-5年）\n3. 高级工程师（5-8年）\n4. 技术专家/架构师（8年以上）\n5. 技术管理（可选路径）'
            },
            'job_recommendation': {
                '算法工程师': '算法工程师岗位要求：\n1. 扎实的数学基础（线性代数、概率统计）\n2. 编程能力（Python、C++）\n3. 机器学习算法知识\n4. 数据处理和分析能力\n5. 项目经验',
                'Python开发': 'Python开发工程师要求：\n1. 精通Python编程\n2. 熟悉Web框架（Django、Flask）\n3. 数据库操作（MySQL、PostgreSQL）\n4. 版本控制（Git）\n5. 系统设计能力',
                '数据科学家': '数据科学家要求：\n1. 统计学和数学基础\n2. 机器学习算法\n3. 数据可视化技能\n4. 业务理解能力\n5. 沟通和表达能力'
            },
            'skill_guidance': {
                '面试': '面试准备建议：\n1. 复习技术基础知识\n2. 准备项目案例\n3. 练习编程题\n4. 准备自我介绍\n5. 了解公司背景',
                '简历': '简历制作要点：\n1. 突出核心技能和经验\n2. 量化项目成果\n3. 使用关键词优化\n4. 保持简洁清晰\n5. 定期更新内容',
                '技能提升': '技能提升方法：\n1. 在线课程学习\n2. 实践项目开发\n3. 参与开源项目\n4. 阅读技术博客\n5. 参加技术会议'
            }
        }
    
    def _load_job_knowledge(self) -> List[Dict]:
        """加载Boss招聘信息作为岗位推荐知识库"""
        job_data = []
        job_dir = Path("boss招聘信息")
        
        if not job_dir.exists():
            logger.warning("Boss招聘信息目录不存在")
            return job_data
        
        # 遍历所有JSON文件
        for json_file in job_dir.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    job_info = json.load(f)
                    # 添加文件路径信息用于溯源
                    job_info['source_file'] = str(json_file)
                    job_data.append(job_info)
            except Exception as e:
                logger.error(f"加载文件 {json_file} 失败: {e}")
        
        logger.info(f"成功加载 {len(job_data)} 条岗位信息")
        return job_data
    
    def _load_career_knowledge(self) -> List[Dict]:
        """加载知乎问答信息作为求职技能辅导知识库"""
        career_data = []
        zhihu_dir = Path("知乎问答")
        
        if not zhihu_dir.exists():
            logger.warning("知乎问答目录不存在")
            return career_data
        
        # 遍历所有JSON文件
        for json_file in zhihu_dir.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    qa_info = json.load(f)
                    # 添加文件路径信息用于溯源
                    qa_info['source_file'] = str(json_file)
                    career_data.append(qa_info)
            except Exception as e:
                logger.error(f"加载文件 {json_file} 失败: {e}")
        
        logger.info(f"成功加载 {len(career_data)} 条问答信息")
        return career_data
    
    def _rag_search(self, query: str, knowledge_base: List[Dict], top_k: int = 5) -> List[Dict]:
        """基于RAG的语义搜索"""
        relevant_docs = []
        
        for doc in knowledge_base:
            score = 0
            query_words = set(query.lower().split())
            
            # 计算文档与查询的相关性分数
            if '职位名称' in doc and isinstance(doc['职位名称'], str):
                job_words = set(doc['职位名称'].lower().split())
                score += len(query_words & job_words) * 2
            
            if '技能要求' in doc and isinstance(doc['技能要求'], str):
                skill_words = set(doc['技能要求'].lower().split())
                score += len(query_words & skill_words) * 1.5
            
            if '岗位职责' in doc and isinstance(doc['岗位职责'], str):
                duty_words = set(doc['岗位职责'].lower().split())
                score += len(query_words & duty_words)
            
            if 'question' in doc and isinstance(doc['question'], str):
                question_words = set(doc['question'].lower().split())
                score += len(query_words & question_words) * 2
            
            if score > 0:
                relevant_docs.append((doc, score))
        
        # 按分数排序并返回top_k结果
        relevant_docs.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, score in relevant_docs[:top_k]]
    
    def _classify_query(self, query: str) -> str:
        """分类用户查询类型"""
        career_keywords = ['职业规划', '发展方向', '转行', '职业选择', '未来规划']
        job_keywords = ['岗位', '职位', '工作', '招聘', '薪资', '公司']
        skill_keywords = ['技能', '学习', '面试', '简历', '求职', '经验']
        
        query_lower = query.lower()
        
        if any(keyword in query_lower for keyword in career_keywords):
            return 'career_planning'
        elif any(keyword in query_lower for keyword in job_keywords):
            return 'job_recommendation'
        elif any(keyword in query_lower for keyword in skill_keywords):
            return 'skill_guidance'
        else:
            return 'general'
    
    def _generate_response(self, query: str, query_type: str, relevant_docs: List[Dict]) -> str:
        """生成回答"""
        # 基于查询类型和相关信息生成回答
        if query_type == 'career_planning':
            if '转行' in query:
                return self.response_templates['career_planning']['转行']
            elif '职业规划' in query or '发展路径' in query:
                return self.response_templates['career_planning']['发展路径']
            else:
                return self.response_templates['career_planning']['职业规划']
        
        elif query_type == 'job_recommendation':
            if '算法' in query:
                return self.response_templates['job_recommendation']['算法工程师']
            elif 'python' in query.lower():
                return self.response_templates['job_recommendation']['Python开发']
            elif '数据' in query:
                return self.response_templates['job_recommendation']['数据科学家']
            else:
                # 基于知识库生成回答
                if relevant_docs:
                    job_info = relevant_docs[0]
                    return f"根据您的查询，我找到以下相关岗位信息：\n\n职位：{job_info.get('职位名称', '未知')}\n公司：{job_info.get('公司名称', '未知')}\n地点：{job_info.get('工作地点', '未知')}\n薪资：{job_info.get('薪资范围', '面议')}\n要求：{job_info.get('技能要求', '暂无')}"
                else:
                    return "抱歉，没有找到相关的岗位信息。建议您尝试其他关键词或联系我们的客服。"
        
        elif query_type == 'skill_guidance':
            if '面试' in query:
                return self.response_templates['skill_guidance']['面试']
            elif '简历' in query:
                return self.response_templates['skill_guidance']['简历']
            elif '技能' in query:
                return self.response_templates['skill_guidance']['技能提升']
            else:
                return self.response_templates['skill_guidance']['技能提升']
        
        else:
            return "您好！我是求职辅导助手，可以为您提供职业规划、岗位推荐和求职技能辅导。请告诉我您具体需要什么帮助？"
    
    def chat(self, user_query: str, user_context: Dict = None) -> str:
        """主要的对话接口"""
        # 分类查询类型
        query_type = self._classify_query(user_query)
        
        # 根据查询类型获取相关知识
        relevant_docs = []
        if query_type == 'job_recommendation':
            relevant_docs = self._rag_search(user_query, self.job_knowledge_base)
        elif query_type == 'skill_guidance':
            relevant_docs = self._rag_search(user_query, self.career_knowledge_base)
        
        # 生成回答
        response = self._generate_response(user_query, query_type, relevant_docs)
        return response
    
    def get_job_recommendations(self, user_profile: Dict) -> List[Dict]:
        """获取岗位推荐"""
        # 构建查询
        skills = user_profile.get('skills', [])
        experience = user_profile.get('experience', '')
        location = user_profile.get('location', '')
        
        query = f"{' '.join(skills)} {experience} {location}"
        
        # 从知识库搜索
        relevant_jobs = self._rag_search(query, self.job_knowledge_base, top_k=10)
        
        return relevant_jobs[:10]
    
    def get_career_advice(self, topic: str) -> str:
        """获取求职建议"""
        # 从知识库搜索
        relevant_advice = self._rag_search(topic, self.career_knowledge_base, top_k=3)
        
        # 基于主题生成建议
        if '简历' in topic:
            return self.response_templates['skill_guidance']['简历']
        elif '面试' in topic:
            return self.response_templates['skill_guidance']['面试']
        elif '技能' in topic:
            return self.response_templates['skill_guidance']['技能提升']
        else:
            return f"关于{topic}的建议：\n\n1. 系统学习相关知识\n2. 实践项目经验\n3. 持续关注行业动态\n4. 建立专业人脉\n5. 保持学习热情"

def test_agent():
    """测试agent功能"""
    print("🚀 测试求职辅导Agent功能")
    print("=" * 60)
    
    # 初始化agent
    agent = TestCareerAgent()
    
    # 测试问题
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
    
    # 测试岗位推荐
    print("\n💼 测试岗位推荐功能")
    print("=" * 40)
    
    test_profile = {
        "skills": ["Python", "机器学习", "深度学习"],
        "experience": "1-3年",
        "location": "北京"
    }
    
    try:
        recommendations = agent.get_job_recommendations(test_profile)
        print(f"📋 推荐岗位数量: {len(recommendations)}")
        
        for i, job in enumerate(recommendations[:3], 1):
            print(f"\n{i}. {job.get('职位名称', '未知职位')}")
            print(f"   公司: {job.get('公司名称', '未知公司')}")
            print(f"   地点: {job.get('工作地点', '未知')}")
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    print("\n✅ 测试完成！")

if __name__ == "__main__":
    test_agent() 