import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import csv
from collections import deque

class CatalogScraper:
    def __init__(self, start_url, output_filename="stonybrook_pinecone_data.csv", max_pages=2000):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.visited_urls = set()
        self.seen_chunks = set()
        self.max_pages = max_pages
        self.output_filename = output_filename
        self.chunk_counter = 1

        # Initialize CSV
        with open(self.output_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['_id', 'chunk_text'])

    def run_crawler(self):
        """Uses a Queue to crawl all links found in the HTML structure."""
        # Initialize our queue with the starting URL
        queue = deque([self.start_url])

        while queue and len(self.visited_urls) < self.max_pages:
            # Get the next URL from the front of the line
            url = queue.popleft()

            # Skip if we've already visited it
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

            # Parse the raw HTML exactly as it came from the server
            soup = BeautifulSoup(response.text, 'html.parser')

            # === 1. GRAB ALL LINKS VISIBLE IN THE HTML STRUCTURE ===
            # Because we do this BEFORE extracting any tags, it finds links in the headers,
            # footers, sidebars, hidden dropdowns, and main text.
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']

                # Skip emails, phone numbers, javascript, and files
                if href.startswith(('mailto:', 'javascript:', '#', 'tel:')) or href.lower().endswith(('.pdf', '.jpg', '.png')):
                    continue

                full_url = urljoin(url, href).split('#')[0]

                # If it's on our domain, hasn't been visited, and isn't already in the queue, add it!
                if full_url not in self.visited_urls and full_url not in queue and urlparse(full_url).netloc == self.domain:
                    queue.append(full_url)

            # === 2. EXTRACT AND SAVE THE ACADEMIC CONTENT ===
            self._extract_and_save_content(soup)

            # Politeness delay so Stony Brook doesn't block your IP
            time.sleep(1)

    def _extract_and_save_content(self, soup):
        """Cleans the HTML and extracts the H2/P tag chunks."""
        # Now that we safely queued all the links, we can destroy the menus
        # so they don't pollute your Pinecone CSV data.
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
        """Formats and deduplicates chunks before writing to CSV."""
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

if __name__ == "__main__":
    start_url = "https://catalog.stonybrook.edu/index.php"

    # 2000 pages should be more than enough to cover the catalog
    scraper = CatalogScraper(start_url, output_filename="stonybrook_pinecone_data.csv", max_pages=2000)

    print("Starting crawler. Press Ctrl+C to stop manually.")
    scraper.run_crawler()
    print(f"\nFinished! Data saved to stonybrook_pinecone_data.csv")