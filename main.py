
import requests
from bs4 import BeautifulSoup
import csv
import time
 
# ---- Setup ----
 
base_url = "http://books.toscrape.com/catalogue/page-{}.html"
 
# The site shows ratings as a CSS class like "star-rating Three".
# We map the word to a number so the CSV is easier to use.
rating_map = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5
}
 
all_books = []  # will hold one dict per book
 
# ---- Loop through all 50 listing pages ----
 
for page in range(1, 51):
    url = base_url.format(page)
 
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # raises an error if page didn't load (404, 500, etc.)
    except requests.exceptions.RequestException as e:
        print(f"Could not load page {page}: {e}")
        continue  # skip this page, move to the next one
 
    soup = BeautifulSoup(response.text, "html.parser")
    books = soup.find_all("article", class_="product_pod")
 
    # ---- Loop through each book on this page ----
    for book in books:
        try:
            title = book.h3.a['title']
 
            price_text = book.find("p", class_="price_color").text
            price = price_text.replace("£", "").strip()
 
            availability = book.find("p", class_="instock availability").text.strip()
 
            rating_tag = book.find("p", class_="star-rating")
            rating_classes = rating_tag['class']  # e.g. ['star-rating', 'Three']
            rating_word = rating_classes[1]
 
            if rating_word in rating_map:
                rating = rating_map[rating_word]
            else:
                rating = 0  # fallback if we don't recognise the word
 
            relative_link = book.h3.a['href']
            book_url = "http://books.toscrape.com/catalogue/" + relative_link.replace("../../../", "")
 
        except AttributeError as e:
            # Means some expected tag (like h3.a) wasn't found on this book
            print(f"Skipping a book on page {page}, missing data: {e}")
            continue
 
        # ---- Visit the book's own page to get genre and UPC ----
        genre = "Unknown"
        upc = "Unknown"
 
        try:
            detail_response = requests.get(book_url, timeout=10)
            detail_response.raise_for_status()
            detail_soup = BeautifulSoup(detail_response.text, "html.parser")
 
            breadcrumb = detail_soup.find("ul", class_="breadcrumb")
            crumbs = breadcrumb.find_all("li")
 
            # breadcrumb looks like: Home / Books / <Genre> / <Book Title>
            if len(crumbs) >= 3:
                genre = crumbs[2].text.strip()
 
            table_rows = detail_soup.find_all("tr")
            if len(table_rows) > 0:
                upc = table_rows[0].find("td").text.strip()
 
        except requests.exceptions.RequestException as e:
            print(f"Could not load detail page for '{title}': {e}")
        except AttributeError as e:
            print(f"Missing detail info for '{title}': {e}")
 
        all_books.append({
            "title": title,
            "price_gbp": price,
            "availability": availability,
            "rating": rating,
            "genre": genre,
            "upc": upc,
            "url": book_url
        })
 
    print(f"Page {page} done. Total books collected so far: {len(all_books)}")
    time.sleep(1)  # small pause so we don't hammer the server
 
# ---- Save everything to a CSV file ----
 
fieldnames = ["title", "price_gbp", "availability", "rating", "genre", "upc", "url"]
 
with open("books_data.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for book in all_books:
        writer.writerow(book)
 
print(f"Done! Saved {len(all_books)} books to books_data.csv")
