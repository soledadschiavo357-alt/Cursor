import os
import glob
from bs4 import BeautifulSoup
import sys
import datetime
import json
import re
import hashlib

# Configuration
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(ROOT_DIR, 'index.html')
BLOG_DIR = os.path.join(ROOT_DIR, 'blog')

class SmartExtractor:
    def __init__(self, index_path):
        self.index_path = index_path
        with open(self.index_path, 'r', encoding='utf-8') as f:
            self.soup = BeautifulSoup(f, 'html.parser')

    def get_nav(self):
        nav = self.soup.find('nav')
        if nav:
            # Clean up active states if necessary, or ensure links are root relative
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
        # Select all icon-related link tags
        icon_tags = self.soup.find_all('link', rel=lambda x: x and ('icon' in x.lower() or 'apple-touch-icon' in x.lower()))
        
        for tag in icon_tags:
            # Create a copy to avoid modifying the original soup during extraction (though standardized links are good)
            new_tag = tag.__copy__()
            href = new_tag.get('href')
            if href:
                # Force root relative path
                if href.startswith('data:'):
                    pass # Ignore data URIs
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
            
            # Skip external/special links (but add protection first)
            if href.startswith(('http', '//', 'mailto:', 'tel:', 'javascript:', 'data:')):
                if href.startswith(('http://', 'https://', '//')):
                    # Check if it's strictly external (not current domain)
                    # We treat links not containing 'cursor-vip.pro' as external
                    if 'cursor-vip.pro' not in href:
                        rel = a.get('rel', [])
                        # bs4 usually returns list for rel, but let's be safe
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
                if not href: href = '/' # index.html -> /
            
            # Clean URL: Remove /index suffix
            if href.endswith('/index'):
                href = href[:-5] # remove index (leaving trailing slash if exists? wait. /blog/index -> /blog/)
                # if href was "index", it became "" -> "/"
                # if href was "blog/index", it becomes "blog/"

            
            # Force Root Relative Path (ensure starts with /)
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
        
        # Clear existing head content but keep specific tags if needed? 
        # Instruction says: "清空并重组" (Clear and Reorganize)
        # But we need to keep CSS/JS resources as per Group D instructions.
        
        # Extract existing CSS/JS to preserve
        css_js_tags = head.find_all(['link', 'script', 'style'])
        preserved_resources = []
        for tag in css_js_tags:
            # Filter out favicons since we re-inject them from index.html
            is_favicon = tag.name == 'link' and tag.get('rel') and ('icon' in tag.get('rel')[0].lower() or 'apple-touch-icon' in tag.get('rel')[0].lower())
            is_canonical = tag.name == 'link' and tag.get('rel') and 'canonical' in tag.get('rel')
            is_json_ld = tag.name == 'script' and tag.get('type') == 'application/ld+json'
            
            # We want to keep CSS (stylesheet), JS (script), Styles (style)
            # We exclude canonical (rebuilt in Group B) and favicons (rebuilt in Group D) and existing JSON-LD (rebuilt in Group E)
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
        
        # SEO: Author and Time
        if self.metadata.get('author'):
            head.append(self.soup.new_tag('meta', attrs={"name": "author", "content": self.metadata.get('author')}))
        if self.metadata.get('date') and self.metadata.get('type') == 'blog':
            head.append(self.soup.new_tag('meta', attrs={"property": "article:published_time", "content": self.metadata.get('date')}))

        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:card", "content": "summary_large_image"}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:title", "content": self.metadata.get('title')}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:description", "content": self.metadata.get('description')}))
        head.append(self.soup.new_tag('meta', attrs={"name": "twitter:image", "content": "https://cursor-vip.pro/assets/og.png"}))
        
        # Group D: Branding & Resources
        # Insert Favicons from Index
        for favicon in self.favicons:
            head.append(favicon)
        
        # Insert Preserved Resources (CSS/JS)
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
        # 1. WebSite
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

        # 2. Organization
        org = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Cursor-VIP",
            "url": self.base_url,
            "logo": f"{self.base_url}/assets/logo.png", # Assuming logo exists, or use favicon
            "sameAs": [
                "https://github.com/cursor-vip",
                "https://twitter.com/cursor_vip"
            ],
            "contactPoint": {
                "@type": "ContactPoint",
                "email": "support@cursor-vip.pro",
                "contactType": "customer support"
            }
        }

        # 3. Product (Cursor Pro)
        product = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Cursor Pro 会员订阅",
            "image": f"{self.base_url}/assets/og.png",
            "description": "Cursor Pro 独享账号与代充服务，解锁 Opus 4.5 与 Copilot++。",
            "brand": {
                "@type": "Brand",
                "name": "Cursor"
            },
            "offers": {
                "@type": "AggregateOffer",
                "priceCurrency": "CNY",
                "lowPrice": "205",
                "highPrice": "260",
                "offerCount": "2",
                "availability": "https://schema.org/InStock"
            },
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": "4.9",
                "reviewCount": "1280"
            }
        }

        # 4. FAQPage
        faq = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "购买后如何发货？需要多久？",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "我们采用全自动发货系统。付款成功后，系统会立即将账号密码（或兑换操作指引）发送到您填写的邮箱中。通常在 1-3 分钟内即可收到。"
                    }
                },
                {
                    "@type": "Question",
                    "name": "成品号和代充有什么区别？",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "成品号 (¥205) 是我们提供一个新的、已经开通好 Pro 会员的账号给您，适合新用户。代充 (¥260) 是在您自己的账号上开通会员，可以保留历史数据。"
                    }
                },
                {
                    "@type": "Question",
                    "name": "账号稳定吗？会掉线吗？",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "非常稳定。我们提供的都是正规渠道开通的独享账号（一人一号），绝非低价共享号。只要不进行恶意滥用，账号在有效期内可以一直稳定使用。"
                    }
                },
                {
                    "@type": "Question",
                    "name": "我的代码会被上传吗？隐私如何保障？",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Cursor 官方非常重视隐私。您可以开启 'Privacy Mode' (隐私模式)，开启后，您的代码仅在本地处理或加密传输用于推理，官方承诺不会将其存储或用于训练模型。"
                    }
                }
            ]
        }

        return [website, org, product, faq]

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
    ICONS = [
        "fa-code", "fa-terminal", "fa-laptop-code", "fa-microchip", 
        "fa-network-wired", "fa-database", "fa-server", "fa-cloud",
        "fa-layer-group", "fa-cubes", "fa-robot", "fa-brain",
        "fa-keyboard", "fa-sitemap", "fa-bug", "fa-file-code"
    ]

    def __init__(self, soup):
        self.soup = soup

    def _get_icon(self, title):
        # Generate consistent icon based on title hash
        hash_val = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16)
        return self.ICONS[hash_val % len(self.ICONS)]

    def inject_nav(self, nav_html):
        if not nav_html: return
        
        body = self.soup.find('body')
        if not body: return
        
        # Remove existing nav
        existing_nav = body.find('nav')
        if existing_nav:
            existing_nav.decompose()
        
        # Insert new nav at the beginning of body
        body.insert(0, nav_html)

    def inject_footer(self, footer_html):
        if not footer_html: return
        
        body = self.soup.find('body')
        if not body: return
        
        # Remove existing footer
        existing_footer = body.find('footer')
        if existing_footer:
            existing_footer.decompose()
            
        # Insert new footer at the end of body (before scripts if any?)
        # Just append to body is usually fine for footer
        body.append(footer_html)

    def inject_breadcrumbs(self, title, is_blog_index=False):
        main = self.soup.find('main')
        if not main: return
        
        # Adjust main padding to reduce gap between header and breadcrumbs
        # Default header is fixed h-16 (mobile) / h-20 (desktop)
        # Previous padding was pt-32 (128px) / lg:pt-48 (192px), which is too large
        # We change it to pt-24 (96px) / lg:pt-32 (128px)
        if main.has_attr('class'):
            classes = main['class']
            # Filter out existing large padding
            new_classes = [c for c in classes if not c.startswith('pt-') and not c.startswith('lg:pt-')]
            # Add new padding
            new_classes.extend(['pt-24', 'lg:pt-32'])
            main['class'] = new_classes
        
        # Remove existing breadcrumbs if any (to avoid duplicates on rebuild)
        existing_bc = main.find('nav', attrs={"aria-label": "Breadcrumb"})
        if existing_bc:
            existing_bc.decompose()
            
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

        bc_soup = BeautifulSoup(bc_html, 'html.parser')
        
        # Insert at the beginning of main
        main.insert(0, bc_soup)

    def inject_article_meta(self, date, author="Cursor-VIP Team"):
        header = self.soup.find('header')
        if not header: return

        # Check if we already injected it to avoid duplicates
        existing_meta = header.find('div', id="article-meta")
        if existing_meta:
            existing_meta.decompose()

        # Create meta HTML
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
        meta_soup = BeautifulSoup(meta_html, 'html.parser')
        
        # Append to header
        header.append(meta_soup)

    def inject_recommended(self, posts, current_url):
        article = self.soup.find('article')
        if not article: return
        
        # Check if recommended section exists (by id)
        rec = article.find(id="recommended-reading")
        if rec:
            rec.decompose() # Clean existing
            
        # Also check for any div that looks like a manual recommended section
        for h3 in article.find_all('h3'):
            if "推荐阅读" in h3.get_text():
                parent = h3.parent
                if parent.name == 'div' and ('bg-slate-900/50' in str(parent.get('class', [])) or 'border-t' in str(parent.get('class', []))):
                     parent.decompose()
                elif parent.name == 'div':
                     parent.decompose()

        # Filter posts
        recommendations = [p for p in posts if p['type'] == 'blog' and p['url'] != current_url and not p['url'].endswith('/index') and 'index.html' not in p['url']]
        
        # Sort by date (newest first)
        recommendations.sort(key=lambda x: x['date'], reverse=True)
        
        # Limit to 3
        recommendations = recommendations[:3]
        
        if not recommendations: return

        # Create Container
        rec_html = """
        <div id="recommended-reading" class="mt-16 pt-10 border-t border-white/10">
            <h3 class="text-2xl font-bold text-white mb-8">推荐阅读</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <!-- Cards injected below -->
            </div>
        </div>
        """
        rec_soup = BeautifulSoup(rec_html, 'html.parser')
        grid_container = rec_soup.find('div', class_="grid")
        
        for post in recommendations:
             # Default values
             title = post.get('title', 'Untitled')
             # Clean title
             if " - " in title:
                 title = title.split(" - ")[0]
             
             desc = post.get('description', '')
             url = post.get('url', '#')
             
             # Convert to root-relative path if internal
             if url.startswith("https://cursor-vip.pro"):
                 url = url.replace("https://cursor-vip.pro", "")
                 if not url: url = "/"
             
             date = post.get('date', '')
             tag = post.get('tag', 'Tech')
             
             # Icon mapping using hash
             icon = self._get_icon(title)
             
             # Truncate description more aggressively for small cards
             if len(desc) > 40: desc = desc[:40] + '...'
             
             card_html = f"""
             <a href="{url}" class="block group h-full">
              <article class="glass-card h-full rounded-xl overflow-hidden flex flex-col bg-[#0B0F19] border border-white/10 hover:border-blue-500/30 transition duration-300">
               <div class="h-32 bg-slate-900/50 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-blue-900/20 to-slate-900"></div>
                <div class="absolute inset-0 flex items-center justify-center">
                 <i class="fa-solid {icon} text-4xl text-blue-500/20 group-hover:text-blue-500/40 transition duration-500"></i>
                </div>
                <div class="absolute top-3 left-3">
                 <span class="px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/10 text-blue-300 text-[10px] font-mono">
                  {tag}
                 </span>
                </div>
               </div>
               <div class="p-4 flex flex-col flex-grow">
                <h4 class="text-base font-bold text-white mb-2 group-hover:text-blue-400 transition line-clamp-2">
                 {title}
                </h4>
                <div class="flex items-center justify-between text-[10px] text-slate-500 mt-auto pt-3 border-t border-white/5">
                 <div class="flex items-center gap-1.5">
                  <i class="fa-regular fa-calendar"></i>
                  <span>{date}</span>
                 </div>
                 <i class="fa-solid fa-arrow-right group-hover:translate-x-1 transition"></i>
                </div>
               </div>
              </article>
             </a>
             """
             card_soup = BeautifulSoup(card_html, 'html.parser')
             grid_container.append(card_soup)

        article.append(rec_soup)

    def inject_blog_index(self, posts):
        container = self.soup.find(id="blog-posts-container")
        if not container: return
        
        container.clear()
        
        for post in posts:
             # Skip the index page itself
             if post['url'].endswith('/index') or 'index.html' in post['url']: continue
             
             # Default values
             title = post.get('title', 'Untitled')
             # Clean title (remove suffix)
             if " - " in title:
                 title = title.split(" - ")[0]
             
             desc = post.get('description', '')
             url = post.get('url', '#')
             
             # Convert to root-relative path if internal
             if url.startswith("https://cursor-vip.pro"):
                 url = url.replace("https://cursor-vip.pro", "")
                 if not url: url = "/"
             
             date = post.get('date', '')
             tag = post.get('tag', 'Tech')
             
             # Icon mapping using hash
             icon = self._get_icon(title)
             
             # Simple truncate description
             if len(desc) > 60: desc = desc[:60] + '...'
             
             html = f"""
             <a href="{url}" class="block group">
              <article class="glass-card h-full rounded-2xl overflow-hidden flex flex-col">
               <div class="h-48 bg-slate-900/50 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-blue-900/40 to-slate-900">
                </div>
                <div class="absolute inset-0 flex items-center justify-center">
                 <i class="fa-solid {icon} text-6xl text-blue-500/20 group-hover:text-blue-500/40 transition duration-500">
                 </i>
                </div>
                <div class="absolute top-4 left-4">
                 <span class="px-3 py-1 rounded-full bg-blue-500/20 border border-blue-500/20 text-blue-300 text-xs font-mono">
                  {tag}
                 </span>
                </div>
               </div>
               <div class="p-6 flex flex-col flex-grow">
                <h2 class="text-xl font-bold text-white mb-3 group-hover:text-blue-400 transition">
                 {title}
                </h2>
                <p class="text-sm text-slate-400 leading-relaxed mb-6 flex-grow">
                 {desc}
                </p>
                <div class="flex items-center justify-between text-xs text-slate-500 border-t border-white/5 pt-4">
                 <div class="flex items-center gap-2">
                  <i class="fa-regular fa-calendar">
                  </i>
                  <span>
                   {date}
                  </span>
                 </div>
                 <div class="flex items-center gap-1 group-hover:translate-x-1 transition">
                  <span>
                   阅读全文
                  </span>
                  <i class="fa-solid fa-arrow-right">
                  </i>
                 </div>
                </div>
               </div>
              </article>
             </a>
             """
             card_soup = BeautifulSoup(html, 'html.parser')
             container.append(card_soup)

    def inject_latest_posts(self, posts):
        container = self.soup.find(id="latest-posts-container")
        if not container: return

        # Clear existing content
        container.clear()

        # Generate HTML for posts
        for post in posts[:6]: # Limit to 6
            # Default values
            title = post.get('title', 'Untitled')
            desc = post.get('description', '')
            url = post.get('url', '#')
            
            # Convert to root-relative path if internal
            if url.startswith("https://cursor-vip.pro"):
                url = url.replace("https://cursor-vip.pro", "")
                if not url: url = "/"
            
            date = post.get('date', '')
            tag = post.get('tag', 'Tech')
            
            # Simple truncate description
            if len(desc) > 60: desc = desc[:60] + '...'

            html = f"""
            <a href="{url}" class="block group">
             <article class="glass-card h-full rounded-2xl overflow-hidden flex flex-col bg-[#0B0F19] border border-white/10 hover:border-blue-500/30 transition duration-300">
              <div class="p-6 flex flex-col flex-grow">
               <div class="flex items-center justify-between mb-4">
                <span class="px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono">
                 {tag}
                </span>
                <span class="text-xs text-slate-500 font-mono">
                 {date}
                </span>
               </div>
               <h3 class="text-lg font-bold text-white mb-3 group-hover:text-blue-400 transition line-clamp-2">
                {title}
               </h3>
               <p class="text-sm text-slate-400 leading-relaxed mb-6 flex-grow line-clamp-3">
                {desc}
               </p>
               <div class="flex items-center gap-2 text-xs text-slate-500 group-hover:text-blue-400 transition mt-auto">
                <span>Read Article</span>
                <i class="fa-solid fa-arrow-right group-hover:translate-x-1 transition-transform"></i>
               </div>
              </div>
             </article>
            </a>
            """
            card_soup = BeautifulSoup(html, 'html.parser')
            container.append(card_soup)

class SitemapGenerator:
    def __init__(self, base_url="https://cursor-vip.pro"):
        self.base_url = base_url
        self.urls = []

    def add_url(self, url, priority=0.8, lastmod=None):
        if not lastmod:
            lastmod = datetime.date.today().isoformat()
            
        self.urls.append({
            "loc": url,
            "lastmod": lastmod,
            "priority": priority
        })

    def generate(self, output_path):
        xml = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        for u in self.urls:
            xml.append('  <url>')
            xml.append(f'    <loc>{u["loc"]}</loc>')
            xml.append(f'    <lastmod>{u["lastmod"]}</lastmod>')
            xml.append('    <changefreq>weekly</changefreq>')
            xml.append(f'    <priority>{u["priority"]}</priority>')
            xml.append('  </url>')
            
        xml.append('</urlset>')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(xml))

class RobotsGenerator:
    def __init__(self, base_url="https://cursor-vip.pro"):
        self.base_url = base_url

    def generate(self, output_path):
        content = f"""User-agent: *
Allow: /

Sitemap: {self.base_url}/sitemap.xml
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

def main():
    print("🚀 Starting Build Process...")
    
    # 1. Smart Extraction
    if not os.path.exists(INDEX_FILE):
        print(f"❌ Error: {INDEX_FILE} not found.")
        return

    print(f"📖 Reading {INDEX_FILE}...")
    extractor = SmartExtractor(INDEX_FILE)
    nav = extractor.get_nav()
    footer = extractor.get_footer()
    favicons = extractor.get_favicons()
    
    print(f"✅ Extracted Nav, Footer, and {len(favicons)} Favicons.")

    # 2. Process Blog Posts
    if not os.path.exists(BLOG_DIR):
        # print(f"⚠️ Warning: {BLOG_DIR} does not exist. Creating it...")
        os.makedirs(BLOG_DIR, exist_ok=True)
        # Create a dummy post for testing - REMOVED per user request
        # with open(os.path.join(BLOG_DIR, 'hello-world.html'), 'w') as f:
        #    f.write("""<!DOCTYPE html><html><head><title>Hello World</title></head><body><article><h1>Hello World</h1><p>Content...</p></article></body></html>""")

    blog_files = glob.glob(os.path.join(BLOG_DIR, '*.html'))
    
    # Add root level static pages
    static_pages = ['index.html', 'about.html', 'privacy.html', 'terms.html', 'refund.html']
    root_files = [os.path.join(ROOT_DIR, f) for f in static_pages if os.path.exists(os.path.join(ROOT_DIR, f))]
    
    all_files = blog_files + root_files
    print(f"📂 Found {len(all_files)} files to process ({len(blog_files)} blog posts, {len(root_files)} static pages).")

    latest_posts = []
    processed_files = []

    # Phase 1: Extraction & Metadata Collection
    for post_path in all_files:
        is_index = os.path.basename(post_path) == 'index.html'
        print(f"🔨 Extracting metadata from {os.path.basename(post_path)}...")
        
        with open(post_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # CLEAN UP LINKS IN CONTENT (Not just Nav/Footer)
        extractor._standardize_links(soup)

        # Metadata extraction (simple version)
        title_tag_find = soup.find('title')
        title = title_tag_find.get_text().strip() if title_tag_find else "Untitled"
        
        # Clean Title Globally (Remove Suffix if user doesn't want it)
        # User requested to remove "- Cursor-VIP.pro"
        if " - Cursor-VIP.pro" in title:
            title = title.replace(" - Cursor-VIP.pro", "")

        # Clean Title: Remove leading numbers (e.g. "1. xxx" -> "xxx")
        title = re.sub(r'^\d+\.?\s*', '', title)
            
        # Try to find description meta, or use first p tag
        desc_tag = soup.find('meta', attrs={"name": "description"})
        description = desc_tag['content'] if desc_tag else "Cursor VIP Service."
        
        filename = os.path.basename(post_path)
        page_type = 'static'
        if BLOG_DIR in post_path:
            url = f"https://cursor-vip.pro/blog/{filename.replace('.html', '')}"
            page_type = 'blog'
        else:
            if is_index:
                url = "https://cursor-vip.pro/"
                page_type = 'home'
            else:
                url = f"https://cursor-vip.pro/{filename.replace('.html', '')}"

        metadata = {
            "title": title,
            "description": description,
            "keywords": "cursor, ai, code editor", # Default keywords
            "url": url,
            "type": page_type
        }

        # Date extraction
        date_published = datetime.date.today().isoformat()
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                         if item.get('datePublished'):
                             date_published = item.get('datePublished')
                             break
                elif data.get('datePublished'):
                    date_published = data.get('datePublished')
            except:
                pass
        
        # Tag extraction
        tag = "技术干货"
        tag_span = soup.find('span', class_=lambda x: x and 'font-mono' in x and 'rounded-full' in x)
        if tag_span:
            tag = tag_span.get_text().strip()

        # Update Metadata with Date and Author
        metadata["date"] = date_published
        metadata["author"] = "Cursor-VIP Team"

        # Save to list (all pages for sitemap)
        post_data = {
            "title": title,
            "description": description,
            "url": url,
            "date": date_published,
            "tag": tag,
            "type": page_type
        }
        latest_posts.append(post_data)
        
        # Store for Phase 2
        processed_files.append({
            "path": post_path,
            "soup": soup,
            "metadata": metadata,
            "is_index": is_index,
            "page_type": page_type,
            "date_published": date_published,
            "title": title
        })

    # Phase 2: Processing & Injection
    for item in processed_files:
        post_path = item['path']
        soup = item['soup']
        metadata = item['metadata']
        is_index = item['is_index']
        page_type = item['page_type']
        date_published = item['date_published']
        title = item['title']
        
        print(f"⚙️ Processing {os.path.basename(post_path)}...")

        # Head Reconstruction
        reconstructor = HeadReconstructor(soup, metadata, favicons, latest_posts)
        reconstructor.reconstruct()

        # Injection
        injector = ContentInjector(soup)
        injector.inject_nav(nav)
        injector.inject_footer(footer)
        
        if is_index and page_type == 'home':
             # Filter only blogs for homepage injection
             blog_posts = [p for p in latest_posts if p['type'] == 'blog' and not p['url'].endswith('/index') and 'index.html' not in p['url']]
             blog_posts.sort(key=lambda x: x['date'], reverse=True)
             injector.inject_latest_posts(blog_posts)
        elif is_index and page_type == 'blog':
             # Inject blog index
             blog_posts = [p for p in latest_posts if p['type'] == 'blog' and not p['url'].endswith('/index') and 'index.html' not in p['url']]
             blog_posts.sort(key=lambda x: x['date'], reverse=True)
             injector.inject_blog_index(blog_posts)
             # Inject breadcrumbs for index
             injector.inject_breadcrumbs("博客", is_blog_index=True)
        elif not is_index:
             if page_type == 'blog':
                 injector.inject_breadcrumbs(title)
                 injector.inject_article_meta(date_published)
                 # Inject recommended reading (pass all posts and current url)
                 injector.inject_recommended(latest_posts, metadata['url'])
             else:
                 injector.inject_recommended(latest_posts, metadata['url'])

        # Save
        with open(post_path, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))

    # 4. Global Update (Homepage Latest Articles)
    # This part assumes there's a place to put them. For now, we'll just log it.
    print("📋 Latest Articles updated (in memory).")
    
    # Sort latest_posts to ensure homepage is first, then blog index, then others
    def sort_key(post):
        url = post['url']
        if url == "https://cursor-vip.pro/": return 0
        if url == "https://cursor-vip.pro/blog/" or url.endswith("/blog/index"): return 1
        if "/blog/" in url: return 2 # Articles
        return 3 # Static pages

    latest_posts.sort(key=sort_key)

    sitemap_gen = SitemapGenerator()

    for post in latest_posts:
        print(f"   - {post['title']} ({post['url']})")
        # Determine priority
        if post['url'] == "https://cursor-vip.pro/" or post['url'].endswith("/index") or post['url'] == "https://cursor-vip.pro/blog/":
            priority = 1.0 
        elif "/blog/" in post['url']:
            priority = 0.8
        else:
            priority = 0.8
            
        # Clean url for sitemap (ensure no index suffix for root)
        sitemap_url = post['url']
        if sitemap_url.endswith("/index"):
            sitemap_url = sitemap_url[:-6] # remove /index
            if not sitemap_url.endswith("/"): sitemap_url += "/" # ensure root has slash or not? usually https://domain.com
        
        # Use article date if available
        sitemap_gen.add_url(sitemap_url, priority, post.get('date'))

    print("🗺️ Generating sitemap.xml...")
    sitemap_gen.generate(os.path.join(ROOT_DIR, 'sitemap.xml'))
    
    print("🤖 Generating robots.txt...")
    robots_gen = RobotsGenerator()
    robots_gen.generate(os.path.join(ROOT_DIR, 'robots.txt'))

    print("✨ Build Complete!")

if __name__ == "__main__":
    main()
