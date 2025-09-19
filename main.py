from google import genai
from bs4 import BeautifulSoup
from datetime import datetime

import os
import sys
import time
import json

# ---- Gemini APIの設定 ----
try:
    #事前にAPI キーをローカルで環境変数 GEMINI_API_KEY として要設定" https://ai.google.dev/gemini-api/docs/api-key?hl=ja
    client = genai.Client()
except Exception as e:
    print(f"Gemini APIの初期化中にエラーが発生しました: {e}")
    sys.exit(1)

# --- HTMLからブックマーク（URL)を抽出 ---
def extract_bookmarks_from_html(html_content):
    """BeautifulSoupを使用してHTMLからブックマーク（URLと名前）を抽出する"""
    bookmarks = []
    # 高速なlxmlパーサーを使用
    soup = BeautifulSoup(html_content, 'lxml')
    
    # <DT><A ...> タグを探す
    for dt_tag in soup.find_all('dt'):
        a_tag = dt_tag.find('a', href=True)
        if a_tag:
            url = a_tag['href']
            # javascript: や data: スキームを除外
            if url and not url.lower().startswith(('javascript:', 'data:', 'place:')):
                name = a_tag.get_text(strip=True) or "名前なし"
                bookmarks.append({"name": name, "url": url})
                
    return bookmarks
            
# ---- Gemini APIでカテゴリ判定 ---
def get_categories_batch(bookmark_batch, existing_categories):
    """Gemini APIを使用してブックマークの「バッチ」のカテゴリを判定する。既存のカテゴリリストを渡し、可能な限り再利用を促す。JSON形式でレスポンスを取得する"""
    
  # 既存のカテゴリストを整形
    if not existing_categories:
        category_list_str = "（まだありません）"
    else:
        # 既存のカテゴリを改行区切りでリストアップ
        category_list_str = "\n".join(f"- {cat}" for cat in existing_categories)
        
    # AIに入力するためのJSON文字列を作成 (IDを付与)
    bookmarks_json_list = []
    for i, bookmark in enumerate(bookmark_batch):
        # AIが処理しやすいよう、id, name, url を持つオブジェクトにする
        bookmarks_json_list.append({
            "id": i, # このIDはバッチ内でのインデックス
            "name": bookmark["name"],
            "url": bookmark["url"]
        })
    
    # ensure_ascii=False で日本語がエスケープされないようにする
    bookmarks_json_str = json.dumps(bookmarks_json_list, indent=2, ensure_ascii=False)
    
    # バッチ処理専用のJSONレスポンスプロンプト
    prompt = f"""
    あなたはブックマークの分類アシスタントです。
    以下の「既存のカテゴリスト」を参考に、指定された「ブックマークJSONリスト」を分類してください。

    # 最重要ルール
    - 回答は、必ず以下の形式のJSON配列のみを返してください。
    - 各オブジェクトには、入力と対応する「id」と、分類結果の「category」を含めてください。
    - カテゴリは最大3階層です（例: '開発 > Python'）。
    - 既存カテゴリに合致するものを優先してください。
    - どのカテゴリにも分類が難しい場合は 'その他' としてください。
    - 回答にはJSON以外の余計なテキスト（"はい、承知しました..."など）を含めないでください。

    # 回答JSON形式の例
    [
      {{"id": 0, "category": "開発 > Python"}},
      {{"id": 1, "category": "ニュース > 経済"}}
    ]

    # 既存のカテゴリスト
    {category_list_str}

    # ブックマークJSONリスト
    {bookmarks_json_str}

    # 回答 (JSON配列のみ)
    """

        
    try: 
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents = prompt
        )
        response_text = response.text.strip()
        
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        # JSON文字列をPythonの辞書リストにパース
        results = json.loads(response_text)
        
        # 3階層を超えないように制限（念のため）
        cleaned_results = []
        for res in results:
            if "category" in res and "id" in res:
                parts = [part.strip() for part in res["category"].split('>') if part.strip()][:3]
                limited_category = ' > '.join(parts)
                cleaned_results.append({
                    "id": res["id"],
                    "category": limited_category or "その他"
                })
        return cleaned_results
    
    except Exception as e:
        print(f"  [APIバッチエラー] バッチ全体の処理に失敗しました: {e}")
        print(f"  [エラー応答] {response_text[:200]}...") # エラー時の応答を一部表示
        # バッチ全体が失敗したため、全件を「その他」として返す
        return [{"id": i, "category": "その他"} for i in range(len(bookmark_batch))]

# --- カテゴリ構造からHTML（インポート形式）を生成 ---
def build_html_recursive(folder_structure, indent_level=1):
    """
    カテゴリの辞書構造から再帰的にHTMLを構築する
    新しい構造: {"フォルダ名": {"_bookmarks_": [...], "サブフォルダ": {...}}}
    """
    html_content = ""
    indent = "    " * indent_level # インデントを半角スペース4つに統一
    
    # 1. まず、その階層にあるブックマーク（_bookmarks_）を先に追加する
    if "_bookmarks_" in folder_structure:
        for item in folder_structure["_bookmarks_"]:
            safe_url = item['url'].replace("&", "&amp;").replace("\"", "&quot;")
            safe_name = item['name'].replace("<", "&lt;").replace(">", "&gt;")
            html_content += f"{indent}<DT><A HREF=\"{safe_url}\">{safe_name}</A>\n"

    # 2. 次に、サブフォルダを処理する
    for name, content in sorted(folder_structure.items()):
        if name == "_bookmarks_":
            continue # ブックマークは処理済みなのでスキップ
            
        if isinstance(content, dict): # サブフォルダは必ず辞書
            html_content += f"{indent}<DT><H3>{name}</H3>\n"
            html_content += f"{indent}<DL><p>\n"
            html_content += build_html_recursive(content, indent_level + 1)
            html_content += f"{indent}</DL><p>\n"
            
    return html_content

def create_bookmark_html(categorized_bookmarks, output_filename="organized_bookmarks.html"):
    """
    カテゴリ分類されたブックマークデータから、Chromeインポート用のHTMLファイルを生成する
    """
    
    organized_data = {}
    for category_path, bookmarks in categorized_bookmarks.items():
        parts = category_path.split(' > ')
        current_level = organized_data
        
        for i, part in enumerate(parts):
            # フォルダ（辞書）がなければ作成する
            if part not in current_level:
                current_level[part] = {}
            
            # 次の階層（フォルダ）へ移動する
            current_level = current_level[part]

            # もし最後の階層（パート）なら、そこにブックマークを追加する
            if i == len(parts) - 1:
                if "_bookmarks_" not in current_level:
                    current_level["_bookmarks_"] = []
                # ここで .extend を呼び出すのは current_level["_bookmarks_"] (リスト)
                current_level["_bookmarks_"].extend(bookmarks)


    # HTMLを構築
    html_header = f"""<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Organized Bookmarks (Generated by Gemini)</TITLE>
<H1>Organized Bookmarks {datetime.now().strftime('%Y-%m-%d')}</H1>
<DL><p>
"""
    
    html_body = build_html_recursive(organized_data)
    html_footer = "</DL><p>\n"
    
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html_header + html_body + html_footer)
        print(f"\n完了: ブックマークが '{output_filename}' にエクスポートされました。")
        print("Chromeの [ブックマーク マネージャ] -> [︙] -> [ブックマークをインポート] からこのファイルをインポートしてください。")
    except IOError as e:
        print(f"\nエラー: ファイルの書き出しに失敗しました: {e}")

# --- バッチ処理用のヘルパー関数 ---
def create_batches(items, batch_size):
    """リストを指定されたサイズのバッチ（小さなリスト）に分割するジェネレータ"""
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]

# --- メイン処理 ---
def main():
    if len(sys.argv) < 2:
        print("エラー: 処理対象のブックマークHTMLファイル名を指定してください。")
        sys.exit(1)

    input_filename = sys.argv[1]
    if not os.path.exists(input_filename):
        print(f"エラー: ファイルが見つかりません: {input_filename}")
        sys.exit(1)

    print(f"入力ファイル: {input_filename} を読み込みます。")
    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            html_content = f.read()
    except Exception as e:
        print(f"ファイルの読み込みに失敗しました: {e}")
        return

    all_bookmarks = extract_bookmarks_from_html(html_content)

    if not all_bookmarks:
        print("対象のブックマーク（リンク）が見つかりませんでした。")
        return

    print(f"合計 {len(all_bookmarks)} 件のブックマークを検出しました。")
    print("Gemini APIによるバッチ分類を開始します...")

    # --- ★バッチ処理設定 ---
    BATCH_SIZE = 200      # 1回のリクエストに含めるブックマーク数 (トークン上限に応じて調整)
    BATCH_DELAY = 5    # バッチ間の待機時間(秒) (TPM/RPM制限回避のため)
    # -------------------------

    categorized_bookmarks = {}
    total_processed = 0
    
    # ブックマークリストをバッチに分割
    batches = list(create_batches(all_bookmarks, BATCH_SIZE))
    num_batches = len(batches)
    
    for i, batch in enumerate(batches):
        print(f"\n--- バッチ {i+1}/{num_batches} ( {len(batch)} 件) を処理中 ---")
        
        # API呼び出し時点での既存カテゴリリストを取得
        existing_categories = list(categorized_bookmarks.keys())
        
        # ★バッチ関数を呼び出し
        batch_results = get_categories_batch(batch, existing_categories)

            
        # バッチの結果を処理
        for result in batch_results:
            try:
                # result は {"id": 0, "category": "開発 > Python"}
                
                # 'id' はバッチ内でのインデックス
                bookmark_index = result["id"] 
                category = result["category"]
                
                # 元のブックマーク情報を取得
                original_bookmark = batch[bookmark_index]
                
                print(f"  -> [{category}] {original_bookmark['name'][:50]}")

                if category not in categorized_bookmarks:
                    categorized_bookmarks[category] = []
                categorized_bookmarks[category].append(original_bookmark)
                
            except (KeyError, IndexError, TypeError) as e:
                print(f"  [結果パースエラー] {e} - 不正な結果: {result}")
                # エラー時は「その他」に分類
                if "その他" not in categorized_bookmarks:
                    categorized_bookmarks["その他"] = []
                # `bookmark_index` が取得できていれば、それを「その他」に入れる
                if 'bookmark_index' in locals() and bookmark_index < len(batch):
                     categorized_bookmarks["その他"].append(batch[bookmark_index])

        total_processed += len(batch)
        print(f"--- バッチ {i+1} 完了。 (合計 {total_processed}/{len(all_bookmarks)} 件処理) ---")
        
        # 最後のバッチ以外は待機 (TPM/RPM制限対策)
        if i < num_batches - 1:
            print(f"TPM/RPM制限回避のため {BATCH_DELAY} 秒待機します...")
            time.sleep(BATCH_DELAY)

    create_bookmark_html(categorized_bookmarks, "organized_bookmarks.html")

if __name__ == "__main__":
    main()