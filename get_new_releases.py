import os
import urllib.request
import urllib.parse
import json
import time

API_ID = os.environ.get("API_ID", "SEn7wgXp4VS0veFFZ05L")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID", "juice0402-990")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODEL_NAME = "gemini-3.6-flash"

def generate_ai_comment(title, actress, maker):
    if not GEMINI_API_KEY:
        return "注目の新作登場！要チェックです！"
        
    actress_str = ", ".join(actress) if actress else "注目の女優"
    prompt = f"以下のFANZA作品の魅力を引き立てる、思わず見たくなるような情熱的な紹介・見どころコメント（80〜120文字程度）を1つ作成してください。キャッチーで魅力的、かつ自然な日本語で書いてください。余計な挨拶や解説は不要で、コメント本文のみを出力してください。\n\nタイトル: {title}\n出演: {actress_str}\nメーカー: {maker}"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(data).encode('utf-8'), 
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                comment = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                return comment
        except urllib.error.HTTPError as e:
            if e.code in [429, 503]:
                time.sleep(5)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
            
    return "注目の新作登場！要チェックです！"

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
            
            print("🤖 AIコメント生成をスタートするよ...")
            for rank, item in enumerate(items, 1):
                img_info = item.get("imageURL", {})
                image_url = img_info.get("large") or img_info.get("list") or img_info.get("small") or ""
                
                title = item.get("title")
                maker = item.get("iteminfo", {}).get("maker", [{}])[0].get("name", "不明")
                actress = [a.get("name") for a in item.get("iteminfo", {}).get("actress", [])]
                
                ai_comment = generate_ai_comment(title, actress, maker)
                print(f"[{rank}/20] 生成完了 ➔ {ai_comment[:22]}...")
                
                time.sleep(3)

                info = {
                    "no": rank,
                    "title": title,
                    "url": item.get("affiliateURL"),
                    "image_url": image_url,
                    "date": item.get("date"),
                    "maker": maker,
                    "actress": actress,
                    "comment": ai_comment
                }
                item_list.append(info)
                
            # ルートと site/src/data/ の両方に保存！
            save_paths = ["new_releases.json", "site/src/data/new_releases.json"]
            for path in save_paths:
                os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(item_list, f, ensure_ascii=False, indent=2)
                
            print("\n✨ 保存完了！")
                
    except Exception as e:
        print(f"❌ エラーが発生しちゃった: {e}")

if __name__ == "__main__":
    fetch_fanza_new_releases()
