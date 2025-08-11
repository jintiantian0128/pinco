import os
import json
import requests
import openai
from typing import List, Dict, Any, Optional
import glob
from pathlib import Path
import re
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CareerAgent:
    def __init__(self, api_key: str):
        """
        初始化求职辅导agent
        
        Args:
            api_key: OpenAI API密钥
        """
        self.api_key = api_key
        openai.api_key = api_key
        
        # 初始化知识库
        self.job_knowledge_base = self._load_job_knowledge()
        self.career_knowledge_base = self._load_career_knowledge()
        
        # 搜索API配置
        self.search_apis = {
            'boss': 'https://www.zhipin.com/api/search',
            'zhihu': 'https://www.zhihu.com/api/search',
            'xiaohongshu': 'https://www.xiaohongshu.com/api/search'
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
    
    def _search_jobs(self, query: str, location: str = None, job_type: str = None) -> List[Dict]:
        """
        搜索Boss招聘、猎聘等网站的岗位信息
        
        Args:
            query: 搜索关键词
            location: 工作地点
            job_type: 职位类型
            
        Returns:
            搜索结果列表
        """
        # 这里应该调用实际的搜索API
        # 由于API限制，这里返回模拟数据
        logger.info(f"搜索岗位: {query}, 地点: {location}, 类型: {job_type}")
        
        # 模拟搜索结果
        mock_results = [
            {
                "公司名称": "模拟公司",
                "职位名称": f"{query}工程师",
                "工作地点": location or "北京",
                "薪资范围": "15k-30k",
                "岗位职责": "负责相关技术开发工作",
                "技能要求": "Python, 机器学习, 深度学习",
                "source": "boss_search"
            }
        ]
        
        return mock_results
    
    def _search_career_advice(self, query: str) -> List[Dict]:
        """
        搜索知乎、小红书等网站的求职建议
        
        Args:
            query: 搜索关键词
            
        Returns:
            搜索结果列表
        """
        # 这里应该调用实际的搜索API
        # 由于API限制，这里返回模拟数据
        logger.info(f"搜索求职建议: {query}")
        
        # 模拟搜索结果
        mock_results = [
            {
                "question": f"如何{query}？",
                "answer": f"关于{query}的建议：1. 系统学习相关知识 2. 实践项目经验 3. 持续关注行业动态",
                "source": "zhihu_search"
            }
        ]
        
        return mock_results
    
    def _rag_search(self, query: str, knowledge_base: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        基于RAG的语义搜索
        
        Args:
            query: 查询内容
            knowledge_base: 知识库
            top_k: 返回结果数量
            
        Returns:
            相关文档列表
        """
        # 简单的关键词匹配（实际应用中应该使用向量数据库）
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
    
    def _call_llm(self, messages: List[Dict]) -> str:
        """
        调用大模型API
        
        Args:
            messages: 对话消息列表
            
        Returns:
            模型回复
        """
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"调用大模型失败: {e}")
            return "抱歉，我现在无法回答您的问题，请稍后再试。"
    
    def _classify_query(self, query: str) -> str:
        """
        分类用户查询类型
        
        Args:
            query: 用户查询
            
        Returns:
            查询类型: 'career_planning', 'job_recommendation', 'skill_guidance'
        """
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
    
    def chat(self, user_query: str, user_context: Dict = None) -> str:
        """
        主要的对话接口
        
        Args:
            user_query: 用户查询
            user_context: 用户上下文信息（如背景、经验等）
            
        Returns:
            Agent回复
        """
        # 分类查询类型
        query_type = self._classify_query(user_query)
        
        # 构建系统提示
        system_prompt = """你是一个专业的求职辅导顾问，具备以下能力：
1. 职业规划：帮助用户制定职业发展路径
2. 岗位推荐：基于用户背景推荐合适的岗位
3. 求职技能辅导：提供面试、简历、技能提升建议

请根据用户的问题提供专业、实用的建议。回答要具体、可操作，并考虑用户的实际情况。"""
        
        # 根据查询类型获取相关知识
        relevant_docs = []
        if query_type == 'job_recommendation':
            relevant_docs = self._rag_search(user_query, self.job_knowledge_base)
            if not relevant_docs:
                # 如果RAG知识库没有相关信息，调用搜索
                search_results = self._search_jobs(user_query)
                relevant_docs = search_results
                
        elif query_type == 'skill_guidance':
            relevant_docs = self._rag_search(user_query, self.career_knowledge_base)
            if not relevant_docs:
                # 如果RAG知识库没有相关信息，调用搜索
                search_results = self._search_career_advice(user_query)
                relevant_docs = search_results
        
        # 构建知识上下文
        knowledge_context = ""
        if relevant_docs:
            knowledge_context = "\n\n相关知识：\n"
            for i, doc in enumerate(relevant_docs[:3], 1):
                if '职位名称' in doc:
                    knowledge_context += f"{i}. 职位：{doc['职位名称']}\n"
                    knowledge_context += f"   公司：{doc.get('公司名称', '未知')}\n"
                    knowledge_context += f"   地点：{doc.get('工作地点', '未知')}\n"
                    knowledge_context += f"   薪资：{doc.get('薪资范围', '未知')}\n"
                    knowledge_context += f"   要求：{doc.get('技能要求', '未知')}\n"
                elif 'question' in doc:
                    knowledge_context += f"{i}. 问题：{doc['question']}\n"
                    if 'answers' in doc and doc['answers']:
                        knowledge_context += f"   回答：{doc['answers'][0][:200]}...\n"
        
        # 构建用户上下文
        user_context_str = ""
        if user_context:
            user_context_str = f"\n用户背景：{json.dumps(user_context, ensure_ascii=False)}"
        
        # 构建完整提示
        full_prompt = f"{system_prompt}{knowledge_context}{user_context_str}\n\n用户问题：{user_query}\n\n请提供专业的建议："
        
        # 调用大模型
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{knowledge_context}{user_context_str}\n\n用户问题：{user_query}"}
        ]
        
        response = self._call_llm(messages)
        return response
    
    def get_job_recommendations(self, user_profile: Dict) -> List[Dict]:
        """
        获取岗位推荐
        
        Args:
            user_profile: 用户档案，包含技能、经验、期望等信息
            
        Returns:
            推荐岗位列表
        """
        # 构建查询
        skills = user_profile.get('skills', [])
        experience = user_profile.get('experience', '')
        location = user_profile.get('location', '')
        
        query = f"{' '.join(skills)} {experience} {location}"
        
        # 从知识库搜索
        relevant_jobs = self._rag_search(query, self.job_knowledge_base, top_k=10)
        
        # 如果知识库结果不足，补充搜索结果
        if len(relevant_jobs) < 5:
            search_results = self._search_jobs(query, location)
            relevant_jobs.extend(search_results)
        
        return relevant_jobs[:10]
    
    def get_career_advice(self, topic: str) -> str:
        """
        获取求职建议
        
        Args:
            topic: 建议主题
            
        Returns:
            建议内容
        """
        # 从知识库搜索
        relevant_advice = self._rag_search(topic, self.career_knowledge_base, top_k=3)
        
        # 如果知识库没有相关信息，搜索网络
        if not relevant_advice:
            search_results = self._search_career_advice(topic)
            relevant_advice = search_results
        
        # 构建建议内容
        advice_content = f"关于{topic}的建议：\n\n"
        
        for i, advice in enumerate(relevant_advice, 1):
            if 'answers' in advice and advice['answers']:
                advice_content += f"{i}. {advice['answers'][0][:300]}...\n\n"
            elif 'answer' in advice:
                advice_content += f"{i}. {advice['answer']}\n\n"
        
        return advice_content

def main():
    """主函数 - 演示agent使用"""
    # 初始化agent
    api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
    agent = CareerAgent(api_key)
    
    print("=== 求职辅导Agent ===\n")
    print("我可以帮助您进行：")
    print("1. 职业规划咨询")
    print("2. 岗位推荐")
    print("3. 求职技能辅导")
    print("4. 一般问答")
    print("\n请输入您的问题（输入'quit'退出）：")
    
    while True:
        user_input = input("\n您: ").strip()
        
        if user_input.lower() in ['quit', 'exit', '退出']:
            print("感谢使用求职辅导Agent，祝您求职顺利！")
            break
        
        if not user_input:
            continue
        
        try:
            response = agent.chat(user_input)
            print(f"\nAgent: {response}")
        except Exception as e:
            print(f"\nAgent: 抱歉，处理您的问题时出现了错误：{e}")

if __name__ == "__main__":
    main() 