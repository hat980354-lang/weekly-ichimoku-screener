# 東証全銘柄｜週足・一目均衡表 雲上抜けスクリーナー

iPad・iPhone・パソコンのブラウザから使えるStreamlitアプリです。

## 主な機能

- 東証プライム・スタンダード・グロースを対象
- 週足で雲を上抜けたばかりの銘柄を抽出
- 雲抜け後1〜5週を選択
- 出来高20週平均比で絞り込み
- 雲上限からの乖離率で絞り込み
- 転換線＞基準線
- 雲が上向き
- 200週線より上
- CSVダウンロード

## 公開に必要なファイル

- app.py
- requirements.txt
- .streamlit/config.toml

## Streamlit Community Cloudで公開

1. GitHubに新しいリポジトリを作成
2. このフォルダ内のファイルをすべてアップロード
3. Streamlit Community CloudへGitHubアカウントでログイン
4. Create app を選択
5. リポジトリを選び、Main file path に app.py を指定
6. Deploy を押す

公開後は `https://任意の名前.streamlit.app` のようなURLで利用できます。

## 注意

株価取得にはyfinanceを利用します。Yahoo Finance側の通信制限や仕様変更により、
一部銘柄を取得できない場合があります。売買前に必ずTradingView等で週足を確認してください。
