import time, json, re
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URLS_FILE = "urls.txt"
OUT_DIR = Path("transcripts_raw")
OUT_DIR.mkdir(exist_ok=True)

def slugify(s, maxlen=80):
    s = re.sub(r"[^\w\s-]", "", s).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:maxlen] if s else "untitled"

def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

    urls = [u.strip() for u in open(URLS_FILE, "r", encoding="utf-8") if u.strip()]
    combined_path = Path("combined.jsonl")
    if combined_path.exists():
        combined_path.unlink()

    for i, url in enumerate(urls, 1):
        driver.get(url)
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "lxml")
        title = soup.title.string if soup.title else f"Transcript {i}"
        text = soup.get_text("\n", strip=True)

        fname = f"{i:04d}_{slugify(title)}.txt"
        out_path = OUT_DIR / fname
        out_path.write_text(text, encoding="utf-8")

        row = {"index": i, "url": url, "title": title, "path": str(out_path), "text": text}
        with open(combined_path, "a", encoding="utf-8") as jf:
            jf.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(f"Saved {fname}")

    driver.quit()
    print("Done.")

if __name__ == "__main__":
    main()
