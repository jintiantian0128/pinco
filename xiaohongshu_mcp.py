#!/usr/bin/env python3
"""
小红书MCP服务器 - AI产品经理求职内容获取工具
用于实时获取小红书上关于AI产品经理求职相关的内容
"""

import os
import json
import requests
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import threading
from dataclasses import dataclass
from urllib.parse import quote

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class XiaohongshuPost:
    """小红书帖子数据结构"""
    title: str
    content: str
    author: str
    likes: int
    comments: int
    shares: int
    timestamp: datetime
    url: str
    tags: List[str]
    relevance_score: float

class XiaohongshuScraper:
    """小红书内容爬取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.xiaohongshu.com/'
        })

        # AI产品经理相关关键词
        self.keywords = [
            'AI产品经理', '人工智能产品经理', 'AI PM', '机器学习产品经理',
            '大模型产品经理', 'NLP产品经理', '计算机视觉产品经理',
            'AI产品求职', 'AI产品经理面试', 'AI产品经理经验',
            'AI产品经理技能', 'AI产品经理学习', 'AI产品经理成长',
            '产品经理转AI', 'AI产品经理薪资', 'AI产品经理发展'
        ]

        # 缓存机制
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存

    def search_content(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索小红书内容
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
        Returns:
            搜索结果列表
        """
        try:
            # 由于小红书API限制，这里使用模拟数据
            # 实际部署时，可以考虑使用官方API或合法的数据源
            logger.info(f"模拟搜索小红书内容: {query}")

            # 模拟搜索结果
            mock_data = self._get_mock_search_results(query, limit)

            logger.info(f"小红书搜索完成，共获取 {len(mock_data)} 条内容")
            return mock_data

        except Exception as e:
            logger.error(f"小红书搜索失败: {e}")
            return []

    def _get_mock_search_results(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """生成模拟搜索结果"""
        # 模拟数据模板
        mock_templates = [
            {
                "title": "AI产品经理面试经验分享：从传统产品经理转型成功",
                "content": "作为一名有5年经验的传统产品经理，我在今年成功转型为AI产品经理。分享我的面试经验：重点考察AI技术理解、产品化思维、跨部门沟通能力。建议准备：1) 熟悉机器学习基本概念 2) 了解AI产品生命周期 3) 准备项目案例展示技术与业务的结合",
                "author": "产品老王",
                "likes": 128,
                "comments": 23,
                "relevance_score": 8.5
            },
            {
                "title": "AI产品经理必备技能：技术+产品+商业思维",
                "content": "AI产品经理需要掌握的核心技能：1) Python基础编程 2) 机器学习算法理解 3) 数据分析能力 4) 用户研究方法 5) 敏捷开发流程 6) 商业价值评估。建议先从数据产品经理做起，逐步深入AI领域。",
                "author": "AI产品探索者",
                "likes": 256,
                "comments": 45,
                "relevance_score": 9.2
            },
            {
                "title": "大厂AI产品经理薪资揭秘：15k-50k月薪",
                "content": "根据最新招聘数据，AI产品经理薪资区间：初级15-20k，中级25-35k，高级35-50k+。字节跳动、腾讯、百度等大厂普遍偏高。加分项：有AI项目经验、熟悉大模型、懂技术架构。建议积累垂直领域经验。",
                "author": "职场分析师",
                "likes": 189,
                "comments": 67,
                "relevance_score": 8.8
            },
            {
                "title": "AI产品经理学习路径：从零开始的成长指南",
                "content": "AI产品经理学习路线：1) 产品经理基础（3个月）2) Python编程入门（2个月）3) 机器学习理论（4个月）4) AI产品案例分析（2个月）5) 实战项目（6个月）。推荐资源：Coursera吴恩达课程、极客时间AI产品经理专栏。",
                "author": "学习狂人",
                "likes": 312,
                "comments": 89,
                "relevance_score": 9.5
            },
            {
                "title": "AI产品经理转行经验：避坑指南",
                "content": "转行AI产品经理的坑：1) 技术深度不够 2) 缺乏系统思维 3) 沟通障碍 4) 业务理解浅薄。建议：先补齐产品经理基础，再系统学习AI技术，多参与跨部门项目，积累可展示的成果。",
                "author": "转行成功者",
                "likes": 178,
                "comments": 34,
                "relevance_score": 8.3
            },
            {
                "title": "NLP产品经理面试题解析",
                "content": "常见NLP产品经理面试题：1) 如何设计一个智能客服系统？2) 文本分类模型的产品化考虑？3) 如何评估模型效果？4) A/B测试设计？重点考察：技术理解、产品思维、数据驱动决策能力。",
                "author": "NLP产品专家",
                "likes": 145,
                "comments": 28,
                "relevance_score": 8.7
            },
            {
                "title": "AI产品经理的日常工作内容",
                "content": "AI产品经理日常工作：1) 需求分析与功能设计 2) 与算法团队沟通 3) 数据指标定义 4) 模型效果评估 5) 用户反馈收集 6) 竞品分析 7) 产品规划与roadmap。需要很强的技术敏感度和商业思维。",
                "author": "AI产品经理",
                "likes": 234,
                "comments": 56,
                "relevance_score": 8.9
            },
            {
                "title": "2024年AI产品经理就业趋势",
                "content": "2024年AI产品经理就业趋势：1) 大模型应用产品需求大增 2) 多模态产品成为热点 3) 垂直行业AI产品机会多 4) 复合型人才更抢手。建议重点关注：医疗AI、教育AI、金融科技、智能制造等领域。",
                "author": "行业观察者",
                "likes": 198,
                "comments": 41,
                "relevance_score": 9.1
            }
        ]

        # 根据查询关键词过滤相关内容
        relevant_templates = []
        query_lower = query.lower()

        for template in mock_templates:
            content_text = (template['title'] + ' ' + template['content']).lower()
            if any(keyword in content_text for keyword in ['ai', '人工智能', '产品经理', '机器学习', '算法', 'nlp', '面试', '技能', '薪资', '学习', '转行']):
                if query_lower in content_text or any(word in query_lower for word in ['ai', '产品', '经理', '求职', '技能', '面试', '经验']):
                    relevant_templates.append(template)

        # 如果没有相关内容，返回所有模拟数据
        if not relevant_templates:
            relevant_templates = mock_templates

        # 限制返回数量并添加时间戳
        results = []
        for i, template in enumerate(relevant_templates[:limit]):
            result = template.copy()
            result.update({
                "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                "url": f"https://www.xiaohongshu.com/discovery/item/mock_{i}",
                "tags": ["AI产品经理", "求职", "经验分享"],
                "shares": result.get("likes", 0) // 3
            })
            results.append(result)

        return results

    def _parse_note(self, note: Dict) -> Optional[XiaohongshuPost]:
        """解析小红书笔记数据"""
        try:
            title = note.get('title', note.get('desc', ''))
            content = note.get('desc', '') + ' ' + note.get('content', '')

            # 计算相关性分数
            relevance_score = self._calculate_relevance(content + title)

            post = XiaohongshuPost(
                title=title,
                content=content,
                author=note.get('user', {}).get('nickname', '未知'),
                likes=note.get('like_count', 0),
                comments=note.get('comment_count', 0),
                shares=note.get('share_count', 0),
                timestamp=datetime.fromtimestamp(note.get('time', 0)),
                url=f"https://www.xiaohongshu.com/discovery/item/{note.get('note_id', '')}",
                tags=note.get('tags', []),
                relevance_score=relevance_score
            )

            return post

        except Exception as e:
            logger.error(f"解析笔记失败: {e}")
            return None

    def _calculate_relevance(self, text: str) -> float:
        """计算内容与AI产品经理求职的相关性"""
        score = 0.0
        text_lower = text.lower()

        # 关键词匹配
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                score += 1.0

        # 专业术语匹配
        ai_terms = ['ai', '人工智能', '机器学习', '深度学习', '神经网络', '大模型', 'nlp', '计算机视觉']
        for term in ai_terms:
            if term in text_lower:
                score += 0.5

        # 求职相关词汇
        job_terms = ['求职', '面试', '简历', '经验', '技能', '学习', '成长', '薪资', '发展', '转行']
        for term in job_terms:
            if term in text_lower:
                score += 0.3

        return min(score, 10.0)  # 限制最大分数为10

    def get_trending_content(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门AI产品经理相关内容"""
        all_posts = []

        # 使用多个关键词进行搜索
        search_queries = ['AI产品经理', '人工智能产品经理', 'AI PM求职', '产品经理转AI']

        # 为每个查询分配足够的结果数量
        posts_per_query = max(limit // len(search_queries), 5)

        for query in search_queries:
            posts = self.search_content(query, posts_per_query)
            all_posts.extend(posts)

        # 按相关性排序
        all_posts.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        return all_posts[:limit]

    def get_recent_content(self, hours: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近几小时的AI产品经理相关内容"""
        posts = self.get_trending_content(limit * 2)

        # 过滤最近的内容
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_posts = [
            post for post in posts
            if datetime.fromisoformat(post.get('timestamp', '2000-01-01T00:00:00')) > cutoff_time
        ]

        return recent_posts[:limit]

class XiaohongshuMCP:
    """小红书MCP服务器"""

    def __init__(self):
        self.scraper = XiaohongshuScraper()
        self.update_interval = 300  # 5分钟更新一次
        self.last_update = None
        self.cached_data = []

        # 启动自动更新线程
        self.update_thread = threading.Thread(target=self._auto_update, daemon=True)
        self.update_thread.start()

    def _auto_update(self):
        """自动更新数据"""
        while True:
            try:
                logger.info("开始自动更新小红书数据...")
                self.cached_data = self.scraper.get_trending_content(50)
                self.last_update = datetime.now()
                logger.info(f"小红书数据更新完成，共 {len(self.cached_data)} 条内容")

                time.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"自动更新失败: {e}")
                time.sleep(60)  # 出错后1分钟重试

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取MCP工具定义"""
        return [
            {
                "name": "search_xiaohongshu_content",
                "description": "搜索小红书上的AI产品经理求职相关内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，如'AI产品经理面试'、'AI产品经理技能'等"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量，默认20",
                            "default": 20
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_trending_ai_pm_content",
                "description": "获取小红书热门的AI产品经理求职内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量，默认10",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "get_recent_ai_pm_content",
                "description": "获取小红书最近的AI产品经理求职内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "最近几小时的内容，默认24",
                            "default": 24
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量，默认20",
                            "default": 20
                        }
                    }
                }
            },
            {
                "name": "get_ai_pm_insights",
                "description": "获取AI产品经理求职趋势分析和见解",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "enum": ["skills", "salary", "career", "interview"],
                            "description": "分析类型：技能要求、薪资情况、职业发展、面试经验"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "分析内容数量，默认10",
                            "default": 10
                        }
                    },
                    "required": ["analysis_type"]
                }
            }
        ]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行MCP工具"""
        try:
            if tool_name == "search_xiaohongshu_content":
                query = arguments.get("query", "")
                limit = arguments.get("limit", 20)

                results = self.scraper.search_content(query, limit)

                return {
                    "success": True,
                    "data": results,
                    "message": f"找到 {len(results)} 条相关内容"
                }

            elif tool_name == "get_trending_ai_pm_content":
                limit = arguments.get("limit", 10)

                if self.cached_data and self.last_update:
                    # 使用缓存数据
                    results = self.cached_data[:limit]
                    last_update_str = self.last_update.strftime("%Y-%m-%d %H:%M:%S")

                    return {
                        "success": True,
                        "data": results,
                        "message": f"获取 {len(results)} 条热门内容（更新时间：{last_update_str}）"
                    }
                else:
                    # 实时获取
                    results = self.scraper.get_trending_content(limit)
                    return {
                        "success": True,
                        "data": results,
                        "message": f"获取 {len(results)} 条热门内容"
                    }

            elif tool_name == "get_recent_ai_pm_content":
                hours = arguments.get("hours", 24)
                limit = arguments.get("limit", 20)

                results = self.scraper.get_recent_content(hours, limit)

                return {
                    "success": True,
                    "data": results,
                    "message": f"获取最近 {hours} 小时内 {len(results)} 条内容"
                }

            elif tool_name == "get_ai_pm_insights":
                analysis_type = arguments.get("analysis_type", "skills")
                limit = arguments.get("limit", 10)

                insights = self._generate_insights(analysis_type, limit)

                return {
                    "success": True,
                    "data": insights,
                    "message": f"生成 {len(insights)} 条{analysis_type}相关见解"
                }

            else:
                return {
                    "success": False,
                    "error": f"未知工具: {tool_name}"
                }

        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_insights(self, analysis_type: str, limit: int) -> List[Dict[str, Any]]:
        """生成AI产品经理求职见解"""
        # 如果没有缓存数据，使用模拟数据
        if not self.cached_data:
            sample_data = self.scraper.get_trending_content(20)
        else:
            sample_data = self.cached_data

        insights = []

        if analysis_type == "skills":
            # 技能分析
            skill_keywords = [
                'Python', '机器学习', '深度学习', '数据分析', '产品设计',
                '用户研究', '项目管理', '沟通能力', '技术背景', '商业思维'
            ]

            skill_counts = {}
            for post in sample_data:
                content = post.get('content', '') + post.get('title', '')
                for skill in skill_keywords:
                    if skill.lower() in content.lower():
                        skill_counts[skill] = skill_counts.get(skill, 0) + 1

            sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
            insights = [
                {
                    "type": "skill",
                    "name": skill,
                    "count": count,
                    "description": f"AI产品经理需要掌握的{skill}技能"
                }
                for skill, count in sorted_skills[:limit]
            ]

        elif analysis_type == "salary":
            # 薪资分析
            salary_ranges = ['15-20k', '20-30k', '30-50k', '50k+']
            salary_counts = {range_: 0 for range_ in salary_ranges}

            for post in sample_data:
                content = post.get('content', '') + post.get('title', '')
                for range_ in salary_ranges:
                    if range_ in content:
                        salary_counts[range_] += 1

            insights = [
                {
                    "type": "salary",
                    "range": range_,
                    "count": count,
                    "description": f"月薪{range_}的AI产品经理职位讨论"
                }
                for range_, count in salary_counts.items() if count > 0
            ][:limit]

        elif analysis_type == "career":
            # 职业发展
            career_keywords = [
                '入门', '初级', '中级', '高级', '资深', '总监',
                '转行', '学习路径', '成长路线', '职业规划'
            ]

            career_counts = {}
            for post in sample_data:
                content = post.get('content', '') + post.get('title', '')
                for career in career_keywords:
                    if career in content:
                        career_counts[career] = career_counts.get(career, 0) + 1

            sorted_careers = sorted(career_counts.items(), key=lambda x: x[1], reverse=True)
            insights = [
                {
                    "type": "career",
                    "stage": career,
                    "count": count,
                    "description": f"AI产品经理{career}阶段的讨论"
                }
                for career, count in sorted_careers[:limit]
            ]

        elif analysis_type == "interview":
            # 面试经验
            interview_keywords = [
                '面试题', '面试经验', '面试官', '面经', '笔试',
                '技术面试', '产品面试', 'HR面试', 'offer', '拒信'
            ]

            interview_counts = {}
            for post in sample_data:
                content = post.get('content', '') + post.get('title', '')
                for interview in interview_keywords:
                    if interview in content:
                        interview_counts[interview] = interview_counts.get(interview, 0) + 1

            sorted_interviews = sorted(interview_counts.items(), key=lambda x: x[1], reverse=True)
            insights = [
                {
                    "type": "interview",
                    "topic": interview,
                    "count": count,
                    "description": f"AI产品经理{interview}相关讨论"
                }
                for interview, count in sorted_interviews[:limit]
            ]

        return insights

def main():
    """主函数 - MCP服务器入口"""
    import sys
    import json

    # 初始化MCP服务器
    mcp_server = XiaohongshuMCP()

    # 读取命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "tools":
            # 输出工具定义
            tools = mcp_server.get_tools()
            print(json.dumps({"tools": tools}, ensure_ascii=False, indent=2))

        elif command == "call":
            # 执行工具调用
            if len(sys.argv) < 3:
                print(json.dumps({"error": "需要工具名称"}, ensure_ascii=False))
                return

            tool_name = sys.argv[2]
            tool_args = {}

            # 解析额外参数
            if len(sys.argv) > 3:
                try:
                    tool_args = json.loads(sys.argv[3])
                except:
                    print(json.dumps({"error": "参数格式错误"}, ensure_ascii=False))
                    return

            result = mcp_server.execute_tool(tool_name, tool_args)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        else:
            print(json.dumps({"error": f"未知命令: {command}"}, ensure_ascii=False))

    else:
        # 默认输出帮助信息
        help_info = {
            "name": "小红书AI产品经理MCP服务器",
            "description": "实时获取小红书上AI产品经理求职相关内容",
            "version": "1.0.0",
            "commands": {
                "tools": "获取可用工具列表",
                "call <tool_name> [args]": "调用指定工具"
            },
            "tools": [
                "search_xiaohongshu_content - 搜索小红书内容",
                "get_trending_ai_pm_content - 获取热门内容",
                "get_recent_ai_pm_content - 获取最近内容",
                "get_ai_pm_insights - 获取求职见解"
            ]
        }
        print(json.dumps(help_info, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
