#!/usr/bin/env python3
"""
牛客网 MCP 服务器
用于搜索和爬取牛客网上的AI产品经理相关面试和题库数据
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NowcoderMCP:
    def __init__(self):
        self.base_url = "https://www.nowcoder.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def search_content(self, keyword: str, content_type: str = "all") -> Dict[str, Any]:
        """
        搜索牛客网内容
        
        Args:
            keyword: 搜索关键词
            content_type: 内容类型 (all, interview, question)
            
        Returns:
            搜索结果字典
        """
        try:
            # 构建搜索URL
            encoded_keyword = quote(keyword)
            search_url = f"{self.base_url}/search/all?query={encoded_keyword}&type={content_type}&searchType=%E9%A1%B9%E9%83%A8%E5%AF%BC%E8%88%AA%E6%A0%8F"
            
            logger.info(f"正在搜索: {search_url}")
            
            # 发送请求
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取搜索结果
            results = []
            
            # 查找面试经验 - 尝试多种选择器
            interview_items = []
            
            # 尝试不同的选择器来查找搜索结果
            selectors = [
                'div.search-item',
                'div.search-result-item', 
                'div.result-item',
                'div[class*="search"]',
                'div[class*="result"]',
                'article',
                'div.item'
            ]
            
            for selector in selectors:
                items = soup.select(selector)
                if items:
                    interview_items = items
                    logger.info(f"使用选择器 '{selector}' 找到 {len(items)} 个结果")
                    break
            
            # 如果没有找到，尝试查找所有包含关键词的链接
            if not interview_items:
                all_links = soup.find_all('a', href=True)
                keyword_links = [link for link in all_links if keyword in link.get_text()]
                logger.info(f"通过链接查找找到 {len(keyword_links)} 个相关结果")
                
                # 将链接转换为搜索结果格式
                for link in keyword_links:
                    try:
                        title = link.get_text(strip=True)
                        href = link.get('href')
                        link_url = urljoin(self.base_url, href) if href else ""
                        
                        # 查找父元素获取更多信息
                        parent = link.parent
                        author = "匿名用户"
                        publish_time = ""
                        content = ""
                        
                        # 尝试从父元素或兄弟元素获取作者和时间信息
                        if parent:
                            # 查找作者信息
                            author_elem = parent.find('span', class_='author') or parent.find('div', class_='user-info')
                            if author_elem:
                                author = author_elem.get_text(strip=True)
                            
                            # 查找时间信息
                            time_elem = parent.find('span', class_='time') or parent.find('time')
                            if time_elem:
                                publish_time = time_elem.get_text(strip=True)
                            
                            # 查找内容摘要
                            content_elem = parent.find('div', class_='content') or parent.find('p')
                            if content_elem:
                                content = content_elem.get_text(strip=True)
                        
                        # 判断内容类型
                        item_type = "面试经验"
                        if "题库" in title or "真题" in title or "题目" in title:
                            item_type = "题库"
                        elif "面经" in title or "面试" in title:
                            item_type = "面试经验"
                        
                        result = {
                            "title": title,
                            "link": link_url,
                            "author": author,
                            "publish_time": publish_time,
                            "content": content[:200] + "..." if len(content) > 200 else content,
                            "likes": "0",
                            "comments": "0",
                            "type": item_type,
                            "relevance": self._calculate_relevance(keyword, title, content)
                        }
                        
                        results.append(result)
                        
                    except Exception as e:
                        logger.warning(f"解析链接结果时出错: {e}")
                        continue
            
            # 处理通过选择器找到的结果
            for item in interview_items:
                try:
                    # 提取标题 - 尝试多种方式
                    title = "无标题"
                    title_elem = item.find('h3') or item.find('h2') or item.find('h1') or item.find('a')
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    else:
                        # 如果没有找到标题元素，尝试从整个item中提取第一个有意义的文本
                        all_text = item.get_text(strip=True)
                        if all_text:
                            title = all_text.split('\n')[0][:100]  # 取第一行作为标题
                    
                    # 提取链接
                    link = ""
                    link_elem = item.find('a')
                    if link_elem:
                        href = link_elem.get('href', '')
                        link = urljoin(self.base_url, href) if href else ""
                    
                    # 提取作者信息 - 尝试多种选择器
                    author = "匿名用户"
                    author_selectors = [
                        'span.author', 'div.user-info', 'span.user-name', 
                        'div.author', 'span[class*="user"]', 'div[class*="user"]'
                    ]
                    for selector in author_selectors:
                        author_elem = item.select_one(selector)
                        if author_elem:
                            author = author_elem.get_text(strip=True)
                            break
                    
                    # 提取时间 - 尝试多种选择器
                    publish_time = ""
                    time_selectors = [
                        'span.time', 'time', 'span.date', 'div.time',
                        'span[class*="time"]', 'div[class*="time"]'
                    ]
                    for selector in time_selectors:
                        time_elem = item.select_one(selector)
                        if time_elem:
                            publish_time = time_elem.get_text(strip=True)
                            break
                    
                    # 提取内容摘要 - 尝试多种选择器
                    content = ""
                    content_selectors = [
                        'div.content', 'p', 'div.description', 'div.summary',
                        'div[class*="content"]', 'div[class*="desc"]'
                    ]
                    for selector in content_selectors:
                        content_elem = item.select_one(selector)
                        if content_elem:
                            content = content_elem.get_text(strip=True)
                            break
                    
                    # 如果没有找到内容，使用整个item的文本
                    if not content:
                        content = item.get_text(strip=True)
                        # 移除标题部分
                        if title in content:
                            content = content.replace(title, '').strip()
                    
                    # 提取点赞数和评论数
                    likes = "0"
                    comments = "0"
                    
                    # 查找包含数字的元素
                    all_spans = item.find_all('span')
                    for span in all_spans:
                        text = span.get_text(strip=True)
                        if '点赞' in text or '赞' in text:
                            # 提取数字
                            import re
                            numbers = re.findall(r'\d+', text)
                            if numbers:
                                likes = numbers[0]
                        elif '评论' in text or '回复' in text:
                            numbers = re.findall(r'\d+', text)
                            if numbers:
                                comments = numbers[0]
                    
                    # 判断内容类型
                    item_type = "面试经验"
                    if "题库" in title or "真题" in title or "题目" in title:
                        item_type = "题库"
                    elif "面经" in title or "面试" in title:
                        item_type = "面试经验"
                    elif "AI" in title and "产品" in title:
                        item_type = "AI产品经理"
                    
                    result = {
                        "title": title,
                        "link": link,
                        "author": author,
                        "publish_time": publish_time,
                        "content": content[:200] + "..." if len(content) > 200 else content,
                        "likes": likes,
                        "comments": comments,
                        "type": item_type,
                        "relevance": self._calculate_relevance(keyword, title, content)
                    }
                    
                    # 只添加有意义的搜索结果
                    if (title != "无标题" and 
                        len(title) > 3 and 
                        not any(skip in title.lower() for skip in ['123456789', '点击反馈'])):
                        results.append(result)
                    
                except Exception as e:
                    logger.warning(f"解析搜索结果项时出错: {e}")
                    continue
            
            # 按相关性排序
            results.sort(key=lambda x: x['relevance'], reverse=True)
            
            return {
                "success": True,
                "keyword": keyword,
                "total_count": len(results),
                "results": results,
                "search_url": search_url
            }
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "keyword": keyword,
                "results": []
            }
    
    def get_interview_experience(self, keyword: str) -> Dict[str, Any]:
        """
        获取面试经验
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            面试经验数据
        """
        return self.search_content(keyword, "interview")
    
    def get_question_bank(self, keyword: str) -> Dict[str, Any]:
        """
        获取题库内容
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            题库数据
        """
        return self.search_content(keyword, "question")
    
    def get_detailed_content(self, url: str) -> Dict[str, Any]:
        """
        获取详细内容页面
        
        Args:
            url: 内容页面URL
            
        Returns:
            详细内容数据
        """
        try:
            logger.info(f"正在获取详细内容: {url}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取标题
            title_elem = soup.find('h1') or soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "无标题"
            
            # 提取作者信息
            author_elem = soup.find('span', class_='author') or soup.find('div', class_='user-info')
            author = author_elem.get_text(strip=True) if author_elem else "匿名用户"
            
            # 提取发布时间
            time_elem = soup.find('span', class_='time') or soup.find('time')
            publish_time = time_elem.get_text(strip=True) if time_elem else ""
            
            # 提取正文内容
            content_elem = soup.find('div', class_='content') or soup.find('article') or soup.find('div', class_='post-content')
            content = content_elem.get_text(strip=True) if content_elem else ""
            
            # 提取点赞数
            like_elem = soup.find('span', class_='like-count') or soup.find('span', string=lambda x: '点赞' in str(x) if x else False)
            likes = like_elem.get_text(strip=True) if like_elem else "0"
            
            # 提取评论数
            comment_elem = soup.find('span', class_='comment-count') or soup.find('span', string=lambda x: '评论' in str(x) if x else False)
            comments = comment_elem.get_text(strip=True) if comment_elem else "0"
            
            # 提取标签
            tags = []
            tag_elems = soup.find_all('span', class_='tag') or soup.find_all('a', class_='tag')
            for tag_elem in tag_elems:
                tag_text = tag_elem.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
            
            return {
                "success": True,
                "url": url,
                "title": title,
                "author": author,
                "publish_time": publish_time,
                "content": content,
                "likes": likes,
                "comments": comments,
                "tags": tags
            }
            
        except Exception as e:
            logger.error(f"获取详细内容失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
    
    def get_ai_pm_insights(self) -> Dict[str, Any]:
        """
        获取AI产品经理相关洞察
        
        Returns:
            AI产品经理洞察数据
        """
        try:
            # 搜索AI产品经理相关内容
            search_results = self.search_content("AI产品经理")
            
            if not search_results.get("success"):
                return {
                    "success": False,
                    "error": "搜索失败",
                    "insights": []
                }
            
            insights = []
            
            # 分析面试经验
            interview_insights = {
                "type": "面试经验分析",
                "total_count": 0,
                "top_companies": [],
                "common_questions": [],
                "skill_requirements": []
            }
            
            # 分析题库
            question_insights = {
                "type": "题库分析",
                "total_count": 0,
                "question_types": [],
                "difficulty_distribution": []
            }
            
            for result in search_results.get("results", []):
                if result.get("type") == "面试经验":
                    interview_insights["total_count"] += 1
                    
                    # 提取公司信息
                    title = result.get("title", "")
                    if "美团" in title:
                        interview_insights["top_companies"].append("美团")
                    elif "百度" in title:
                        interview_insights["top_companies"].append("百度")
                    elif "阿里" in title or "阿里巴巴" in title:
                        interview_insights["top_companies"].append("阿里巴巴")
                    elif "腾讯" in title:
                        interview_insights["top_companies"].append("腾讯")
                    elif "字节" in title:
                        interview_insights["top_companies"].append("字节跳动")
                    
                    # 提取常见问题
                    content = result.get("content", "")
                    if "自我介绍" in content:
                        interview_insights["common_questions"].append("自我介绍")
                    if "项目经历" in content:
                        interview_insights["common_questions"].append("项目经历")
                    if "技术理解" in content:
                        interview_insights["common_questions"].append("技术理解")
                    if "产品设计" in content:
                        interview_insights["common_questions"].append("产品设计")
                    if "数据分析" in content:
                        interview_insights["common_questions"].append("数据分析")
                    
                    # 提取技能要求
                    if "AI" in content or "人工智能" in content:
                        interview_insights["skill_requirements"].append("AI技术理解")
                    if "产品" in content:
                        interview_insights["skill_requirements"].append("产品思维")
                    if "数据" in content:
                        interview_insights["skill_requirements"].append("数据分析")
                    if "沟通" in content:
                        interview_insights["skill_requirements"].append("沟通能力")
                
                elif result.get("type") == "题库":
                    question_insights["total_count"] += 1
                    
                    title = result.get("title", "")
                    if "算法" in title:
                        question_insights["question_types"].append("算法题")
                    elif "系统设计" in title:
                        question_insights["question_types"].append("系统设计")
                    elif "产品设计" in title:
                        question_insights["question_types"].append("产品设计")
                    elif "数据分析" in title:
                        question_insights["question_types"].append("数据分析")
            
            # 去重和统计
            interview_insights["top_companies"] = list(set(interview_insights["top_companies"]))
            interview_insights["common_questions"] = list(set(interview_insights["common_questions"]))
            interview_insights["skill_requirements"] = list(set(interview_insights["skill_requirements"]))
            question_insights["question_types"] = list(set(question_insights["question_types"]))
            
            insights.append(interview_insights)
            insights.append(question_insights)
            
            return {
                "success": True,
                "search_results": search_results,
                "insights": insights
            }
            
        except Exception as e:
            logger.error(f"生成洞察失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "insights": []
            }
    
    def _calculate_relevance(self, keyword: str, title: str, content: str) -> float:
        """
        计算相关性分数
        
        Args:
            keyword: 搜索关键词
            title: 标题
            content: 内容
            
        Returns:
            相关性分数 (0-1)
        """
        relevance = 0.0
        
        # 标题匹配权重更高
        if keyword.lower() in title.lower():
            relevance += 0.5
        
        # 内容匹配
        if keyword.lower() in content.lower():
            relevance += 0.3
        
        # 关键词匹配
        keywords = keyword.split()
        for kw in keywords:
            if kw.lower() in title.lower():
                relevance += 0.1
            if kw.lower() in content.lower():
                relevance += 0.05
        
        return min(relevance, 1.0)

if __name__ == "__main__":
    # 测试代码
    nowcoder = NowcoderMCP()
    
    print("测试牛客网MCP功能")
    
    # 测试搜索功能
    print("\n1. 测试搜索AI产品经理相关内容...")
    search_result = nowcoder.search_content("AI产品经理")
    
    if search_result.get("success"):
        print(f"搜索成功，找到 {search_result.get('total_count', 0)} 条结果")
        
        # 显示前3条结果
        for i, result in enumerate(search_result.get("results", [])[:3], 1):
            print(f"\n结果 {i}:")
            print(f"  标题: {result.get('title', '无标题')}")
            print(f"  作者: {result.get('author', '匿名')}")
            print(f"  类型: {result.get('type', '未知')}")
            print(f"  链接: {result.get('link', '无链接')}")
            print(f"  内容: {result.get('content', '无内容')[:100]}...")
    else:
        print(f"搜索失败: {search_result.get('error', '未知错误')}")
    
    # 测试洞察分析
    print("\n2. 测试生成洞察分析...")
    insights_result = nowcoder.get_ai_pm_insights()
    
    if insights_result.get("success"):
        print("洞察分析生成成功")
        for insight in insights_result.get("insights", []):
            print(f"\n{insight.get('type', '未知类型')}:")
            if "total_count" in insight:
                print(f"  总数: {insight['total_count']}")
            if "top_companies" in insight and insight["top_companies"]:
                print(f"  热门公司: {', '.join(insight['top_companies'])}")
            if "common_questions" in insight and insight["common_questions"]:
                print(f"  常见问题: {', '.join(insight['common_questions'])}")
    else:
        print(f"洞察分析失败: {insights_result.get('error', '未知错误')}")
