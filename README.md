# AI产品经理求职助手

这是一个专门为AI产品经理求职者设计的工具集合，帮助您在上海寻找AI产品经理相关的工作机会。

## 功能特性

- 🤖 **AI产品经理职位搜索**：智能搜索AI产品经理相关职位
- 📊 **职位数据分析**：分析职位要求、技能需求等
- 💡 **求职建议**：提供针对性的求职指导
- 🔍 **多平台数据**：整合BOSS直聘等平台的招聘信息

## 项目结构

```
pinco_cursor/
├── ai_product_manager_search.py    # AI产品经理职位搜索工具
├── boss招聘信息/                    # BOSS直聘招聘数据
│   ├── 上海/                       # 上海地区职位数据
│   ├── 北京/                       # 北京地区职位数据
│   ├── 深圳/                       # 深圳地区职位数据
│   └── 杭州/                       # 杭州地区职位数据
├── 知乎问答/                       # 知乎相关问答数据
├── templates/                      # Web界面模板
├── requirements.txt               # Python依赖包
└── README.md                      # 项目说明文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行AI产品经理职位搜索

```bash
python3 ai_product_manager_search.py
```

### 3. 使用Web界面

```bash
python3 web_interface.py
```

## 主要工具

### AI产品经理职位搜索工具

`ai_product_manager_search.py` 是一个专门用于搜索AI产品经理相关职位的工具，具有以下功能：

- 智能关键词匹配
- 多维度职位筛选
- 详细的职位信息展示
- 个性化的求职建议

### 使用方法

```python
from ai_product_manager_search import AIProductManagerJobSearch

# 创建搜索实例
searcher = AIProductManagerJobSearch()

# 搜索AI产品经理职位
jobs = searcher.search_ai_product_manager_jobs()

# 显示搜索结果
searcher.display_jobs(jobs)
```

## 数据来源

- **BOSS直聘**：招聘信息数据
- **知乎**：AI产品经理相关问答

## 技术栈

- **Python 3.8+**
- **JSON数据处理**
- **正则表达式**
- **Web界面（可选）**

## 贡献指南

欢迎提交Issue和Pull Request来改进这个项目！

## 许可证

MIT License

## 联系方式

- 作者：jintiantian0128
- 邮箱：jtt_0128@163.com

---

**注意**：本项目仅用于学习和研究目的，请遵守相关平台的使用条款。
