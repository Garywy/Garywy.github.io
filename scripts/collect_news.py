import feedparser
import datetime
from slugify import slugify
import os
from html.parser import HTMLParser
import re

# --- 配置部分 ---
# !!! 替换为您自建 RSSHub 实例的实际 IP 和端口 !!!
YOUR_RSSHUB_BASE_URL = 'http://8.219.233.29:1200' # 示例，请替换为你的实际地址

# 定义要抓取的新闻源列表，按国家和新闻名称分类
NEWS_SOURCES = {
    "中国": [
        {"name": "新华社", "url": f"{YOUR_RSSHUB_BASE_URL}/news/xhsxw"},
        {"name": "第一财经", "url": f"{YOUR_RSSHUB_BASE_URL}/yicai/headline"},
    ],
    "日本": [
        {"name": "NHK", "url": f"{YOUR_RSSHUB_BASE_URL}/nhk/news/zh"}, 
    ],
    "欧美": [
        {"name": "BBC", "url": f"{YOUR_RSSHUB_BASE_URL}/bbc/world-asia"},
        # 如果需要纽约时报英文，且你的RSSHub支持，可以添加：
        # {"name": "纽约时报 (英文)", "url": f"{YOUR_RSSHUB_BASE_URL}/nytimes/homepage"},
    ],
}

# Hugo 整合文件输出目录和文件名配置
OUTPUT_SUMMARY_DIRS = [
    'content/Chinese/posts/news',  
    'content/English/posts/news'
]
# 文件名格式：daily-news-summary-YYYYMMDD.md
# 每天生成一个新文件，当天多次运行会覆盖当天文件
SUMMARY_FILENAME_PREFIX = 'daily-news-summary'

# Hugo Front Matter 配置
FRONT_MATTER_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S%z'

# 用于HTML内容简单清理的辅助类
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

def strip_html_tags(html_content):
    """简单的HTML标签移除函数"""
    if isinstance(html_content, str) and '<' in html_content and '>' in html_content:
        try:
            s = MLStripper()
            s.feed(html_content)
            return s.get_data()
        except Exception:
            return re.sub(r'<[^>]+>', '', html_content)
    return html_content

def fetch_news_data():
    all_news_data = {}

    for country, sources in NEWS_SOURCES.items():
        all_news_data[country] = []
        for source in sources:
            news_name = source["name"]
            feed_url = source["url"]
            
            num_to_fetch = 1 if news_name == "央视新闻" else 10
            
            print(f"-> 正在获取 {country} - {news_name} (最新 {num_to_fetch} 条)")

            try:
                feed = feedparser.parse(feed_url)

                if feed.bozo:
                    print(f"⚠️ 警告: 解析 {news_name} ({feed_url}) 时出现问题: {feed.bozo_exception}")
                    
                if not feed.entries:
                    print(f"没有找到 {news_name} 的新闻条目。")
                    continue

                latest_entries = feed.entries[:num_to_fetch] 
                if not latest_entries:
                    print(f"{news_name} 没有最新的新闻条目。")
                    continue

                source_news_items = []
                for entry in latest_entries:
                    try:
                        title = entry.get('title', '无标题')
                        link = entry.get('link', '无链接')

                        published_str = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
                        if 'published_parsed' in entry and entry.published_parsed:
                            try:
                                pub_date_utc = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)
                                published_str = pub_date_utc.isoformat(timespec='seconds')
                            except Exception as date_e:
                                print(f"警告: 新闻 '{title}' 的发布日期解析失败: {date_e}，使用当前UTC时间。")
                        else:
                            print(f"警告: 新闻 '{title}' 没有发布日期信息，使用当前UTC时间。")

                        content = ""
                        if 'content' in entry and entry.content:
                            for c in entry.content:
                                if c.type == 'text/html':
                                    content = c.value
                                    break
                                elif c.type == 'text/plain':
                                    content = c.value
                                    break
                        
                        if not content and 'summary' in entry and entry.summary:
                            content = entry.summary
                        elif not content and 'description' in entry and entry.description:
                            content = entry.description
                        
                        if not content:
                            content = "此新闻没有摘要或完整内容。"
                        
                        cleaned_content = strip_html_tags(content)
                        
                        source_news_items.append({
                            "title": title,
                            "link": link,
                            "published_str": published_str,
                            "content": cleaned_content
                        })

                    except Exception as e:
                        print(f"❌ 处理新闻条目 '{entry.get('title', '未知标题')}' 时发生错误: {e}")
                        print(f"链接: {entry.get('link', '无链接')}")
                
                all_news_data[country].append({"name": news_name, "items": source_news_items})

            except Exception as e:
                print(f"❌ 错误：处理新闻源 {news_name} ({feed_url}) 时发生网络或其他问题: {e}")
                print("请检查该 RSS Feed 地址是否正确、您的 RSSHub 服务是否正常运行。")
    return all_news_data


def generate_summary_markdown(news_data, i):
    """
    将结构化新闻数据转换为一个Markdown字符串。
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    # 获取当前日期，用于文章标题和文件名
    # 按照 [XXXX年X月X日 全球新闻汇总] 格式
    today_date_display = now_utc.strftime('%Y.%m.%d.') 
    if i == 0:
        markdown_title = f"[{today_date_display} 全球新闻汇总]"
    else:
        markdown_title = f"[{today_date_display} Global News Roundup]"

    markdown_content = ""

    # --- Hugo Front Matter ---
    markdown_content += f"""---
title: "{markdown_title}"
date: {now_utc.isoformat(timespec='seconds')}
categories: ["新闻整合"]
tags: ["每日", "新闻", "自动化", "{now_utc.strftime('%Y%m%d')}"]
draft: false
---
"""
    # print(news_data)
    for country, sources in news_data.items():
        if sources:
            markdown_content += f"## 国家/地区: {country}\n\n"
            for source in sources:
                if source["items"]:
                    markdown_content += f"### {source['name']}\n\n"
                    for item in source["items"]:
                        markdown_content += f"* **[{item['title']}]({item['link']})** - {item['published_str']}\n"
                        display_content = item['content'].replace('\n', ' ')
                        markdown_content += f"  > {display_content[:500]}...\n\n"
    return markdown_content

if __name__ == "__main__":
    print("--- 启动每日新闻整合与Markdown生成脚本 ---")
    
    all_news_data = fetch_news_data()
    # print(all_news_data)
    
    if all_news_data:
        for i in range(2):
            markdown_output = generate_summary_markdown(all_news_data, i)
    
            os.makedirs(OUTPUT_SUMMARY_DIR[i], exist_ok=True)
    
            current_date_filename = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')
            output_filepath = os.path.join(OUTPUT_SUMMARY_DIR[i], f"{SUMMARY_FILENAME_PREFIX}-{current_date_filename}.md")

            try:
                with open(output_filepath, 'w', encoding='utf-8') as f:
                    f.write(markdown_output)
                print(f"✅ 成功生成整合新闻文件: {output_filepath}")
            except Exception as e:
                print(f"❌ 错误：保存Markdown文件失败: {e}")
        else:
            print("没有获取到任何新闻数据，跳过Markdown文件生成。")

        print("\n--- 脚本执行完毕 ---")
