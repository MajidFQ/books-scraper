import requests
from bs4 import BeautifulSoup
import time
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError

# --- Configuration ---

load_dotenv()  # loads variables from .env into the environment

base_url = "http://books.toscrape.com/catalogue/page-{}.html"
progress_file = "progress.txt"

# --- MongoDB connection ---

mongo_uri = os.getenv("MONGO_URI")

if not mongo_uri:
    print("Error: MONGO_URI is not set. Create a .env file with your MongoDB connection string.")
    print("See .env.example for the required format.")
    exit(1)

try:
    client = MongoClient(mongo_uri)
    client.admin.command("ping")  # verify the connection is reachable
    print("Connected to MongoDB Atlas successfully.")
except ConnectionFailure as e:
    print(f"Could not connect to MongoDB: {e}")
    exit(1)

db = client["books_scraper"]        # database name
collection = db["books"]            # collection name (like a "table")

# NEW: make sure "upc" can never be duplicated in this collection
collection.create_index("upc", unique=True)

rating_map = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5
}

all_books = []

# ---- Figure out where to start from ----

start_page = 1

if os.path.exists(progress_file):
    with open(progress_file, "r") as f:
        last_completed = f.read().strip()
    try:
        start_page = int(last_completed) + 1
        print(f"Resuming from page {start_page}")
    except ValueError:
        start_page = 1

if start_page > 50:
    print("All 50 pages already scraped. Nothing to do.")
    exit()

# ---- Loop through pages ----

for page in range(start_page, 51):
    url = base_url.format(page)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Could not load page {page}: {e}")
        continue

    soup = BeautifulSoup(response.text, "html.parser")
    books = soup.find_all("article", class_="product_pod")

    page_books = []

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
                rating = 0

            relative_link = book.h3.a['href']
            book_url = "http://books.toscrape.com/catalogue/" + relative_link.replace("../../../", "")

        except AttributeError as e:
            print(f"Skipping a book on page {page}, missing data: {e}")
            continue

        genre = "Unknown"
        upc = "Unknown"

        try:
            detail_response = requests.get(book_url, timeout=10)
            detail_response.raise_for_status()
            detail_soup = BeautifulSoup(detail_response.text, "html.parser")

            breadcrumb = detail_soup.find("ul", class_="breadcrumb")
            crumbs = breadcrumb.find_all("li")
            if len(crumbs) >= 3:
                genre = crumbs[2].text.strip()

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

    # ---- NEW: insert this page's books into MongoDB, skip duplicates ----
    for book in page_books:
        try:
            collection.insert_one(book)
        except DuplicateKeyError:
            print(f"'{book['title']}' already in database, skipping.")

    all_books.extend(page_books)

    with open(progress_file, "w") as f:
        f.write(str(page))

    print(f"Page {page} done. Total books collected so far: {len(all_books)}")
    time.sleep(1)

print(f"Done! Scraped {len(all_books)} books this run.")
print(f"Total books now in database: {collection.count_documents({})}")