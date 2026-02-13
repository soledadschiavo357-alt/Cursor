import os
import glob
import subprocess
from bs4 import BeautifulSoup
import sys
import datetime
import json
import re
import hashlib
import copy
import math
import shutil

# ==========================================
# Configuration & Constants
# ==========================================
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(ROOT_DIR, 'index.html')
BLOG_DIR = os.path.join(ROOT_DIR, 'blog')

# Tag Mappings: Map granular tags to broader categories
TAG_MAPPING = {
    "新手教程": "使用教程",
    "使用指南": "使用教程",
    "汉化教程": "使用教程",
    "功能解析": "使用教程",
    "技术干货": "技术深度",
    "技术揭秘": "技术深度",
    "深度评测": "技术深度",
    "价格解析": "订阅指南",
    "充值指南": "订阅指南"
}

# Icons for auto-generation based on title hash
ICONS = [
    "fa-code", "fa-terminal", "fa-laptop-code", "fa-microchip", 
    "fa-network-wired", "fa-database", "fa-server", "fa-cloud",
    "fa-layer-group", "fa-cubes", "fa-robot", "fa-brain",
    "fa-keyboard", "fa-sitemap", "fa-bug", "fa-file-code"
]

# ==========================================
# Helper Functions
# ==========================================

def get_post_date(filepath):
    """
    Get the original creation date from Git history.
    Fallback to today if not found.
    """
    try:
        # Get all commit dates for the file (newest first)
        # --follow handles renames
        result = subprocess.run(
            ['git', 'log', '--follow', '--format=%ad', '--date=short', filepath],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split('\n')
        
        # The last line is the oldest commit (creation date)
        if lines and lines[-1]:
            return lines[-1].strip()
            
    except Exception as e:
        print(f"⚠️ Git date extraction failed for {os.path.basename(filepath)}: {e}")
    
    return datetime.date.today().isoformat()

def get_last_modified_date(filepath):
    """
    Get the last modification date from Git history.
    Fallback to today if not found.
    """
    try:
        # Get latest commit date for the file
        result = subprocess.run(
            ['git', 'log', '-n', '1', '--format=%ad', '--date=short', filepath],
            capture_output=True, text=True
        )
        line = result.stdout.strip()
        if line:
            return line
            
    except Exception as e:
        print(f"⚠️ Git lastmod extraction failed for {os.path.basename(filepath)}: {e}")
    
    return datetime.date.today().isoformat()

# ==========================================
# Classes
# ==========================================

class SmartExtractor:
    def __init__(self, index_path):
        self.index_path = index_path
        with open(self.index_path, 'r', encoding='utf-8') as f:
            self.soup = BeautifulSoup(f, 'html.parser')

    def get_nav(self):
        nav = self.soup.find('nav')
        if nav:
            self._standardize_links(nav, convert_anchors=True)
            # Ensure logo points to SVG if referenced
            logo_img = nav.find('img', alt=lambda x: x and 'logo' in x.lower())
            if logo_img:
                logo_img['src'] = '/assets/logo.png'
        return nav

    def get_footer(self):
        footer = self.soup.find('footer')
        if footer:
            self._standardize_links(footer, convert_anchors=True)
        return footer

    def get_favicons(self):
        """Extracts and standardizes favicon links."""
        favicons = []
        icon_tags = self.soup.find_all('link', rel=lambda x: x and ('icon' in x.lower() or 'apple-touch-icon' in x.lower()))
        
        for tag in icon_tags:
            new_tag = tag.__copy__()
            href = new_tag.get('href')
            if href:
                if href.startswith('data:'):
                    pass
                elif not href.startswith(('http', '//', '/')):
                    new_tag['href'] = '/' + href
                elif href.startswith('./'):
                    new_tag['href'] = '/' + href[2:]
            favicons.append(new_tag)
        return favicons

    def _standardize_links(self, element, convert_anchors=False):
        """Helper to ensure links and resources in an element are root-relative and clean."""
        # 1. Standardize Links (a tags)
        for a in element.find_all('a', href=True):
            href = a['href']
            
            # Skip external/special links
            if href.startswith(('http', '//', 'mailto:', 'tel:', 'javascript:', 'data:')):
                if href.startswith(('http://', 'https://', '//')):
                    if 'cursor-vip.pro' not in href:
                        rel = a.get('rel', [])
                        if isinstance(rel, str): rel = [rel]
                        updates = ['nofollow', 'noopener', 'noreferrer']
                        for u in updates:
                            if u not in rel:
                                rel.append(u)
                        a['rel'] = rel
                continue

            # Handle Anchors
            if href.startswith('#'):
                if convert_anchors and href != '#':
                    href = '/' + href
                    a['href'] = href
                continue

            # Clean URL: Remove .html suffix
            if href.endswith('.html'):
                href = href[:-5]
                if not href: href = '/' 

            # Clean URL: Remove /index suffix
            if href.endswith('/index'):
                href = href[:-5]
            
            # Force Root Relative Path
            if not href.startswith('/'):
                href = '/' + href
            
            a['href'] = href

        # 2. Standardize Resources (img src, etc.)
        for tag in element.find_all(['img', 'script', 'source'], src=True):
            src = tag['src']
            if not src.startswith(('http', '//', '/', 'data:')):
                tag['src'] = '/' + src

class HeadReconstructor:
    def __init__(self, soup, metadata, favicons, latest_posts=None):
        self.soup = soup
        self.metadata = metadata
        self.favicons = favicons
        self.latest_posts = latest_posts or []

    def reconstruct(self):
        head = self.soup.find('head')
        if not head:
            head = self.soup.new_tag('head')
            self.soup.html.insert(0, head)
        
        # Extract existing CSS/JS to preserve
        css_js_tags = head.find_all(['link', 'script', 'style'])
        preserved_resources = []
        for tag in css_js_tags:
            is_favicon = tag.name == 'link' and tag.get('rel') and ('icon' in tag.get('rel')[0].lower() or 'apple-touch-icon' in tag.get('rel')[0].lower())
            is_canonical = tag.name == 'link' and tag.get('rel') and 'canonical' in tag.get('rel')
            is_json_ld = tag.name == 'script' and tag.get('type') == 'application/ld+json'
            
            if not is_favicon and not is_canonical and not is_json_ld:
                 preserved_resources.append(tag)

        head.clear()

        # Group A: Basic Metadata
        head.append(self.soup.new_tag('meta', charset="utf-8"))
        head.append(self.soup.new_tag('meta', attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"}))
        
        title_tag = self.soup.new_tag('title')
        title_tag.string = self.metadata.get('title', 'Cursor Blog')
        head.append(title_tag)
        
        # Group B: SEO Core
        if self.metadata.get('description'):
            head.append(self.soup.new_tag('meta', attrs={"name": "description", "content": self.metadata.get('description')}))
        if self.metadata.get('keywords'):
            head.append(self.soup.new_tag('meta', attrs={"name": "keywords", "content": self.metadata.get('keywords')}))
        
        canonical = self.soup.new_tag('link', rel="canonical", href=self.metadata.get('url', ''))
        head.append(canonical)

        # Group C: Indexing & Geo
        head.append(self.soup.new_tag('meta', attrs={"name": "robots", "content": "index, follow"}))
        head.append(self.soup.new_tag('meta', attrs={"http-equiv": "content-language", "content": "zh-cn"}))

        # Group C.1: Open Graph / Social
        head.append(self.soup.new_tag('meta', attrs={"property": "og:title", "content": self.metadata.get('title')}))
        head.append(self.soup.new_tag('meta', attrs={"property": "og:description", "content": self.metadata.get('description')}))
        head.append(self.soup.new_tag('meta', attrs={"property": "og:url", "content": self.metadata.get('url')}))
        head.append(self.soup.new_tag('meta', attrs={"property": "og:site_name", "content": "Cursor-VIP.pro"}))
        head.append(self.soup.new_tag('meta', attrs={"property": "og:image", "content": "https://cursor-vip.pro/assets/og.png"}))
        head.append(self.soup.new_tag('meta', attrs={"property": "og:type", "content": "website"}))
        
        if self.metadata.get('author'):
            head.append(self.soup.new_tag('meta', attrs={"name": "author", "content": self.metadata.get('author')}))
        if self.metadata.get('date') and self.metadata.get('type') == 'blog':
            head.append(self.soup.new_tag('meta', attrs={"property": "article:published_time", "content": self.metadata.get('date')}))

        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:card", "content": "summary_large_image"}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:title", "content": self.metadata.get('title')}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:description", "content": self.metadata.get('description')}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:image", "content": "https://cursor-vip.pro/assets/og.png"}))
        
        # Group D: Branding & Resources
        for favicon in self.favicons:
            head.append(favicon)
        
        for res in preserved_resources:
            head.append(res)

        # Group E: Schema
        schema_gen = SchemaGenerator(self.metadata)
        schemas = []
        
        if self.metadata.get('type') == 'home':
            schemas = schema_gen.get_home_schema()
        elif self.metadata.get('type') == 'blog':
            schemas = schema_gen.get_blog_schema()
        else:
            schemas = schema_gen.get_static_page_schema()

        for s in schemas:
            script_schema = self.soup.new_tag('script', type="application/ld+json")
            script_schema.string = json.dumps(s, ensure_ascii=False, indent=2)
            head.append(script_schema)

class SchemaGenerator:
    def __init__(self, metadata):
        self.metadata = metadata
        self.base_url = "https://cursor-vip.pro"

    def get_home_schema(self):
        website = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "Cursor-VIP.pro",
            "url": self.base_url,
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{self.base_url}/search?q={{search_term_string}}",
                "query-input": "required name=search_term_string"
            }
        }
        org = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Cursor-VIP",
            "url": self.base_url,
            "logo": f"{self.base_url}/assets/logo.png",
            "sameAs": ["https://github.com/cursor-vip", "https://twitter.com/cursor_vip"],
            "contactPoint": {
                "@type": "ContactPoint",
                "email": "support@cursor-vip.pro",
                "contactType": "customer support"
            }
        }
        return [website, org]

    def get_blog_schema(self):
        blog_posting = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": self.metadata.get('title'),
            "description": self.metadata.get('description'),
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": self.metadata.get('url')
            },
            "author": {
                "@type": "Organization",
                "name": "Cursor-VIP Team"
            },
            "publisher": {
                "@type": "Organization",
                "name": "Cursor-VIP",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{self.base_url}/logo.svg"
                }
            },
            "datePublished": self.metadata.get('date', datetime.date.today().isoformat())
        }
        breadcrumb = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "首页",
                    "item": self.base_url
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "博客",
                    "item": f"{self.base_url}/blog/"
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": self.metadata.get('title'),
                    "item": self.metadata.get('url')
                }
            ]
        }
        return [blog_posting, breadcrumb]

    def get_static_page_schema(self):
        return [{
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": self.metadata.get('title'),
            "description": self.metadata.get('description'),
            "url": self.metadata.get('url')
        }]

class ContentInjector:
    def __init__(self, soup):
        self.soup = soup

    def _get_icon(self, title):
        hash_val = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16)
        return ICONS[hash_val % len(ICONS)]

    def inject_nav(self, nav_html):
        if not nav_html: return
        body = self.soup.find('body')
        if not body: return
        existing_nav = body.find('nav')
        if existing_nav: existing_nav.decompose()
        body.insert(0, nav_html)

    def inject_footer(self, footer_html):
        if not footer_html: return
        body = self.soup.find('body')
        if not body: return
        existing_footer = body.find('footer')
        if existing_footer: existing_footer.decompose()
        body.append(footer_html)

    def inject_breadcrumbs(self, title, is_blog_index=False):
        main = self.soup.find('main')
        if not main: return
        
        if main.has_attr('class'):
            classes = main['class']
            new_classes = [c for c in classes if not c.startswith('pt-') and not c.startswith('lg:pt-')]
            new_classes.extend(['pt-24', 'lg:pt-32'])
            main['class'] = new_classes
        
        existing_bc = main.find('nav', attrs={"aria-label": "Breadcrumb"})
        if existing_bc: existing_bc.decompose()
            
        if is_blog_index:
             bc_html = f"""
            <nav aria-label="Breadcrumb" class="max-w-7xl mx-auto px-6 mb-8">
              <ol class="flex items-center space-x-2 text-sm text-slate-400">
                <li><a href="/" class="hover:text-white transition">首页</a></li>
                <li><i class="fa-solid fa-chevron-right text-xs opacity-50"></i></li>
                <li class="text-slate-200 font-medium truncate" aria-current="page">博客</li>
              </ol>
            </nav>
            """
        else:
            bc_html = f"""
            <nav aria-label="Breadcrumb" class="max-w-7xl mx-auto px-6 mb-8">
              <ol class="flex items-center space-x-2 text-sm text-slate-400">
                <li><a href="/" class="hover:text-white transition">首页</a></li>
                <li><i class="fa-solid fa-chevron-right text-xs opacity-50"></i></li>
                <li><a href="/blog/" class="hover:text-white transition">博客</a></li>
                <li><i class="fa-solid fa-chevron-right text-xs opacity-50"></i></li>
                <li class="text-slate-200 font-medium truncate" aria-current="page">{title}</li>
              </ol>
            </nav>
            """
        main.insert(0, BeautifulSoup(bc_html, 'html.parser'))

    def inject_article_meta(self, date, author="Cursor-VIP Team"):
        header = self.soup.find('header')
        if not header: return
        existing_meta = header.find('div', id="article-meta")
        if existing_meta: existing_meta.decompose()
        meta_html = f"""
        <div id="article-meta" class="flex items-center justify-center gap-6 text-sm text-slate-400 mt-4 font-mono">
            <div class="flex items-center gap-2">
                <i class="fa-regular fa-calendar text-blue-400"></i>
                <time datetime="{date}">{date}</time>
            </div>
            <div class="flex items-center gap-2">
                <i class="fa-regular fa-user text-purple-400"></i>
                <span>{author}</span>
            </div>
        </div>
        """
        header.append(BeautifulSoup(meta_html, 'html.parser'))

    def inject_recommended(self, posts, current_url):
        article = self.soup.find('article')
        if not article: return
        
        rec = article.find(id="recommended-reading")
        if rec: rec.decompose()
            
        for h3 in article.find_all('h3'):
            if "推荐阅读" in h3.get_text():
                parent = h3.parent
                if parent.name == 'div': parent.decompose()

        recommendations = [p for p in posts if p['type'] == 'blog' and p['url'] != current_url and not p['url'].endswith('/index') and 'index.html' not in p['url']]
        recommendations.sort(key=lambda x: x['date'], reverse=True)
        recommendations = recommendations[:3]
        if not recommendations: return

        rec_html = """
        <div id="recommended-reading" class="mt-16 pt-10 border-t border-white/10">
            <h3 class="text-2xl font-bold text-white mb-8">推荐阅读</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6"></div>
        </div>
        """
        rec_soup = BeautifulSoup(rec_html, 'html.parser')
        grid_container = rec_soup.find('div', class_="grid")
        
        for post in recommendations:
             title = post.get('title', 'Untitled').split(" - ")[0]
             desc = post.get('description', '')[:40] + '...' if len(post.get('description', '')) > 40 else post.get('description', '')
             url = post.get('url', '#').replace("https://cursor-vip.pro", "") or "/"
             date = post.get('date', '')
             tag = post.get('tag', 'Tech')
             icon = self._get_icon(title)
             
             card_html = f"""
             <a href="{url}" class="block group h-full">
              <article class="glass-card h-full rounded-xl overflow-hidden flex flex-col bg-[#0B0F19] border border-white/10 hover:border-blue-500/30 transition duration-300">
               <div class="h-32 bg-slate-900/50 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-blue-900/20 to-slate-900"></div>
                <div class="absolute inset-0 flex items-center justify-center">
                 <i class="fa-solid {icon} text-4xl text-blue-500/20 group-hover:text-blue-500/40 transition duration-500"></i>
                </div>
                <div class="absolute top-3 left-3">
                 <span class="px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/10 text-blue-300 text-[10px] font-mono">{tag}</span>
                </div>
               </div>
               <div class="p-4 flex flex-col flex-grow">
                <h4 class="text-base font-bold text-white mb-2 group-hover:text-blue-400 transition line-clamp-2">{title}</h4>
                <div class="flex items-center justify-between text-[10px] text-slate-500 mt-auto pt-3 border-t border-white/5">
                 <div class="flex items-center gap-1.5"><i class="fa-regular fa-calendar"></i><span>{date}</span></div>
                 <i class="fa-solid fa-arrow-right group-hover:translate-x-1 transition"></i>
                </div>
               </div>
              </article>
             </a>
             """
             grid_container.append(BeautifulSoup(card_html, 'html.parser'))

        article.append(rec_soup)

    def inject_blog_app(self, posts):
        container = self.soup.find(id="blog-posts-container")
        if not container: return
        
        existing_scripts = self.soup.find_all('script')
        for script in existing_scripts:
            if script.string and ('const BLOG_DATA' in script.string or 'const BLOG_TAGS' in script.string):
                script.decompose()
        
        container.clear()
        
        posts_data = []
        tags = set()
        
        for p in posts:
            if p['url'].endswith('/index') or 'index.html' in p['url']: continue
            
            title = p.get('title', 'Untitled').split(" - ")[0]
            desc = p.get('description', '')[:60] + '...' if len(p.get('description', '')) > 60 else p.get('description', '')
            url = p.get('url', '#').replace("https://cursor-vip.pro", "") or "/"
            date = p.get('date', '')
            tag = p.get('tag', 'Tech')
            if tag: tags.add(tag)
            icon = self._get_icon(title)
            
            posts_data.append({
                "title": title, "desc": desc, "url": url,
                "date": date, "tag": tag, "icon": icon
            })
            
        sorted_tags = sorted(list(tags))

        # --- Pre-render Category Nav ---
        cat_buttons = [f'<button onclick="window.setCategory(\'全部\')" class="px-4 py-2 rounded-full text-sm font-medium transition bg-blue-600 text-white shadow-lg shadow-blue-500/25">全部</button>']
        for tag in sorted_tags:
             cat_buttons.append(f'<button onclick="window.setCategory(\'{tag}\')" class="px-4 py-2 rounded-full text-sm font-medium transition bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5">{tag}</button>')
        
        cat_nav = self.soup.find(id="category-nav")
        if cat_nav: cat_nav.decompose()
        cat_html = f'<div id="category-nav" class="flex flex-wrap gap-2 mb-12 justify-center">{"".join(cat_buttons)}</div>'
        container.insert_before(BeautifulSoup(cat_html, 'html.parser'))
        
        # --- Pre-render Posts (Page 1) ---
        posts_per_page = 6
        page_1_posts = posts_data[:posts_per_page]
        
        if not page_1_posts:
             container.append(BeautifulSoup('<div class="col-span-full text-center text-slate-500 py-20">暂无文章</div>', 'html.parser'))
        else:
             for post in page_1_posts:
                 card_html = f"""
                 <a href="{post['url']}" class="block group">
                  <article class="glass-card h-full rounded-2xl overflow-hidden flex flex-col">
                   <div class="h-48 bg-slate-900/50 relative overflow-hidden">
                    <div class="absolute inset-0 bg-gradient-to-br from-blue-900/40 to-slate-900"></div>
                    <div class="absolute inset-0 flex items-center justify-center">
                     <i class="fa-solid {post['icon']} text-6xl text-blue-500/20 group-hover:text-blue-500/40 transition duration-500"></i>
                    </div>
                    <div class="absolute top-4 left-4">
                     <span class="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/20 text-blue-300 text-xs font-mono">{post['tag']}</span>
                    </div>
                   </div>
                   <div class="p-6 flex flex-col flex-grow">
                    <h2 class="text-xl font-bold text-white mb-3 group-hover:text-blue-400 transition">{post['title']}</h2>
                    <p class="text-sm text-slate-400 leading-relaxed mb-6 flex-grow">{post['desc']}</p>
                    <div class="flex items-center justify-between text-xs text-slate-500 border-t border-white/5 pt-4">
                     <div class="flex items-center gap-2"><i class="fa-regular fa-calendar"></i><span>{post['date']}</span></div>
                     <div class="flex items-center gap-1 group-hover:translate-x-1 transition"><span>阅读全文</span><i class="fa-solid fa-arrow-right"></i></div>
                    </div>
                   </div>
                  </article>
                 </a>
                 """
                 container.append(BeautifulSoup(card_html, 'html.parser'))

        # --- Pre-render Pagination ---
        pag_nav = self.soup.find(id="pagination")
        if pag_nav: pag_nav.decompose()
        
        total_pages = math.ceil(len(posts_data) / posts_per_page)
        pag_inner_html = ""
        if total_pages > 1:
            pag_inner_html += f'<button onclick="window.setPage(1)" class="w-10 h-10 flex items-center justify-center rounded-full text-sm font-medium transition bg-blue-600 text-white shadow-lg shadow-blue-500/25">1</button>'
            for i in range(2, total_pages + 1):
                if i <= 3:
                     pag_inner_html += f'<button onclick="window.setPage({i})" class="w-10 h-10 flex items-center justify-center rounded-full text-sm font-medium transition bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5">{i}</button>'
                elif i == 4 and total_pages > 4:
                     pag_inner_html += '<span class="w-10 h-10 flex items-center justify-center text-slate-600">...</span>'
            pag_inner_html += f'<button onclick="window.setPage(2)" class="w-10 h-10 flex items-center justify-center rounded-full bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5 transition"><i class="fa-solid fa-chevron-right text-xs"></i></button>'

        pag_html = f'<div id="pagination" class="flex justify-center items-center gap-2 mt-16">{pag_inner_html}</div>'
        container.insert_after(BeautifulSoup(pag_html, 'html.parser'))
            
        script_content = f"""
        const BLOG_DATA = {json.dumps(posts_data, ensure_ascii=False)};
        const BLOG_TAGS = {json.dumps(sorted_tags, ensure_ascii=False)};
        
        (function() {{
            const postsPerPage = 6;
            let currentPage = 1;
            let currentCategory = '全部';
            const container = document.getElementById('blog-posts-container');
            const catNav = document.getElementById('category-nav');
            const pagNav = document.getElementById('pagination');
            
            function initState() {{
                const params = new URLSearchParams(window.location.search);
                currentCategory = params.get('category') || '全部';
                currentPage = parseInt(params.get('page')) || 1;
                render();
            }}
            
            function render() {{
                const filtered = currentCategory === '全部' ? BLOG_DATA : BLOG_DATA.filter(p => p.tag === currentCategory);
                const totalPages = Math.ceil(filtered.length / postsPerPage);
                if (currentPage > totalPages) currentPage = 1;
                if (currentPage < 1) currentPage = 1;
                
                const start = (currentPage - 1) * postsPerPage;
                const pagePosts = filtered.slice(start, start + postsPerPage);
                
                renderPosts(pagePosts);
                renderCategories();
                renderPagination(totalPages);
                
                const newUrl = new URL(window.location);
                if (currentCategory !== '全部') newUrl.searchParams.set('category', currentCategory);
                else newUrl.searchParams.delete('category');
                if (currentPage > 1) newUrl.searchParams.set('page', currentPage);
                else newUrl.searchParams.delete('page');
                window.history.replaceState({{}}, '', newUrl);
            }}
            
            function renderPosts(posts) {{
                if (posts.length === 0) {{
                    container.innerHTML = '<div class="col-span-full text-center text-slate-500 py-20">暂无文章</div>';
                    return;
                }}
                container.innerHTML = posts.map(post => `
                    <a href="${{post.url}}" class="block group">
                      <article class="glass-card h-full rounded-2xl overflow-hidden flex flex-col">
                       <div class="h-48 bg-slate-900/50 relative overflow-hidden">
                        <div class="absolute inset-0 bg-gradient-to-br from-blue-900/40 to-slate-900"></div>
                        <div class="absolute inset-0 flex items-center justify-center">
                         <i class="fa-solid ${{post.icon}} text-6xl text-blue-500/20 group-hover:text-blue-500/40 transition duration-500"></i>
                        </div>
                        <div class="absolute top-4 left-4">
                         <span class="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/20 text-blue-300 text-xs font-mono">${{post.tag}}</span>
                        </div>
                       </div>
                       <div class="p-6 flex flex-col flex-grow">
                        <h2 class="text-xl font-bold text-white mb-3 group-hover:text-blue-400 transition">${{post.title}}</h2>
                        <p class="text-sm text-slate-400 leading-relaxed mb-6 flex-grow">${{post.desc}}</p>
                        <div class="flex items-center justify-between text-xs text-slate-500 border-t border-white/5 pt-4">
                         <div class="flex items-center gap-2"><i class="fa-regular fa-calendar"></i><span>${{post.date}}</span></div>
                         <div class="flex items-center gap-1 group-hover:translate-x-1 transition"><span>阅读全文</span><i class="fa-solid fa-arrow-right"></i></div>
                        </div>
                       </div>
                      </article>
                    </a>
                `).join('');
            }}
            
            function renderCategories() {{
                const allActive = currentCategory === '全部' ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5';
                let html = `<button onclick="window.setCategory('全部')" class="px-4 py-2 rounded-full text-sm font-medium transition ${{allActive}}">全部</button>`;
                BLOG_TAGS.forEach(tag => {{
                    const isActive = currentCategory === tag;
                    const cls = isActive ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5';
                    html += `<button onclick="window.setCategory('${{tag}}')" class="px-4 py-2 rounded-full text-sm font-medium transition ${{cls}}">${{tag}}</button>`;
                }});
                catNav.innerHTML = html;
            }}
            
            function renderPagination(totalPages) {{
                if (totalPages <= 1) {{ pagNav.innerHTML = ''; return; }}
                let html = '';
                if (currentPage > 1) html += `<button onclick="window.setPage(${{currentPage - 1}})" class="w-10 h-10 flex items-center justify-center rounded-full bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5 transition"><i class="fa-solid fa-chevron-left text-xs"></i></button>`;
                for (let i = 1; i <= totalPages; i++) {{
                    if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {{
                        const isActive = i === currentPage;
                        const cls = isActive ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/25' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5';
                        html += `<button onclick="window.setPage(${{i}})" class="w-10 h-10 flex items-center justify-center rounded-full text-sm font-medium transition ${{cls}}">${{i}}</button>`;
                    }} else if (i === 2 && currentPage > 3) html += '<span class="w-10 h-10 flex items-center justify-center text-slate-600">...</span>';
                    else if (i === totalPages - 1 && currentPage < totalPages - 2) html += '<span class="w-10 h-10 flex items-center justify-center text-slate-600">...</span>';
                }}
                if (currentPage < totalPages) html += `<button onclick="window.setPage(${{currentPage + 1}})" class="w-10 h-10 flex items-center justify-center rounded-full bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white border border-white/5 transition"><i class="fa-solid fa-chevron-right text-xs"></i></button>`;
                pagNav.innerHTML = html;
            }}
            
            window.setCategory = (cat) => {{ currentCategory = cat; currentPage = 1; render(); }};
            window.setPage = (p) => {{ currentPage = p; render(); document.getElementById('category-nav').scrollIntoView({{ behavior: 'smooth' }}); }};
            
            initState();
            window.addEventListener('popstate', initState);
        }})();
        """
        script_tag = self.soup.new_tag('script')
        script_tag.string = script_content
        self.soup.body.append(script_tag)

    def inject_latest_posts(self, posts):
        container = self.soup.find(id="latest-posts-container")
        if not container: return
        container.clear()
        for post in posts[:6]:
            title = post.get('title', 'Untitled')
            desc = post.get('description', '')[:60] + '...' if len(post.get('description', '')) > 60 else post.get('description', '')
            url = post.get('url', '#').replace("https://cursor-vip.pro", "") or "/"
            date = post.get('date', '')
            tag = post.get('tag', 'Tech')
            html = f"""
            <a href="{url}" class="block group">
             <article class="glass-card h-full rounded-2xl overflow-hidden flex flex-col bg-[#0B0F19] border border-white/10 hover:border-blue-500/30 transition duration-300">
              <div class="p-6 flex flex-col flex-grow">
               <div class="flex items-center justify-between mb-4">
                <span class="px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono">{tag}</span>
                <span class="text-xs text-slate-500 font-mono">{date}</span>
               </div>
               <h3 class="text-lg font-bold text-white mb-3 group-hover:text-blue-400 transition line-clamp-2">{title}</h3>
               <p class="text-sm text-slate-400 leading-relaxed mb-6 flex-grow line-clamp-3">{desc}</p>
               <div class="flex items-center gap-2 text-xs text-slate-500 group-hover:text-blue-400 transition mt-auto">
                <span>Read Article</span>
                <i class="fa-solid fa-arrow-right group-hover:translate-x-1 transition-transform"></i>
               </div>
              </div>
             </article>
            </a>
            """
            container.append(BeautifulSoup(html, 'html.parser'))

class SitemapGenerator:
    def __init__(self, base_url="https://cursor-vip.pro"):
        self.base_url = base_url
        self.urls = []

    def add_url(self, url, priority=0.8, lastmod=None):
        if not lastmod: lastmod = datetime.date.today().isoformat()
        self.urls.append({"loc": url, "lastmod": lastmod, "priority": priority})

    def generate(self, output_path):
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u in self.urls:
            xml.append(f'  <url>\n    <loc>{u["loc"]}</loc>\n    <lastmod>{u["lastmod"]}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>{u["priority"]}</priority>\n  </url>')
        xml.append('</urlset>')
        with open(output_path, 'w', encoding='utf-8') as f: f.write('\n'.join(xml))

class RobotsGenerator:
    def __init__(self, base_url="https://cursor-vip.pro"):
        self.base_url = base_url

    def generate(self, output_path):
        content = f"User-agent: *\nAllow: /\n\nSitemap: {self.base_url}/sitemap.xml\n"
        with open(output_path, 'w', encoding='utf-8') as f: f.write(content)

def main():
    print("🚀 Starting Build Process...")
    if not os.path.exists(INDEX_FILE):
        print(f"❌ Error: {INDEX_FILE} not found.")
        return

    print(f"📖 Reading {INDEX_FILE}...")
    extractor = SmartExtractor(INDEX_FILE)
    nav = extractor.get_nav()
    footer = extractor.get_footer()
    favicons = extractor.get_favicons()
    
    if not os.path.exists(BLOG_DIR): os.makedirs(BLOG_DIR, exist_ok=True)
    blog_files = glob.glob(os.path.join(BLOG_DIR, '*.html'))
    static_pages = ['index.html', 'about.html', 'privacy.html', 'terms.html', 'refund.html']
    root_files = [os.path.join(ROOT_DIR, f) for f in static_pages if os.path.exists(os.path.join(ROOT_DIR, f))]
    all_files = blog_files + root_files
    print(f"📂 Found {len(all_files)} files to process.")

    latest_posts = []
    processed_files = []

    for post_path in all_files:
        is_index = os.path.basename(post_path) == 'index.html'
        with open(post_path, 'r', encoding='utf-8') as f: soup = BeautifulSoup(f, 'html.parser')
        extractor._standardize_links(soup)

        title_tag_find = soup.find('title')
        title = title_tag_find.get_text().strip() if title_tag_find else "Untitled"
        if " - Cursor-VIP.pro" in title: title = title.replace(" - Cursor-VIP.pro", "")
        title = re.sub(r'^\d+[.、\s]*\s*', '', title)
        title = re.sub(r'\s?202[0-9]\s?', '', title)
            
        desc_tag = soup.find('meta', attrs={"name": "description"})
        description = desc_tag['content'] if desc_tag else "Cursor VIP Service."
        
        filename = os.path.basename(post_path)
        if BLOG_DIR in post_path:
            url = f"https://cursor-vip.pro/blog/{filename.replace('.html', '')}"
            page_type = 'blog'
        else:
            if is_index:
                url = "https://cursor-vip.pro/"
                page_type = 'home'
            else:
                url = f"https://cursor-vip.pro/{filename.replace('.html', '')}"
                page_type = 'static'

        metadata = {"title": title, "description": description, "keywords": "cursor, ai, code editor", "url": url, "type": page_type}
        
        # Date extraction
        # Priority 1: Meta Tag "article:published_time" (Manual Control) - Highest Priority
        # Priority 2: JSON-LD "datePublished" (Manual Control)
        # Priority 3: Git Creation Date (Historical Reality)
        # Priority 4: Today (Fallback)
        
        date_published = None
        
        # 1. Check Meta Tag (Manual Override)
        meta_date = soup.find('meta', property='article:published_time')
        if meta_date and meta_date.get('content'):
            date_published = meta_date['content']
            
        # 2. Check JSON-LD (if not found in meta)
        if not date_published:
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    if script.string:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get('datePublished'):
                            date_published = data.get('datePublished')
                        elif isinstance(data, list):
                             for item in data:
                                 if item.get('datePublished'):
                                     date_published = item.get('datePublished')
                                     break
                    if date_published: break
                except:
                    pass
        
        # 3. Fallback to Git Creation Date
        if not date_published:
             date_published = get_post_date(post_path)
             
        # Get Last Modified Date for Sitemap
        date_modified = get_last_modified_date(post_path)
        
        # 4. Git History Check (Smart Suppression)
        # If Git Last Modified is '2026-02-03' or '2026-02-04' (Batch Fix Dates),
        # AND the article is older than Feb 1st, suppress the modification date in Sitemap.
        # This ensures sitemap looks historically accurate for old posts,
        # while allowing FUTURE updates (after Feb 5th) to trigger a new lastmod.
        
        if date_modified in ['2026-02-03', '2026-02-04', '2026-02-11', '2026-02-12', '2026-02-13']:
            try:
                pub_dt = datetime.datetime.strptime(date_published, "%Y-%m-%d")
                # If published before Feb 15th (covering all current articles), and modified in batch fix window -> use published date
                if pub_dt < datetime.datetime(2026, 2, 15):
                    date_modified = date_published
            except:
                pass
             
        print(f"   📅 Date: {date_published} (Published), {date_modified} (Modified)")
        
        tag = "技术干货"
        tag_elem = soup.find(['span', 'div'], class_=lambda x: x and 'font-mono' in x and 'rounded-full' in x)
        if tag_elem:
            raw_tag = tag_elem.get_text().strip()
            tag = TAG_MAPPING.get(raw_tag, raw_tag)

        metadata["date"] = date_published
        metadata["author"] = "Cursor-VIP Team"
        latest_posts.append({"title": title, "description": description, "url": url, "date": date_published, "lastmod": date_modified, "tag": tag, "type": page_type})
        processed_files.append({"path": post_path, "soup": soup, "metadata": metadata, "is_index": is_index, "page_type": page_type, "date_published": date_published, "title": title})

    for item in processed_files:
        print(f"⚙️ Processing {os.path.basename(item['path'])}...")
        reconstructor = HeadReconstructor(item['soup'], item['metadata'], favicons, latest_posts)
        reconstructor.reconstruct()
        injector = ContentInjector(item['soup'])
        injector.inject_nav(nav)
        injector.inject_footer(footer)
        
        if item['is_index'] and item['page_type'] == 'home':
             blog_posts = [p for p in latest_posts if p['type'] == 'blog' and not p['url'].endswith('/index') and 'index.html' not in p['url']]
             blog_posts.sort(key=lambda x: x['date'], reverse=True)
             injector.inject_latest_posts(blog_posts)
        elif item['is_index'] and item['page_type'] == 'blog':
             all_blog_posts = [p for p in latest_posts if p['type'] == 'blog' and not p['url'].endswith('/index') and 'index.html' not in p['url']]
             all_blog_posts.sort(key=lambda x: x['date'], reverse=True)
             injector.inject_breadcrumbs("博客", is_blog_index=True)
             injector.inject_blog_app(all_blog_posts)
        elif not item['is_index']:
             if item['page_type'] == 'blog':
                 injector.inject_breadcrumbs(item['title'])
                 injector.inject_article_meta(item['date_published'])
                 injector.inject_recommended(latest_posts, item['metadata']['url'])
             else:
                 injector.inject_recommended(latest_posts, item['metadata']['url'])

        with open(item['path'], 'w', encoding='utf-8') as f:
            # Using str() instead of prettify() to preserve formatting
            f.write(str(item['soup']))

    print("📋 Latest Articles updated.")
    
    def sort_key(post):
        url = post['url']
        if url == "https://cursor-vip.pro/": type_order = 0
        elif url == "https://cursor-vip.pro/blog/" or url.endswith("/blog/index"): type_order = 1
        elif "/blog/" in url: type_order = 2
        else: type_order = 3
        try:
            date_str = post.get('date', '1970-01-01')
            if 'T' in date_str: dt = datetime.datetime.fromisoformat(date_str)
            else: dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            timestamp = dt.timestamp()
        except: timestamp = 0
        return (type_order, -timestamp)

    latest_posts.sort(key=sort_key)
    sitemap_gen = SitemapGenerator()

    for post in latest_posts:
        if post['url'] == "https://cursor-vip.pro/" or post['url'].endswith("/index") or post['url'] == "https://cursor-vip.pro/blog/": priority = 1.0 
        elif "/blog/" in post['url']: priority = 0.8
        else: priority = 0.8
        sitemap_url = post['url']
        if sitemap_url.endswith("/index"): sitemap_url = sitemap_url[:-6]
        if not sitemap_url.endswith("/"): sitemap_url += "/"
        sitemap_gen.add_url(sitemap_url, priority, post.get('lastmod', post.get('date')))

    print("🗺️ Generating sitemap.xml...")
    sitemap_gen.generate(os.path.join(ROOT_DIR, 'sitemap.xml'))
    print("🤖 Generating robots.txt...")
    RobotsGenerator().generate(os.path.join(ROOT_DIR, 'robots.txt'))
    print("✨ Build Complete!")

if __name__ == "__main__":
    main()
