import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import csv
from collections import deque
import pandas as pd
import re

class CatalogScraper:
    def __init__(self, start_url, output_filename="stonybrook_raw_data.csv", max_pages=50000):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.visited_urls = set()
        self.seen_chunks = set()
        self.max_pages = max_pages
        self.output_filename = output_filename
        self.chunk_counter = 1

        # Initialize raw CSV
        with open(self.output_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['_id', 'chunk_text'])

    def run_crawler(self):
        """Uses a Queue to crawl all links found in the HTML structure."""
        queue = deque([self.start_url])

        while queue and len(self.visited_urls) < self.max_pages:
            url = queue.popleft()

            if url in self.visited_urls:
                continue

            print(f"[+] Scraping ({len(self.visited_urls)+1}/{self.max_pages}): {url}")
            self.visited_urls.add(url)

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"[-] Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # === 1. GRAB ALL LINKS ===
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']

                if href.startswith(('mailto:', 'javascript:', '#', 'tel:')) or href.lower().endswith(('.pdf', '.jpg', '.png')):
                    continue

                full_url = urljoin(url, href).split('#')[0]

                if full_url not in self.visited_urls and full_url not in queue and urlparse(full_url).netloc == self.domain:
                    queue.append(full_url)

            # === 2. EXTRACT TEXT ===
            self._extract_and_save_content(soup)
            time.sleep(1)

    def _extract_and_save_content(self, soup):
        for unwanted in soup(['nav', 'header', 'footer', 'aside']):
            unwanted.extract()

        content_area = soup.find('main') or soup.find('div', id='content') or soup.body

        if not content_area:
            return

        h1_tag = content_area.find('h1')
        if h1_tag:
            current_header = ' '.join(h1_tag.get_text(strip=True).split())
        else:
            current_header = soup.title.get_text(strip=True) if soup.title else "Page Intro"

        current_paragraphs = []
        ignore_headers = ["Audiences", "About", "Admissions", "Academics", "Things to Do", "Resources", "Logins", "Info For"]

        for element in content_area.find_all(['h2', 'p']):
            if element.name == 'h2':
                self._save_chunk(current_header, current_paragraphs)

                new_header = ' '.join(element.get_text(strip=True).split())
                current_header = "Ignored Content" if new_header in ignore_headers else new_header
                current_paragraphs = []

            elif element.name == 'p':
                if current_header != "Ignored Content":
                    text = ' '.join(element.get_text(strip=True).split())
                    if text:
                        current_paragraphs.append(text)

        if current_header != "Ignored Content":
            self._save_chunk(current_header, current_paragraphs)

    def _save_chunk(self, header, paragraphs):
        if not paragraphs:
            return

        combined_paragraphs = " ".join(paragraphs)
        separator = " " if header.endswith(":") else ": "
        chunk_text = f"{header}{separator}{combined_paragraphs}"

        if chunk_text not in self.seen_chunks:
            self.seen_chunks.add(chunk_text)

            with open(self.output_filename, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                row_id = f"vec_{self.chunk_counter}"
                writer.writerow([row_id, chunk_text])

            self.chunk_counter += 1

# ==========================================
# NEW DATA CLEANING FUNCTION
# ==========================================
def clean_and_finalize_data(raw_csv, final_csv):
    print(f"\n[*] Starting data cleaning process on {raw_csv}...")
    df = pd.read_csv(raw_csv)
    df['chunk_text'] = df['chunk_text'].fillna('').astype(str)

    def clean_text(text):
        # 1. Remove hidden soft hyphens (fixes "Edu­ca­tion" to "Education")
        text = text.replace('\xad', '').replace('\u00ad', '')
        
        # 2. Fix missing spaces after punctuation (fixes "website.The" -> "website. The")
        text = re.sub(r'(?<=[.,!?])(?=[A-Za-z])', r' ', text)
        
        # 3. Fix missing spaces between lowercase and uppercase letters (fixes "EquityAdministration" -> "Equity Administration")
        text = re.sub(r'(?<=[a-z])(?=[A-Z])', r' ', text)
        
        # 4. Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # Apply the text cleaning
    df['chunk_text'] = df['chunk_text'].apply(clean_text)

    # Filter out chunks that are too short (< 15 words) or clearly gibberish
    initial_count = len(df)
    df = df[df['chunk_text'].str.split().str.len() >= 15]

    # Re-index the IDs so they are consecutive (vec_1, vec_2, vec_3...)
    df = df.reset_index(drop=True)
    df['_id'] = [f"vec_{i+1}" for i in range(len(df))]

    # Save final polished CSV
    df.to_csv(final_csv, index=False)
    
    print(f"[+] Cleaning complete!")
    print(f"    - Original rows: {initial_count}")
    print(f"    - Short/useless rows removed: {initial_count - len(df)}")
    print(f"    - Final clean rows saved to: {final_csv}")


if __name__ == "__main__":
    start_url = "https://catalog.stonybrook.edu/index.php"
    raw_file = "stonybrook_raw_data.csv"
    final_file = "stonybrook_pinecone_data.csv"

    scraper = CatalogScraper(start_url, output_filename=raw_file, max_pages=100000)

    print("Starting crawler. Press Ctrl+C to stop manually.")
    
    # Run the scraper
    scraper.run_crawler()
    
    # Run the cleaner immediately after
    clean_and_finalize_data(raw_csv=raw_file, final_csv=final_file) 