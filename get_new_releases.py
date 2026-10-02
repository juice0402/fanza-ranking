import os
import urllib.request
import urllib.parse
import json

# 環境変数から取得（ローカル実行用にデフォルト値も用意）
API_ID = os.environ.get("API_ID", "SEn7wgXp4VS0veFFZ05L")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID", "juice0402-990")

def fetch_fanza_new_releases():
    url = "https://api.dmm.com/affiliate/v3/ItemList"
    
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": "date",
        "hits": 20,
        "output": "json"
    }
    
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"
    
    req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            items = data.get("result", {}).get("items", [])
            item_list = []
            
            for rank, item in enumerate(items, 1):
                img_info = item.get("imageURL", {})
                image_url = img_info.get("large") or img_info.get("list") or img_info.get("small") or ""
                
                info = {
                    "no": rank,
                    "title": item.get("title"),
                    "url": item.get("affiliateURL"),
                    "image_url": image_url,
                    "date": item.get("date"),
                    "maker": item.get("iteminfo", {}).get("maker", [{}])[0].get("name", "不明"),
                    "actress": [a.get("name") for a in item.get("iteminfo", {}).get("actress", [])]
                }
                item_list.append(info)
                
            with open("new_releases.json", "w", encoding="utf-8") as f:
                json.dump(item_list, f, ensure_ascii=False, indent=2)
                
            print(f"✨ 成功！{len(item_list)}件の新着データを new_releases.json に保存したよ！")
            
    except Exception as e:
        print(f"❌ エラーが発生しちゃった: {e}")

if __name__ == "__main__":
    fetch_fanza_new_releases()
