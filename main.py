import requests
from bs4 import BeautifulSoup
import csv
import time
import os

# --- Configuration ---

base_url = "http://books.toscrape.com/catalogue/page-{}.html"
progress_file = "progress.txt"  # tracks the last successfully scraped page
csv_file = "books_data.csv"

# Maps the star-rating CSS class word to its integer equivalent
rating_map = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5
}

all_books = []

# --- Determine starting page (supports resume on interrupted runs) ---

start_page = 1

if os.path.exists(progress_file):
    with open(progress_file, "r") as f:
        last_completed = f.read().strip()
    try:
        start_page = int(last_completed) + 1
        print(f"Resuming from page {start_page}")
    except ValueError:
        start_page = 1  # corrupted or empty progress file; restart from page 1

# --- Early exit if the full catalogue has already been scraped ---

if start_page > 50:
    print("All 50 pages already scraped. Nothing to do.")
    exit()

# --- Initialise the CSV file with headers if it doesn't exist yet ---

file_already_exists = os.path.exists(csv_file)
fieldnames = ["title", "price_gbp", "availability", "rating", "genre", "upc", "url"]

if not file_already_exists:
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

# --- Scrape each listing page and visit individual book pages for full details ---

for page in range(start_page, 51):
    url = base_url.format(page)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"  # force correct decoding; prevents £ being read as Â£
    except requests.exceptions.RequestException as e:
        print(f"Could not load page {page}: {e}")
        continue

    soup = BeautifulSoup(response.text, "html.parser")
    books = soup.find_all("article", class_="product_pod")

    page_books = []  # holds results for this page before writing to CSV

    for book in books:
        try:
            title = book.h3.a['title']
            price_text = book.find("p", class_="price_color").text
            price = price_text.replace("£", "").strip()
            availability = book.find("p", class_="instock availability").text.strip()

            rating_tag = book.find("p", class_="star-rating")
            rating_classes = rating_tag['class']
            rating_word = rating_classes[1]

            if rating_word in rating_map:
                rating = rating_map[rating_word]
            else:
                rating = 0  # fallback for any unrecognised rating class

            relative_link = book.h3.a['href']
            book_url = "http://books.toscrape.com/catalogue/" + relative_link.replace("../../../", "")

        except AttributeError as e:
            print(f"Skipping a book on page {page}, missing data: {e}")
            continue

        genre = "Unknown"
        upc = "Unknown"

        # Visit the book's detail page to extract genre and UPC
        try:
            detail_response = requests.get(book_url, timeout=10)
            detail_response.raise_for_status()
            detail_response.encoding = "utf-8"  # same encoding fix for detail pages
            detail_soup = BeautifulSoup(detail_response.text, "html.parser")

            breadcrumb = detail_soup.find("ul", class_="breadcrumb")
            crumbs = breadcrumb.find_all("li")
            if len(crumbs) >= 3:
                genre = crumbs[2].text.strip()  # breadcrumb: Home > Books > <Genre> > Title

            table_rows = detail_soup.find_all("tr")
            if len(table_rows) > 0:
                upc = table_rows[0].find("td").text.strip()

        except requests.exceptions.RequestException as e:
            print(f"Could not load detail page for '{title}': {e}")
        except AttributeError as e:
            print(f"Missing detail info for '{title}': {e}")

        page_books.append({
            "title": title,
            "price_gbp": price,
            "availability": availability,
            "rating": rating,
            "genre": genre,
            "upc": upc,
            "url": book_url
        })

    # Append this page's results to the CSV immediately to avoid data loss on interruption
    with open(csv_file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for book in page_books:
            writer.writerow(book)

    all_books.extend(page_books)

    # Record progress so the next run can resume from the following page
    with open(progress_file, "w") as f:
        f.write(str(page))

    print(f"Page {page} done. Total books collected so far: {len(all_books)}")
    time.sleep(1)  # brief delay to avoid hammering the server

print(f"Done! Scraped {len(all_books)} books this run.")
