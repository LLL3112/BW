import cloudscraper
from bs4 import BeautifulSoup
import csv
import datetime
import os
import time

BASE = "https://www.halooglasi.com"

CATEGORIES = {
    "prodaja": [
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/jednosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/jednoiposoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/dvosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/trosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/cetvorosoban",
        "/nekretnine/prodaja-stanova/beograd-savski-venac-beograd-na-vodi/petosoban-i-veci",
    ],
    "izdavanje": [
        "/nekretnine/izdavanje-stanova/beograd-savski-venac-beograd-na-vodi",
    ],
}

scraper = cloudscraper.create_scraper()


def parse_listing_card(card):
    try:
        naslov_tag = card.select_one(".product-title")
        naslov = naslov_tag.get_text(strip=True) if naslov_tag else ""

        link_tag = card.select_one("a")
        link = BASE + link_tag["href"] if link_tag and link_tag.get("href", "").startswith("/") else (link_tag["href"] if link_tag else "")

        cena_tag = card.select_one(".central-feature, .price")
        cena = cena_tag.get_text(strip=True) if cena_tag else ""

        features = card.select(".text-feature, .other-features li")
        kvadratura = ""
        sprat = ""
        for feat in features:
            txt = feat.get_text(strip=True)
            if "m2" in txt or "m²" in txt:
                kvadratura = txt
            if "sprat" in txt.lower():
                sprat = txt

        return {
            "naslov": naslov,
            "cena": cena,
            "kvadratura": kvadratura,
            "sprat": sprat,
            "link": link,
        }
    except Exception as e:
        return {"naslov": "GRESKA", "cena": str(e), "kvadratura": "", "sprat": "", "link": ""}


def scrape_category(path):
    listings = []
    page = 1
    while page <= 15:
        url = f"{BASE}{path}?page={page}"
        try:
            resp = scraper.get(url, timeout=30)
        except Exception as e:
            print(f"Greska pri ucitavanju {url}: {e}")
            break

        cards_check = BeautifulSoup(resp.text, "lxml").select(".product-item")
        print(f"STATUS: {resp.status_code}, DUZINA HTML: {len(resp.text)}, BROJ .product-item: {len(cards_check)}")

        if page == 1:
            print("PRVIH 3000 KARAKTERA HTML-a:")
            print(resp.text[:3000])

        if resp.status_code != 200:
            print(f"Status {resp.status_code} za {url}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".product-item")
        if not cards:
            break

        for card in cards:
            listings.append(parse_listing_card(card))
        page += 1
        time.sleep(2)
    return listings


def main():
    all_rows = []
    timestamp = datetime.datetime.utcnow().isoformat()

    for tip, paths in CATEGORIES.items():
        for path in paths:
            print(f"Skrejpujem: {path}")
            rows = scrape_category(path)
            for r in rows:
                r["tip_oglasa"] = tip
                r["scraped_at"] = timestamp
            all_rows.extend(rows)

    os.makedirs("data", exist_ok=True)
    fieldnames = ["naslov", "cena", "kvadratura", "sprat", "link", "tip_oglasa", "scraped_at"]

    dated_file = f"data/oglasi_{datetime.date.today().isoformat()}.csv"
    with open(dated_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    with open("data/latest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Gotovo. Ukupno oglasa: {len(all_rows)}")


if __name__ == "__main__":
    main()
