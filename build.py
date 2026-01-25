import os
import glob
from bs4 import BeautifulSoup
import sys
import datetime

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
            self._standardize_links(nav)

            # Ensure logo points to SVG if referenced
            logo_img = nav.find('img', alt=lambda x: x and 'logo' in x.lower())
            if logo_img:
                logo_img['src'] = '/assets/logo.png'
        return nav

    def get_footer(self):
        footer = self.soup.find('footer')
        if footer:
            self._standardize_links(footer)
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

    def _standardize_links(self, element):
        """Helper to ensure links and resources in an element are root-relative and clean."""
        # 1. Standardize Links (a tags)
        for a in element.find_all('a', href=True):
            href = a['href']
            
            # Skip external/special links
            if href.startswith(('http', '//', '#', 'mailto:', 'tel:', 'javascript:', 'data:')):
                continue

            # Clean URL: Remove .html suffix
            if href.endswith('.html'):
                href = href[:-5]
                if not href: href = '/' # index.html -> /
            
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
    def __init__(self, soup, metadata, favicons):
        self.soup = soup
        self.metadata = metadata
        self.favicons = favicons

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
            script_schema.string = str(s)
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
        return [{
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
            "datePublished": datetime.date.today().isoformat() # Ideally parse from content
        }]

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

    def inject_recommended(self):
        article = self.soup.find('article')
        if article:
            # Check if recommended section exists
            rec = article.find(id="recommended-reading")
            if not rec:
                rec_html = """
                <div id="recommended-reading" class="mt-12 pt-8 border-t border-slate-800">
                    <h3 class="text-xl font-bold text-white mb-4">推荐阅读</h3>
                    <ul class="space-y-2 text-slate-400">
                        <li><a href="/" class="hover:text-blue-400">返回首页</a></li>
                        <!-- Dynamic links could be added here -->
                    </ul>
                </div>
                """
                rec_soup = BeautifulSoup(rec_html, 'html.parser')
                article.append(rec_soup)

class SitemapGenerator:
    def __init__(self, base_url="https://cursor-vip.pro"):
        self.base_url = base_url
        self.urls = []

    def add_url(self, url, priority=0.8):
        self.urls.append({
            "loc": url,
            "lastmod": datetime.date.today().isoformat(),
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

    for post_path in all_files:
        is_index = os.path.basename(post_path) == 'index.html'
        print(f"🔨 Processing {os.path.basename(post_path)}...")
        
        with open(post_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # CLEAN UP LINKS IN CONTENT (Not just Nav/Footer)
        # This fixes the Audit warnings about .html extensions in the body content
        extractor._standardize_links(soup)

        # Metadata extraction (simple version)
        title_tag_find = soup.find('title')
        title = title_tag_find.get_text().strip() if title_tag_find else "Untitled"
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

        # Phase 2: Head Reconstruction
        # Note: We might want to be careful with index.html to not lose custom scripts not in preserved list
        # But HeadReconstructor preserves scripts/styles, so it should be fine.
        reconstructor = HeadReconstructor(soup, metadata, favicons)
        reconstructor.reconstruct()

        # Phase 3: Injection
        injector = ContentInjector(soup)
        
        # Don't inject Nav/Footer into index.html if it IS the source (avoid self-injection loop artifacts)
        # But actually, since we extracted clean versions, injecting them back ensures index.html is also standardized!
        # So we KEEP injection for all files.
        injector.inject_nav(nav)
        injector.inject_footer(footer)
        
        if not is_index:
             injector.inject_recommended()

        # Save
        with open(post_path, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
            
        latest_posts.append({"title": title, "url": url})

    # 4. Global Update (Homepage Latest Articles)
    # This part assumes there's a place to put them. For now, we'll just log it.
    print("📋 Latest Articles updated (in memory).")
    
    sitemap_gen = SitemapGenerator()

    for post in latest_posts:
        print(f"   - {post['title']} ({post['url']})")
        # Determine priority
        priority = 1.0 if post['url'] == "https://cursor-vip.pro/" or post['url'].endswith("/index") else 0.8
        # Clean url for sitemap (ensure no index suffix for root)
        sitemap_url = post['url']
        if sitemap_url.endswith("/index"):
            sitemap_url = sitemap_url[:-6] # remove /index
            if not sitemap_url.endswith("/"): sitemap_url += "/" # ensure root has slash or not? usually https://domain.com
        
        sitemap_gen.add_url(sitemap_url, priority)

    print("🗺️ Generating sitemap.xml...")
    sitemap_gen.generate(os.path.join(ROOT_DIR, 'sitemap.xml'))
    
    print("🤖 Generating robots.txt...")
    robots_gen = RobotsGenerator()
    robots_gen.generate(os.path.join(ROOT_DIR, 'robots.txt'))

    print("✨ Build Complete!")

if __name__ == "__main__":
    main()
