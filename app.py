# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import time
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="東証｜週足雲抜けスクリーナー",
    page_icon="☁️",
    layout="wide",
)

JPX_PAGES = [
    "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html",
    "https://www.jpx.co.jp/english/markets/statistics-equities/misc/01.html",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

st.title("☁️ 東証全銘柄｜週足・一目均衡表 雲上抜けスクリーナー")
st.caption(
    "前週は雲上限以下、直近の確定週終値で雲上限を上抜けた銘柄を抽出します。"
)

with st.expander("判定ルールを見る"):
    st.markdown(
        """
- 前週終値が、前週時点の雲上限以下
- 上抜け週の終値が、その週時点の雲上限より上
- 指定した週数以内の上抜け
- 最新の確定週でも雲上限より上
- 先行スパンA・Bの26週シフトを反映
- ETF、REIT、インフラファンド等は基本的に除外
        """
    )

c1, c2, c3, c4 = st.columns(4)
with c1:
    recent_weeks = st.selectbox(
        "雲抜け後の期間",
        options=[1, 2, 3, 4, 5],
        index=2,
        format_func=lambda x: f"直近{x}週以内",
    )
with c2:
    min_volume_ratio = st.number_input(
        "最低出来高倍率",
        min_value=0.0,
        max_value=10.0,
        value=0.0,
        step=0.1,
        help="0なら出来高条件を使いません。20週平均との比較です。",
    )
with c3:
    max_distance = st.number_input(
        "雲上限からの最大乖離率",
        min_value=0.0,
        max_value=100.0,
        value=15.0,
        step=1.0,
        help="上昇しすぎた銘柄を除外できます。",
    )
with c4:
    market_choice = st.multiselect(
        "対象市場",
        ["プライム", "スタンダード", "グロース"],
        default=["プライム", "スタンダード", "グロース"],
    )

o1, o2, o3 = st.columns(3)
with o1:
    require_tenkan = st.checkbox("転換線 ＞ 基準線", value=False)
with o2:
    require_bull_cloud = st.checkbox("雲が上向き", value=False)
with o3:
    require_above_200 = st.checkbox("200週線より上", value=False)


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def get_jpx_list() -> pd.DataFrame:
    errors = []
    for page_url in JPX_PAGES:
        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            excel_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"\.xlsx?$", href, flags=re.I):
                    excel_links.append(urljoin(page_url, href))

            preferred = [
                u for u in excel_links
                if any(k in u.lower() for k in ("data_j", "data_e", "listed"))
            ]
            candidates = preferred or excel_links
            if not candidates:
                continue

            excel = requests.get(candidates[0], headers=HEADERS, timeout=60)
            excel.raise_for_status()
            raw = pd.read_excel(io.BytesIO(excel.content), dtype=str)
            break
        except Exception as exc:
            errors.append(str(exc))
    else:
        raise RuntimeError("JPXの銘柄一覧を取得できませんでした: " + " / ".join(errors))

    raw.columns = [str(c).strip() for c in raw.columns]

    def find_col(keys):
        for col in raw.columns:
            normalized = col.replace(" ", "").lower()
            if any(k.replace(" ", "").lower() in normalized for k in keys):
                return col
        raise KeyError(f"必要な列が見つかりません: {keys}")

    code_col = find_col(["コード", "code"])
    name_col = find_col(["銘柄名", "issue name", "company name", "name"])
    market_col = find_col(["市場・商品区分", "market/product category", "market"])

    df = raw[[code_col, name_col, market_col]].copy()
    df.columns = ["コード", "銘柄名", "市場区分"]
    df["コード"] = (
        df["コード"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df = df[df["コード"].str.match(r"^[0-9A-Z]{4}$", na=False)]

    market_text = df["市場区分"].fillna("").astype(str)
    include = market_text.str.contains(
        r"プライム|スタンダード|グロース|Prime|Standard|Growth",
        case=False,
        regex=True,
    )
    exclude = market_text.str.contains(
        r"ETF|ETN|REIT|投資法人|優先|出資証券|インフラ|PRO Market",
        case=False,
        regex=True,
    )
    df = df[include & ~exclude].drop_duplicates("コード").reset_index(drop=True)
    df["Ticker"] = df["コード"] + ".T"

    def normalize_market(text):
        t = str(text)
        if re.search("Prime|プライム", t, re.I):
            return "プライム"
        if re.search("Standard|スタンダード", t, re.I):
            return "スタンダード"
        if re.search("Growth|グロース", t, re.I):
            return "グロース"
        return t

    df["市場"] = df["市場区分"].map(normalize_market)
    return df


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    idx = pd.to_datetime(daily.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    daily.index = idx

    weekly = daily.resample("W-FRI").agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    )
    weekly = weekly.dropna(subset=["Open", "High", "Low", "Close"])

    # 未来の金曜ラベル＝週途中の未確定足を除外
    today = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    return weekly[weekly.index <= today]


def calculate_signal(weekly: pd.DataFrame, n_weeks: int):
    if len(weekly) < 90:
        return None

    high, low, close, volume = (
        weekly["High"],
        weekly["Low"],
        weekly["Close"],
        weekly["Volume"],
    )

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a_raw = (tenkan + kijun) / 2
    span_b_raw = (high.rolling(52).max() + low.rolling(52).min()) / 2

    cloud_a = span_a_raw.shift(26)
    cloud_b = span_b_raw.shift(26)
    cloud_top = pd.concat([cloud_a, cloud_b], axis=1).max(axis=1)

    breakout = (close > cloud_top) & (close.shift(1) <= cloud_top.shift(1))
    positions = np.flatnonzero(breakout.fillna(False).to_numpy())
    if len(positions) == 0:
        return None

    last = len(weekly) - 1
    cross = int(positions[-1])
    weeks_since = last - cross
    latest_top = cloud_top.iloc[-1]

    if weeks_since >= n_weeks or pd.isna(latest_top) or close.iloc[-1] <= latest_top:
        return None

    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = float(volume.iloc[-1] / vol_avg) if pd.notna(vol_avg) and vol_avg > 0 else np.nan
    sma200 = close.rolling(200).mean().iloc[-1]
    distance = float((close.iloc[-1] / latest_top - 1) * 100)

    return {
        "判定日": weekly.index[-1].date().isoformat(),
        "雲抜け日": weekly.index[cross].date().isoformat(),
        "雲抜け後週数": weeks_since,
        "終値": round(float(close.iloc[-1]), 2),
        "雲上限": round(float(latest_top), 2),
        "雲上限乖離率(%)": round(distance, 2),
        "出来高20週比": round(vol_ratio, 2) if pd.notna(vol_ratio) else np.nan,
        "転換線>基準線": bool(tenkan.iloc[-1] > kijun.iloc[-1]),
        "雲が上向き": bool(cloud_a.iloc[-1] > cloud_b.iloc[-1]),
        "200週線より上": bool(close.iloc[-1] > sma200) if pd.notna(sma200) else False,
    }


def extract_one(data: pd.DataFrame, ticker: str, batch_len: int) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(map(str, data.columns.get_level_values(0)))
        level1 = set(map(str, data.columns.get_level_values(1)))
        if ticker in level0:
            one = data[ticker].copy()
        elif ticker in level1:
            one = data.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        if batch_len != 1:
            return pd.DataFrame()
        one = data.copy()

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in one.columns for c in required):
        return pd.DataFrame()
    return one[required].dropna(how="all")


def run_scan(stocks: pd.DataFrame, n_weeks: int, progress_bar, status):
    batch_size = 60
    tickers = stocks["Ticker"].tolist()
    meta = stocks.set_index("Ticker")[["コード", "銘柄名", "市場"]].to_dict("index")
    rows, failed = [], []

    for start in range(0, len(tickers), batch_size):
        batch = tickers[start : start + batch_size]
        status.write(
            f"{start + 1:,}〜{min(start + len(batch), len(tickers)):,} / "
            f"{len(tickers):,}銘柄を確認中"
        )
        try:
            data = yf.download(
                tickers=batch,
                period="5y",
                interval="1d",
                auto_adjust=False,
                actions=False,
                group_by="ticker",
                threads=True,
                progress=False,
                timeout=30,
            )
        except Exception:
            failed.extend(batch)
            continue

        for ticker in batch:
            try:
                daily = extract_one(data, ticker, len(batch))
                if daily.empty:
                    failed.append(ticker)
                    continue
                signal = calculate_signal(to_weekly(daily), n_weeks)
                if signal:
                    rows.append({**meta[ticker], **signal})
            except Exception:
                failed.append(ticker)

        progress_bar.progress(min((start + len(batch)) / max(len(tickers), 1), 1.0))
        time.sleep(0.3)

    return pd.DataFrame(rows), len(set(failed))


if st.button("🔍 東証全銘柄をスキャン", type="primary", use_container_width=True):
    if not market_choice:
        st.warning("対象市場を1つ以上選んでください。")
        st.stop()

    try:
        with st.spinner("JPXから最新の上場銘柄一覧を取得しています…"):
            stocks = get_jpx_list()
            stocks = stocks[stocks["市場"].isin(market_choice)].reset_index(drop=True)

        st.info(f"対象：{len(stocks):,}銘柄。数分かかる場合があります。画面を閉じずにお待ちください。")
        progress = st.progress(0)
        status = st.empty()

        result, failed_count = run_scan(stocks, recent_weeks, progress, status)
        progress.empty()
        status.empty()

        if result.empty:
            st.warning("現在の条件に該当する銘柄はありませんでした。")
        else:
            result = result[result["雲上限乖離率(%)"] <= max_distance]
            if min_volume_ratio > 0:
                result = result[result["出来高20週比"] >= min_volume_ratio]
            if require_tenkan:
                result = result[result["転換線>基準線"]]
            if require_bull_cloud:
                result = result[result["雲が上向き"]]
            if require_above_200:
                result = result[result["200週線より上"]]

            result = result.sort_values(
                ["雲抜け後週数", "雲上限乖離率(%)", "出来高20週比"],
                ascending=[True, True, False],
                na_position="last",
            ).reset_index(drop=True)

            st.success(f"該当：{len(result):,}銘柄")
            if failed_count:
                st.caption(
                    f"価格を取得できなかった銘柄：{failed_count}件。"
                    "上場直後や一時的な通信制限などが原因の場合があります。"
                )

            st.dataframe(
                result,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "転換線>基準線": st.column_config.CheckboxColumn("転換線>基準線"),
                    "雲が上向き": st.column_config.CheckboxColumn("雲が上向き"),
                    "200週線より上": st.column_config.CheckboxColumn("200週線より上"),
                },
            )

            csv = result.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 結果をCSVでダウンロード",
                data=csv,
                file_name="週足_雲上抜け候補.csv",
                mime="text/csv",
                use_container_width=True,
            )

st.divider()
st.caption(
    "注意：株価は外部データを利用するため、取得漏れ・遅延・仕様変更が起こる場合があります。"
    "売買前には必ず実際の週足チャートで確認してください。"
)
