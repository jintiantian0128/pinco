#!/usr/bin/env python3
"""
小红书MCP服务器使用示例
展示如何使用小红书MCP服务器获取AI产品经理求职相关内容
"""

import json
import subprocess
import sys
from typing import Dict, Any, List

class XiaohongshuMCPClient:
    """小红书MCP服务器客户端"""

    def __init__(self):
        self.server_script = "xiaohongshu_mcp.py"

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用MCP工具"""
        try:
            cmd = [
                "python3",
                self.server_script,
                "call",
                tool_name,
                json.dumps(arguments, ensure_ascii=False)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30
            )

            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                return {
                    "success": False,
                    "error": result.stderr
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def search_content(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """搜索小红书内容"""
        return self._call_tool("search_xiaohongshu_content", {
            "query": query,
            "limit": limit
        })

    def get_trending_content(self, limit: int = 10) -> Dict[str, Any]:
        """获取热门内容"""
        return self._call_tool("get_trending_ai_pm_content", {
            "limit": limit
        })

    def get_recent_content(self, hours: int = 24, limit: int = 20) -> Dict[str, Any]:
        """获取最近内容"""
        return self._call_tool("get_recent_ai_pm_content", {
            "hours": hours,
            "limit": limit
        })

    def get_insights(self, analysis_type: str, limit: int = 10) -> Dict[str, Any]:
        """获取求职见解"""
        return self._call_tool("get_ai_pm_insights", {
            "analysis_type": analysis_type,
            "limit": limit
        })

def print_result(title: str, result: Dict[str, Any]):
    """打印结果"""
    print(f"\n{'='*50}")
    print(f"📊 {title}")
    print(f"{'='*50}")

    if result.get("success"):
        data = result.get("data", [])
        message = result.get("message", "")
        print(f"✅ {message}")

        if isinstance(data, list) and data:
            for i, item in enumerate(data[:5], 1):  # 只显示前5条
                if 'type' in item and item['type'] == 'skill':
                    print(f"\n{i}. {item.get('name', '无名称')}")
                    print(f"   技能: {item.get('name', '')}")
                    print(f"   提及次数: {item.get('count', 0)}")
                    print(f"   描述: {item.get('description', '')}")
                elif 'type' in item and item['type'] == 'salary':
                    print(f"\n{i}. {item.get('range', '无范围')}")
                    print(f"   薪资范围: {item.get('range', '')}")
                    print(f"   提及次数: {item.get('count', 0)}")
                    print(f"   描述: {item.get('description', '')}")
                elif 'type' in item and item['type'] == 'career':
                    print(f"\n{i}. {item.get('stage', '无阶段')}")
                    print(f"   职业阶段: {item.get('stage', '')}")
                    print(f"   提及次数: {item.get('count', 0)}")
                    print(f"   描述: {item.get('description', '')}")
                elif 'type' in item and item['type'] == 'interview':
                    print(f"\n{i}. {item.get('topic', '无主题')}")
                    print(f"   面试主题: {item.get('topic', '')}")
                    print(f"   提及次数: {item.get('count', 0)}")
                    print(f"   描述: {item.get('description', '')}")
                else:
                    print(f"\n{i}. {item.get('title', '无标题')}")
                    if 'content' in item:
                        content = item['content'][:100] + "..." if len(item['content']) > 100 else item['content']
                        print(f"   内容: {content}")
                    if 'relevance_score' in item:
                        print(f"   相关度: {item['relevance_score']:.2f}")
                    if 'author' in item:
                        print(f"   作者: {item['author']}")
                    if 'likes' in item:
                        print(f"   点赞: {item['likes']}")
        else:
            print("   无数据")
    else:
        print(f"❌ 错误: {result.get('error', '未知错误')}")

def main():
    """主函数"""
    client = XiaohongshuMCPClient()

    print("🚀 小红书AI产品经理MCP服务器使用示例")
    print("这个示例展示了如何获取AI产品经理求职相关内容\n")

    # 示例1: 搜索特定内容
    print("示例1: 搜索AI产品经理面试经验")
    result1 = client.search_content("AI产品经理面试", 5)
    print_result("AI产品经理面试搜索结果", result1)

    # 示例2: 获取热门内容
    print("\n示例2: 获取热门AI产品经理内容")
    result2 = client.get_trending_content(5)
    print_result("热门AI产品经理内容", result2)

    # 示例3: 获取最近内容
    print("\n示例3: 获取最近24小时的内容")
    result3 = client.get_recent_content(24, 5)
    print_result("最近24小时AI产品经理内容", result3)

    # 示例4: 获取技能分析
    print("\n示例4: AI产品经理技能分析")
    result4 = client.get_insights("skills", 8)
    print_result("AI产品经理技能分析", result4)

    # 示例5: 获取薪资分析
    print("\n示例5: AI产品经理薪资分析")
    result5 = client.get_insights("salary", 5)
    print_result("AI产品经理薪资分析", result5)

    # 示例6: 获取职业发展分析
    print("\n示例6: AI产品经理职业发展分析")
    result6 = client.get_insights("career", 6)
    print_result("AI产品经理职业发展分析", result6)

    # 示例7: 获取面试经验分析
    print("\n示例7: AI产品经理面试经验分析")
    result7 = client.get_insights("interview", 8)
    print_result("AI产品经理面试经验分析", result7)

    print(f"\n{'='*50}")
    print("🎉 示例演示完成！")
    print("您可以通过以下方式使用MCP服务器：")
    print("1. 直接运行: python xiaohongshu_mcp.py")
    print("2. 查看工具列表: python xiaohongshu_mcp.py tools")
    print("3. 调用工具: python xiaohongshu_mcp.py call <tool_name> <args>")
    print("4. 在AI应用中集成此MCP服务器")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
