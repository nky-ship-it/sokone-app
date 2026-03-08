import streamlit as st

import google.generativeai as genai

from PIL import Image

import pandas as pd

import csv

import os

from datetime import datetime

import re
from io import BytesIO



# ==========================================

# 憲法：設定とモデル固定

# ==========================================

MODEL_NAME = "gemini-flash-latest" 

API_KEY = st.secrets["GEMINI_API_KEY"]

FILE_NAME = "price_history.csv"
SAVE_DIR = "item_images"

# フォルダがなければ作る
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)



genai.configure(api_key=API_KEY)



MAIN_CATEGORIES = ["肉", "魚", "野菜", "乳製品", "パン", "惣菜", "食品", "飲料", "日用品", "調味料", "冷凍食品", "菓子", "果物", "米・穀物", "麺類", "その他"]



def extract_numbers(text):

    if not text: return []

    return [float(x) for x in re.findall(r"\d+\.?\d*", str(text).replace(",", ""))]



def safe_read_csv():

    if not os.path.exists(FILE_NAME) or os.path.getsize(FILE_NAME) == 0:

        return pd.DataFrame()

    try:

        return pd.read_csv(FILE_NAME, encoding="utf-8-sig")

    except:

        return pd.DataFrame()



# ==========================================

# メインUI

# ==========================================

# menu_itemsの中に設定を書くことで、ブラウザに日本語であることを正しく伝えます
st.set_page_config(
    page_title="底値調", 
    layout="centered",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "### 日本語のアプリです"
    }
)

# ブラウザの翻訳機能を直接オフにするための「おまじない」を画面に埋め込みます
st.markdown('<html lang="ja">', unsafe_allow_html=True)

if "SAVE_DIR" in globals(): st.static_file_storage_path = SAVE_DIR 

st.markdown("### 底値調")


if "res" not in st.session_state: st.session_state.res = None

if "last_image_hash" not in st.session_state: st.session_state.last_image_hash = None



mode = st.sidebar.radio("メニュー", ["解析・登録", "履歴・分析"])



if mode == "解析・登録":

    file = st.file_uploader("", type=["jpg", "jpeg", "png"])

    

    if file:
        image = Image.open(file)
        # --- ここから追加 ---
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image) 
        # --- ここまで ---
        st.image(image, width=300)
        img_hash = hash(file.getvalue())

        

        if st.session_state.last_image_hash != img_hash:

            with st.spinner("解析中..."):

                model = genai.GenerativeModel(MODEL_NAME)

                # AIには「数値」と「フラグ」だけを厳密に答えさせる

                prompt = f"""

                画像の商品1つを解析し、以下の項目を正確に抽出せよ。

                1. 店舗名：屋号のみ。

                2. 商品名：ブランド名や種類。
                   ※トイレットペーパーの場合は、必ず「シングル」か「ダブル」かを判別して商品名に含めよ（例：エリエール ダブル）。

                3. 定価：割引前の税込数値のみ。

                4. 割引後価格：割引後の税込数値のみ。割引がない場合は定価と同じ数値を入れよ。

                5. 半額フラグ：画像内に「半額」の文字があれば「True」、なければ「False」。

                6. 内容量：数値と単位(g/ml/m/枚/ロール/ネット)。

　　　　　　　　　※トイレットペーパー等は必ず「m数」と「ロール数」の両方を書け（例：25m 12ロール）。
                   ※重量不明な菓子等は、成分表から「1枚のkcal / 100gのkcal * 100 * 枚数」を計算し、その合計g数を出力せよ。

                7. 推定分類：大分類/小分類。大分類は {MAIN_CATEGORIES} から選択。肉なら必ず大分類を「肉」にせよ。

                

                出力形式：

                店舗名：

                商品名：

                定価：

                割引後価格：

                半額フラグ：

                内容量：

                推定分類：

                """

                # --- 画像の軽量化処理 ---
                img_for_ai = image.copy().convert("RGB")
                img_for_ai.thumbnail((800, 800))  # 最大800pxにリサイズ
                
                buf = BytesIO()
                img_for_ai.save(buf, format="JPEG", quality=50)  # 画質50%で圧縮
                reduced_image = Image.open(buf)
                
                # 軽量化した reduced_image をAIに送る
                response = model.generate_content([prompt, reduced_image])

                text = response.text

                

                parsed = {"store":"", "product":"", "orig_p":0, "disc_p":0, "is_half": False, "content":"", "cat":"その他", "sub":""}

                for line in text.split("\n"):

                    if "店舗名：" in line: parsed["store"] = line.split("：")[-1].strip()

                    if "商品名：" in line: parsed["product"] = line.split("：")[-1].strip()

                    if "定価：" in line: 

                        nums = extract_numbers(line)

                        parsed["orig_p"] = int(nums[0]) if nums else 0

                    if "割引後価格：" in line:

                        nums = extract_numbers(line)

                        parsed["disc_p"] = int(nums[0]) if nums else 0

                    if "半額フラグ：" in line: parsed["is_half"] = "True" in line

                    if "内容量：" in line:
                        raw_content = line.split("：")[-1].strip()
                        c_nums = extract_numbers(raw_content)
                        if c_nums and "k" in raw_content.lower():
                            parsed["content"] = f"{int(c_nums[0] * 1000)}g"
                        else:
                            parsed["content"] = raw_content

                    if "推定分類：" in line:

                        parts = line.split("：")[-1].split("/")

                        parsed["cat"] = parts[0].strip() if parts[0].strip() in MAIN_CATEGORIES else "その他"

                        if len(parts) > 1: parsed["sub"] = parts[1].strip()

                

                st.session_state.res = parsed

                st.session_state.last_image_hash = img_hash



    if st.session_state.res:
        res = st.session_state.res
        st.divider()

        # --- 表示用データの準備 ---
        if res["is_half"] and res["orig_p"] > 0:
            price_display = f"{res['orig_p']}円 レジにて半額（{res['disc_p']}円）"
            final_price = res["disc_p"]
        else:
            price_display = f"{res['disc_p']}円"
            final_price = res["disc_p"]

        # --- 入力フォーム ---
        # --- 店舗・商品・価格入力エリア（ここから貼り付け） ---
        # よく行く店リスト（自由に追加・削除してください）(, "", "", "")
        favorite_stores = ["イオン", "マルイチ", "ビッグハウス", "オセン", "土日ジャンボ", "じゃんまる", "ジョイス", "業務スーパー", "さっこら", "トライアル", "マイヤ", "薬王堂", "サンドラッグ", "やまや", ""]

        # 履歴から過去の店名を取得してリストを作る
        df_history = safe_read_csv()
        if not df_history.empty:
            past_stores = df_history["店舗"].value_counts().index.tolist()
            all_options = favorite_stores + [s for s in past_stores if s not in favorite_stores]
        else:
            all_options = favorite_stores

        # AIの解析結果を選択肢の最初に入れる
        if res["store"] not in all_options:
            all_options = [res["store"]] + all_options

        # 店舗名の入力（選択 ＋ 固定チェック）
        c_st1, c_st2 = st.columns([3, 1])
        with c_st1:
            store = st.selectbox("店舗名を選択", options=all_options, index=0)
        with c_st2:
            keep_check = st.checkbox("店名を固定", value=True)

        # リストにない場合の手動入力
        manual_store = st.text_input("（リストにない場合は入力）", "")
        if manual_store:
            store = manual_store

        # 商品名・価格・内容量の入力
        product = st.text_input("商品名", res["product"])
        price_val = st.text_input("価格 (税込)", price_display)
        content_val = st.text_input("内容量", res["content"])
        # --- ここまで貼り付け ---

        c1, col2 = st.columns(2)
        with c1:
            cat = st.selectbox("大分類", MAIN_CATEGORIES, index=MAIN_CATEGORIES.index(res["cat"]))
        with col2:
            sub = st.text_input("小分類", res["sub"])

        note = st.text_area("備考", "")
        save_image_check = st.checkbox("商品写真を履歴に保存する", value=True)

        # --- 単価計算（改良版：kg/g/ml/m/個 対応） ---
        # --- 単価計算（修正版：単位表示の改善） ---
        c_nums = extract_numbers(content_val)
        unit_price_display = "計算不可"

        if final_price > 0 and c_nums:
            content_lower = content_val.lower()
            
            # 1. メートル単価 (トイレットペーパー等) を最優先
            if "m" in content_lower and "ml" not in content_lower:
                # 数値が2つあれば「25m * 12ロール」のように掛け算、1つならそのまま
                total_m = c_nums[0] * c_nums[1] if len(c_nums) >= 2 else c_nums[0]
                if total_m > 0:
                    unit_price_display = f"{round(final_price / total_m, 2)} 円/m"
            
            # 2. 重さ・容量 (g, ml, kg)
            elif any(x in content_lower for x in ["g", "ml", "k"]):
                # 数値が2つあれば掛け算、1つならそのまま
                base_val = c_nums[0] * c_nums[1] if len(c_nums) >= 2 else c_nums[0]
                
                # kg(k)が含まれる場合は1000倍してg換算
                if "k" in content_lower:
                    base_val = base_val * 1000
                
                if base_val > 0:
                    # 単位を表示し分ける（mlがあれば100ml、それ以外は100g）
                    u_label = "100ml" if "ml" in content_lower else "100g"
                    unit_price_display = f"{round((final_price / base_val) * 100, 1)} 円/{u_label}"
            
            # 3. その他（個、袋、パックなど）
            else:
                total_u = c_nums[0]
                u_name = re.sub(r'[0-9.]', '', content_val).strip() or "単位"
                unit_price_display = f"{round(final_price / total_u, 1)} 円/{u_name}"

        # ↑ ここまでを貼り付け ↑



        st.markdown(f"### 単価: <span style='color:red'>{unit_price_display}</span>", unsafe_allow_html=True)



        if st.button("履歴に保存", type="primary", use_container_width=True):
            try:
                # --- 画像を低画質（サムネイル）で保存 ---
                img_path = "なし"
                if file and save_image_check:
                    # ファイル名を日時ベースで作成
                    img_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    img_path = os.path.join(SAVE_DIR, img_name)
                    
                    # 画像を小さくして保存（低画質モード）
                    thumb_img = image.copy()
                    thumb_img.thumbnail((200, 200)) # 最大200pxに縮小
                    thumb_img.save(img_path, "JPEG", quality=50) # 画質を落として保存
                
                # 保存する項目を10個に増やします（末尾にimg_pathを追加）
                new_row = [
                    datetime.now().strftime("%Y-%m-%d %H:%M"), 
                    store, product, price_val, content_val, 
                    unit_price_display, cat, sub, note, img_path
                ]
                
                file_exists = os.path.exists(FILE_NAME) and os.path.getsize(FILE_NAME) > 0
                with open(FILE_NAME, "a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        # 見出しにも「画像」を追加
                        writer.writerow(["日時", "店舗", "商品", "価格", "内容量", "単価", "category", "subcategory", "備考", "画像"])
                    writer.writerow(new_row)
                
                # --- ここから書き換え ---
                if file and save_image_check:
                    st.success("画像付きで保存完了しました！")
                else:
                    st.success("保存完了しました！")
                
                # --- ここから追加 ---
                import time
                time.sleep(2) 
                # --- ここまで追加 ---


                if keep_check: st.session_state.res["store"] = store # ←これを追加
                st.session_state.res = None
                st.rerun()
            except Exception as e:
                st.error(f"保存失敗: {e}")



elif mode == "履歴・分析":
    df = safe_read_csv()
    if not df.empty:
        # --- 1. 画面設定と切り替えスイッチ ---
        col_title, col_view = st.columns([2, 1])
        with col_title:
            st.subheader("📊 履歴の検索・比較")
        with col_view:
            view_mode = st.radio("表示形式", ["表", "カード"], horizontal=True)

        # --- 2. フィルタエリア ---
        with st.expander("🔍 絞り込み条件", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                search_word = st.text_input("商品名検索", "")
                ai_search = st.checkbox("AIであいまい検索")
            with col2:
                target_cat = st.selectbox("カテゴリ", ["すべて"] + MAIN_CATEGORIES)
            
            c3, c4 = st.columns(2)
            with c3:
                sub_list = sorted(df[df["category"] == target_cat]["subcategory"].dropna().unique().tolist()) if target_cat != "すべて" else sorted(df["subcategory"].dropna().unique().tolist())
                target_sub = st.selectbox("小分類", ["すべて"] + sub_list)
            with c4:
                target_store = st.selectbox("店舗名", ["すべて"] + sorted(df["店舗"].unique().tolist()))

        # --- 3. フィルタリング実行 ---
        filtered_df = df.copy()
        if search_word:
            if ai_search:
                with st.spinner("AIが似た意味の商品を探しています..."):
                    model = genai.GenerativeModel(MODEL_NAME)
                    p_list = filtered_df["商品"].unique().tolist()
                    prompt = f"「{search_word}」と意味が近いものをリストから選び、カンマ区切りで出力せよ。リスト:{p_list}"
                    res = model.generate_content(prompt)
                    matched = [p.strip() for p in res.text.split(",")]
                    filtered_df = filtered_df[filtered_df["商品"].isin(matched)]
            else:
                # 簡易検索（爆速）
                filtered_df = filtered_df[filtered_df["商品"].str.contains(search_word, na=False)]

        if target_cat != "すべて": filtered_df = filtered_df[filtered_df["category"] == target_cat]
        if target_sub != "すべて": filtered_df = filtered_df[filtered_df["subcategory"] == target_sub]
        if target_store != "すべて": filtered_df = filtered_df[filtered_df["店舗"] == target_store]

        # --- 4. 表示部分 ---
        if not filtered_df.empty:
            # 最安値表示
            def get_num(x):
                nums = extract_numbers(x)
                return nums[0] if nums else 999999
            best_row = filtered_df.assign(v=filtered_df["単価"].apply(get_num)).sort_values("v").iloc[0]

            # 画像のBase64化関数
            import base64
            # 画像のBase64化関数（エラー対策強化版）
            import base64
            def get_img(path):
                # pathが文字ではない場合、または空の場合は即座にNoneを返す
                if not isinstance(path, str) or not path:
                    return None
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
                return None

            if view_mode == "表":
                # 1. 表示用データの準備（最新順に並び替え）
                display_df = filtered_df.copy()
                if "画像" in display_df.columns:
                    display_df["画像"] = display_df["画像"].apply(get_img)
                
                # ここで「最新が一番上」になるように並び替えます
                display_df = display_df.sort_values("日時", ascending=False)

                # 2. 表（エディタ）の表示
                edited_df = st.data_editor(
                    display_df,
                    column_config={
                        "画像": st.column_config.ImageColumn("写真", width="medium"),
                        "日時": st.column_config.TextColumn("登録日", disabled=True),
                    },
                    use_container_width=True,
                    hide_index=False, 
                    num_rows="dynamic",
                    key="editor_table"
                )

                # 3. 修正・削除の保存処理
                state = st.session_state.editor_table
                if state.get("edited_rows") or state.get("deleted_rows"):
                    if st.button("📝 修正を確定して保存する", use_container_width=True):
                        full_df = safe_read_csv()
                        
                        # 編集の反映
                        if state.get("edited_rows"):
                            for idx_str, edits in state.get("edited_rows").items():
                                target_idx = display_df.index[int(idx_str)]
                                for col, val in edits.items():
                                    if col != "画像":
                                        full_df.at[target_idx, col] = val
                        
                        # 削除の反映
                        if state.get("deleted_rows"):
                            delete_indices = [display_df.index[int(i)] for i in state.get("deleted_rows")]
                            full_df = full_df.drop(delete_indices)
                        
                        full_df.to_csv(FILE_NAME, index=False)
                        st.success("✅ 修正を反映しました！")
                        import time
                        time.sleep(1)
                        st.rerun()
            else:
                # カード型レイアウト（メルカリ風）
                cols = st.columns(2) # 2列で並べる
                for i, (_, row) in enumerate(filtered_df.sort_values("日時", ascending=False).iterrows()):
                    with cols[i % 2]:
                        img_base64 = get_img(row["画像"])
                        if img_base64:
                            st.image(img_base64, use_container_width=True)
                        st.markdown(f"**{row['商品']}**")
                        st.markdown(f"### <span style='color:red'>{row['価格']}</span>", unsafe_allow_html=True)
                        st.caption(f"{row['店舗']} | {row['単価']}")
                        st.divider()

    else:
        st.info("履歴がまだありません。")

