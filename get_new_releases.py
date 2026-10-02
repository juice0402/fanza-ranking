import os
import urllib.request
import urllib.parse
import json
import time
import random

API_ID = os.environ.get("API_ID", "SEn7wgXp4VS0veFFZ05L")
AFFILIATE_ID = os.environ.get("AFFILIATE_ID", "juice0402-990")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODEL_NAME = "gemini-3.6-flash"

# セーフティで弾かれた時の予備文章（ランダムで変化をつけて自然に！）
FALLBACK_COMMENTS = [
    "話題の最新作！キャストの美しさと魅力がギュッと詰まった必見の一作です✨",
    "注目の新着タイトル！期待を裏切らない見ごたえ十分のストーリー展開🔥",
    "いま一番チェックしたい注目作品！圧倒的な世界観と映像美を楽しめます💖",
    "ファン必見の最新リリース！見どころ満載で満足度の高い仕上がりです🌟"
]

def generate_ai_comment(title, actress, maker):
    if not GEMINI_API_KEY:
        return random.choice(FALLBACK_COMMENTS)
        
    actress_str = ", ".join(actress) if actress else "注目の女優"
    
    # セーフティを徹底回避しつつ魅力を上品＆ドラマチックに伝えるプロンプト！
    prompt = (
        f"以下の映像作品の魅力を伝える、思わず見たくなるような情熱的な紹介レビュー（80〜100文字程度）を作成してください。\n"
        f"【重要ルール】過激・直接的な単語や性表現は一切使用せず、上品・ドラマチック・魅力的な言葉遣いで、作品の雰囲気やキャストの美しさを引き立ててください。挨拶や解説は不要で、コメント本文のみを出力してください。\n\n"
        f"タイトル: {title}\n"
        f"出演: {actress_str}\n"
        f"メーカー: {maker}"
    )

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
                
                candidates = res_data.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts and 'text' in parts[0]:
                        comment_text = parts[0]['text'].strip()
                        if comment_text:
                            return comment_text
                return random.choice(FALLBACK_COMMENTS)
                
        except urllib.error.HTTPError as e:
            if e.code in [429, 503]:
                wait_time = 10 * (attempt + 1)
                print(f"⏳ 混雑中(HTTP {e.code})… {wait_time}秒休憩して再挑戦するよ！ ({attempt+1}/3)")
                time.sleep(wait_time)
            else:
                time.sleep(2)
        except Exception as e:
            time.sleep(2)
            
    return random.choice(FALLBACK_COMMENTS)

def fetch_fanza_new_releases():
    url = "https://api.dmm.com/affiliate/v3/ItemList"
    
    # 更新件数を10件に設定！
    params = {
        "api_id": API_ID,
        "affiliate_id": AFFILIATE_ID,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": "date",
        "hits": 10,
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
                print(f"[{rank}/10] 生成完了 ➔ {ai_comment[:22]}...")
                
                time.sleep(5)

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
