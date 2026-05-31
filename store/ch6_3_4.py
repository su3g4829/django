import re
from html.parser import HTMLParser
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


TEST_URL = "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=10072806"


class MomoPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = {}
        self.text_parts = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            value = attrs.get("content")
            if key and value:
                self.meta[key] = value

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        text = data.strip()
        if text:
            self.text_parts.append(text)


def first_match(pattern, text, flags=0, default=""):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else default


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip()


def clean_price(text):
    return text.replace(",", "").replace("$", "").strip()


def fetch_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.momoshop.com.tw/",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")
        return response.status, html


def extract_product_info(html):
    parser = MomoPageParser()
    parser.feed(html)

    page_title = parser.title.strip() or first_match(r"<title>(.*?)</title>", html, re.I | re.S)
    og_title = parser.meta.get("og:title", "").strip()
    meta_price = parser.meta.get("product:price:amount", "").strip() or parser.meta.get("og:price:amount", "").strip()
    meta_description = parser.meta.get("og:description", "").strip() or parser.meta.get("description", "").strip()
    visible_text = normalize_text(" ".join(parser.text_parts))

    product_name = og_title or page_title.split("-momo")[0].strip()
    promo_price = clean_price(meta_price) or first_match(r"([0-9,]+)\s*元", visible_text, default="")

    return {
        "product_name": product_name,
        "price": promo_price,
        "description": meta_description,
        "page_title": page_title,
    }


def main():
    try:
        status_code, html = fetch_html(TEST_URL)
    except HTTPError as err:
        print("HTTP 錯誤：", err.code, err.reason)
        raise SystemExit(1)
    except URLError as err:
        print("連線失敗：", err.reason)
        raise SystemExit(1)
    except Exception as err:
        print("抓取失敗：", err)
        raise SystemExit(1)

    print(f"HTTP 狀態碼：{status_code}")
    if status_code != 200:
        print("頁面沒有成功取得，請先檢查網址或網站是否阻擋。")
        raise SystemExit(1)

    product = extract_product_info(html)

    print("商品名稱：", product["product_name"] or "未取得")
    print("價格：", f"{product['price']} 元" if product["price"] else "未取得")
    print("描述：", product["description"] or "未取得")


if __name__ == "__main__":
    main()
