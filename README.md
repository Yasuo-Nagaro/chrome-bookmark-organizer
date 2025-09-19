# Chromeブックマーク整理ツール

## 1. ツールの概要

このツールは、Google ChromeからエクスポートしたブックマークファイルをGemini APIを利用して自動でカテゴリ分類し、整理された新しいブックマークファイルを生成するPythonスクリプトです。

大量のブックマークを手作業で整理する手間を省き、「開発 > Python」や「ニュース > 経済」のような階層構造で自動的にフォルダ分けします。

## 2. インストール方法

### a. Gemini APIキーの取得と設定

1.  [Google AI for Developers](https://ai.google.dev/gemini-api/docs/api-key?hl=ja)にアクセスし、APIキーを取得します。
2.  取得したAPIキーを環境変数 `GEMINI_API_KEY` に設定します。

    **macOS/Linuxの場合:**
    ```bash
    export GEMINI_API_KEY='YOUR_API_KEY'
    ```

    **Windows (PowerShell)の場合:**
    ```powershell
    $env:GEMINI_API_KEY='YOUR_API_KEY'
    ```
    （ターミナルを再起動すると設定がリセットされるため、恒久的に設定したい場合は `.zshrc` や `.bash_profile` などに追記してください）

### b. 依存関係のインストール

プロジェクトのルートディレクトリで以下のコマンドを実行し、必要なライブラリをインストールします。

```bash
`pip install -r requirements.txt`
```

## 3. 使い方

1.  **Chromeからブックマークをエクスポート**
    - Chromeを開き、ブックマークマネージャ（`chrome://bookmarks`）にアクセスします。
    - 右上のメニュー（︙）から「ブックマークをエクスポート」を選択し、HTMLファイルとして保存します（例: `bookmarks.html`）。

2.  **スクリプトを実行**
    ターミナルで以下のコマンドを実行します。引数には、先ほどエクスポートしたHTMLファイルのパスを指定してください。

    ```bash
    python main.py path/to/your/bookmarks.html
    ```

3.  **整理されたブックマークをインポート**
    - スクリプトが完了すると、`organized_bookmarks.html` というファイルが生成されます。
    - 再びChromeのブックマークマネージャを開き、右上のメニューから「ブックマークをインポート」を選択します。
    - 生成された `organized_bookmarks.html` を選択すると、カテゴリ分類されたフォルダ構造でブックマークがインポートされます。

## 4. カスタマイズ方法

分類のルールやカテゴリの粒度は、`main.py`内のプロンプトや変数を編集することで調整できます。

-   **編集箇所:**
    -   `main.py` ファイル内の `get_categories_batch` 関数

### a. カテゴリ階層の深さを変更する

`nest` 変数の数値を変更することで、カテゴリの最大階層を調整できます。例えば、`nest = 2` とすれば、`開発 > Python` のような2階層までが上限になります。

```python
# main.py の get_categories_batch 関数内
def get_categories_batch(bookmark_batch, existing_categories):
    # ...（略）...
    nest = 3 # <--- この数値を変更（例: 2）
    prompt = f"""
    あなたはブックマークの分類アシスタントです。
    # ...（略）...
```

### b. 分類ルール（プロンプト）を編集する

`prompt` 変数に格納されているGemini APIへの指示を書き換えることで、より詳細な分類ルールを設定できます。

-   **カスタマイズ例:**
    -   「カテゴリ名は必ず英語にしてください」といった指示を追加する。
    -   「IT技術関連のブックマークは特に細かく分類してください」のように、特定の分野に関する指示を追加する。
    -   特定のURL（社内ツールなど）を強制的に特定のカテゴリに割り当てるルールを追記する。

```python
# main.py の get_categories_batch 関数内

    # ...（略）...
    prompt = f"""
    あなたはブックマークの分類アシスタントです。
    以下の「既存のカテゴリスト」を参考に、指定された「ブックマークJSONリスト」を分類してください。

    # 最重要ルール
    - 回答は、必ず以下の形式のJSON配列のみを返してください。
    - 各オブジェクトには、入力と対応する「id」と、分類結果の「category」を含めてください。
    - カテゴリは最大{nest}階層です（例: '開発 > Python'）。
    - 既存カテゴリに合致するものを優先してください。
    - どのカテゴリにも分類が難しい場合は 'その他' としてください。
    - 回答にはJSON以外の余計なテキスト（"はい、承知しました..."など）を含めないでください。
    - カテゴリ名は必ず日本語にしてください。 # <--- このような指示を追加・変更

    # 回答JSON形式の例
    # ...（略）...
    """
    # ...（略）...
```

### c. 使用するAIモデルを変更する

スクリプトはデフォルトで `gemini-2.5-flash` を使用しています。より高精度なモデル（例: `gemini-2.5-pro`）に変更したい場合は、`generate_content` の呼び出し部分を編集してください。
（※モデルによって料金や速度が異なります）

```python
# main.py の get_categories_batch 関数内
    # ...（略）...
    try: 
        response = client.models.generate_content(
            model="gemini-2.5-flash", # <--- このモデル名を変更
            contents = prompt
        )
    # ...（略）...
```
