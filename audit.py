import os
import glob
import re
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
from urllib.parse import urlparse, urljoin

# Initialize colorama
init(autoreset=True)

# Configuration
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(ROOT_DIR, 'index.html')

class AuditConfig:
    def __init__(self):
        self.base_url = None
        self.keywords = []
        self.ignore_paths = ['.git', 'node_modules', '__pycache__', '.DS_Store']
        self.ignore_urls = ['/go/', 'cdn-cgi', 'javascript:', 'mailto:', '#', 'tel:']
        self.ignore_files = ['google', '404.html']
        self._load_from_index()

    def _load_from_index(self):
        if not os.path.exists(INDEX_FILE):
            print(f"{Fore.RED}[ERROR] index.html not found! Cannot auto-configure.{Style.RESET_ALL}")
            return

        try:
            with open(INDEX_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                soup = BeautifulSoup(f, 'html.parser')
                
                # Base URL
                canonical = soup.find('link', rel='canonical')
                if canonical and canonical.get('href'):
                    self.base_url = canonical['href'].rstrip('/')
                else:
                    og_url = soup.find('meta', property='og:url')
                    if og_url and og_url.get('content'):
                        self.base_url = og_url['content'].rstrip('/')
                    else:
                        print(f"{Fore.YELLOW}[WARN] No Base URL found (canonical/og:url). Defaulting to empty.{Style.RESET_ALL}")

                # Keywords
                kw_meta = soup.find('meta', attrs={'name': 'keywords'})
                if kw_meta and kw_meta.get('content'):
                    self.keywords = [k.strip() for k in kw_meta['content'].split(',')]

        except Exception as e:
            print(f"{Fore.RED}[ERROR] Failed to parse index.html config: {e}{Style.RESET_ALL}")

    def should_ignore_path(self, path):
        return any(ignore in path for ignore in self.ignore_paths)

    def should_ignore_file(self, filename):
        return any(ignore in filename for ignore in self.ignore_files)

    def should_ignore_url(self, url):
        return any(url.startswith(ignore) or ignore in url for ignore in self.ignore_urls)

class SEOAuditor:
    def __init__(self, config):
        self.config = config
        self.files = []
        self.internal_links = {} # target -> [sources]
        self.external_links = set()
        self.score = 100
        self.issues = []

    def scan_files(self):
        print(f"{Fore.CYAN}[INFO] Scanning files...{Style.RESET_ALL}")
        for root, dirs, files in os.walk(ROOT_DIR):
            # Ignore directories
            dirs[:] = [d for d in dirs if not self.config.should_ignore_path(os.path.join(root, d))]
            
            for file in files:
                if file.endswith('.html') and not self.config.should_ignore_file(file):
                    self.files.append(os.path.join(root, file))
        print(f"{Fore.GREEN}[SUCCESS] Found {len(self.files)} HTML files.{Style.RESET_ALL}")

    def audit_file(self, filepath):
        rel_path = os.path.relpath(filepath, ROOT_DIR)
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'html.parser')

            # C. Semantics
            self._check_semantics(soup, rel_path)

            # Link Analysis
            for a in soup.find_all('a', href=True):
                href = a['href'].strip()
                if not href or self.config.should_ignore_url(href):
                    continue

                if href.startswith(('http://', 'https://')):
                    # Check if it's actually internal (based on base_url)
                    if self.config.base_url and href.startswith(self.config.base_url):
                        path = href[len(self.config.base_url):]
                        self._analyze_internal_link(path, rel_path, soup)
                        self._add_issue('WARN', f"Internal link uses absolute URL: {href}", rel_path, -2)
                    else:
                        self.external_links.add(href)
                        # Check noopener/nofollow
                        rel = a.get('rel', [])
                        if 'noopener' not in rel:
                             # Just a minor check, maybe not worth penalizing heavily unless strictly required
                             pass
                else:
                    self._analyze_internal_link(href, rel_path, soup)

        except Exception as e:
            self._add_issue('ERROR', f"Failed to process file: {e}", rel_path, 0)

    def _check_semantics(self, soup, rel_path):
        # H1 Check
        h1s = soup.find_all('h1')
        if len(h1s) == 0:
            self._add_issue('ERROR', "Missing <h1> tag", rel_path, -5)
        elif len(h1s) > 1:
            self._add_issue('WARN', "Multiple <h1> tags found", rel_path, -2)

        # Schema Check
        schema = soup.find('script', type='application/ld+json')
        if not schema:
            self._add_issue('WARN', "Missing Schema (application/ld+json)", rel_path, -2)

    def _analyze_internal_link(self, href, source_path, soup):
        # Clean URL Check
        if href.endswith('.html') or href.endswith('.htm'):
             self._add_issue('WARN', f"Link contains .html extension: {href}", source_path, -2)
        
        # Relative vs Absolute Check
        if not href.startswith('/'):
             self._add_issue('WARN', f"Link uses relative path: {href}", source_path, -2)
             # Resolve to absolute for checking existence
             # This is tricky without a proper web server context, but we can approximate
             # For now, let's assume root-relative is the standard and required
        
        # Dead Link Check (Local Mapping)
        # 1. Normalize href to absolute local path
        target_path = href.split('#')[0].split('?')[0] # Remove fragment/query
        
        if target_path.startswith('/'):
            local_target = os.path.join(ROOT_DIR, target_path.lstrip('/'))
        else:
            # Handle relative paths for existence check
            source_dir = os.path.dirname(os.path.join(ROOT_DIR, source_path))
            local_target = os.path.join(source_dir, target_path)
        
        # Check possibilities
        exists = False
        
        # Case 1: Direct file
        if os.path.isfile(local_target):
            exists = True
        # Case 2: .html appended
        elif os.path.isfile(local_target + '.html'):
            exists = True
        # Case 3: index.html inside directory
        elif os.path.isdir(local_target) and os.path.isfile(os.path.join(local_target, 'index.html')):
            exists = True
            
        if not exists:
            self._add_issue('ERROR', f"Dead link detected: {href}", source_path, -10)
        else:
            # Record for Orphan check (using normalized cleaned path as key)
            # We use the relative path of the target file as the key
            normalized_key = None
            if os.path.isfile(local_target):
                normalized_key = os.path.relpath(local_target, ROOT_DIR)
            elif os.path.isfile(local_target + '.html'):
                normalized_key = os.path.relpath(local_target + '.html', ROOT_DIR)
            elif os.path.isdir(local_target) and os.path.isfile(os.path.join(local_target, 'index.html')):
                normalized_key = os.path.relpath(os.path.join(local_target, 'index.html'), ROOT_DIR)
            
            if normalized_key:
                if normalized_key not in self.internal_links:
                    self.internal_links[normalized_key] = []
                self.internal_links[normalized_key].append(source_path)

    def check_external_links(self):
        print(f"{Fore.CYAN}[INFO] Checking {len(self.external_links)} external links (Async)...{Style.RESET_ALL}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(self._check_url, url): url for url in self.external_links}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    code = future.result()
                    if code >= 400:
                        self._add_issue('ERROR', f"External dead link ({code}): {url}", "GLOBAL", -5)
                except Exception as exc:
                    self._add_issue('WARN', f"External check failed: {url} ({exc})", "GLOBAL", 0)

    def _check_url(self, url):
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SEOAuditor/1.0)'}
        r = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        return r.status_code

    def check_orphans(self):
        print(f"{Fore.CYAN}[INFO] Checking for orphan pages...{Style.RESET_ALL}")
        for file in self.files:
            rel_path = os.path.relpath(file, ROOT_DIR)
            if rel_path == 'index.html' or self.config.should_ignore_file(rel_path):
                continue
            
            if rel_path not in self.internal_links:
                self._add_issue('WARN', f"Orphan page (0 inbound links)", rel_path, -5)

    def _add_issue(self, level, message, context, penalty):
        self.issues.append({
            'level': level,
            'message': message,
            'context': context
        })
        self.score += penalty
        color = Fore.RED if level == 'ERROR' else Fore.YELLOW
        print(f"{color}[{level}] {context}: {message} ({penalty}){Style.RESET_ALL}")

    def generate_report(self):
        self.score = max(0, self.score)
        print("\n" + "="*50)
        print(f"{Fore.WHITE}{Style.BRIGHT}SEO AUDIT REPORT{Style.RESET_ALL}")
        print("="*50)
        
        print(f"Base URL: {self.config.base_url}")
        print(f"Files Scanned: {len(self.files)}")
        print(f"External Links: {len(self.external_links)}")
        
        print("\nTop Issues:")
        # Sort issues by severity (ERROR first)
        sorted_issues = sorted(self.issues, key=lambda x: 0 if x['level'] == 'ERROR' else 1)
        for i, issue in enumerate(sorted_issues[:10]): # Show top 10
            color = Fore.RED if issue['level'] == 'ERROR' else Fore.YELLOW
            print(f"{i+1}. {color}[{issue['level']}] {issue['context']}: {issue['message']}{Style.RESET_ALL}")
            
        if len(self.issues) > 10:
            print(f"... and {len(self.issues) - 10} more issues.")

        print("\n" + "-"*50)
        score_color = Fore.GREEN if self.score >= 90 else (Fore.YELLOW if self.score >= 70 else Fore.RED)
        print(f"FINAL SCORE: {score_color}{self.score}/100{Style.RESET_ALL}")
        print("-"*50)
        
        if self.score < 100:
            print(f"{Fore.CYAN}💡 Suggestion: Run 'python3 build.py' to fix standardization issues.{Style.RESET_ALL}")

def main():
    config = AuditConfig()
    auditor = SEOAuditor(config)
    
    auditor.scan_files()
    
    for file in auditor.files:
        auditor.audit_file(file)
        
    auditor.check_orphans()
    auditor.check_external_links()
    
    auditor.generate_report()

if __name__ == "__main__":
    main()
