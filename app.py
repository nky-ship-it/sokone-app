import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import csv
import os
from datetime import datetime
import re
from io import BytesIO
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 憲法：設定とモデル固定（一切変更禁止）
# ==========================================
MODEL_NAME = "gemini-flash-latest" 
API_KEY = st.secrets["GEMINI_API_KEY"]
FILE_NAME = "price_history.csv"
SAVE_DIR = "item_images"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

genai.configure(api_key=API_KEY)

# あなたが決定した大分類・小分類構造
MAIN_CATEGORIES = ["肉", "魚", "野菜", "乳製品", "パン", "惣菜", "食品", "飲料", "日用品", "調味料", "油", "冷凍食品", "菓子", "果物", "米・穀物", "麺類", "その他"]

SUB_CAT_DICT = {
    "肉": ["豚肉", "鶏もも", "鶏むね", "ささみ", "牛肉", "鶏肉", "ソーセージ"],
    "魚": ["魚", "牡蠣", "エビ"],
    "野菜": ["玉ねぎ", "バナナ", "にんにく", "生姜"],
    "果物": ["バナナ"],
    "乳製品": ["牛乳", "卵", "ヨーグルト", "チーズ", "スキムミルク", "生クリーム", "バター"],
    "パン": ["食パン"],
    "米・穀物": ["米", "餅"],
    "食品": ["薄力粉", "強力粉", "片栗粉", "米粉", "豆腐", "納豆", "糸こんにゃく", "角こんにゃく", "油揚げ"],
    "油": ["サラダ油", "オリーブオイル", "ごま油", "米油"],
    "調味料": ["醤油", "ソース", "ケチャップ", "マヨネーズ", "砂糖", "塩", "胡椒", "コンソメ", "鶏がらスープ", "だしの素", "豆板醤", "コチュジャン"],
    "日用品": ["トイレットペーパー", "ティッシュ", "洗濯洗剤", "食器用洗剤", "シャンプー", "コンディショナー", "ボディソープ", "石鹸", "ハンドソープ"]
}

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
st.set_page_config(page_title="底値調", layout="centered")
st.markdown('<html lang="ja">', unsafe_allow_html=True)
st.markdown("### 底値調")

if "res" not in st.session_state: st.session_state.res = None
if "saved_store" not in st.session_state: st.session_state.saved_store = ""
if "last_image_hash" not in st.session_state: st.session_state.last_image_hash = None

mode = st.sidebar.radio("メニュー", ["解析・登録", "履歴・分析"])

if mode == "解析・登録":
    file = st.file_uploader("", type=["jpg", "jpeg", "png"])
    # 初期状態
    res = st.session_state.res if st.session_state.res else {"store":"", "product":"", "orig_p":0, "disc_p":0, "is_half": False, "content":"", "cat":"肉", "sub":""}

    if file:
        image = Image.open(file)
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image) 
        st.image(image, width=300)
        img_hash = hash(file.getvalue())

        if st.session_state.last_image_hash != img_hash:
            with st.spinner("解析中..."):
                model = genai.GenerativeModel(MODEL_NAME)
                # あなたが苦労して完成させたプロンプトを完全復元
                prompt = f"""
                画像の商品1つを解析し、以下の項目を正確に抽出せよ。
                1. 店舗名：屋号のみ。
                2. 商品名：ブランド名や種類。
                3. 定価：割引前の税込数値のみ。
                4. 割引後価格：割引後の税込数値のみ。
                5. 半額フラグ：画像内に「半額」の文字があれば「True」。
                6. 内容量：数値と単位。トイレットペーパーは「m」数（ダブル・シングルの判別含む）、お菓子等は「g」や「kcal」を重視。
                7. 推定分類：大分類/小分類。大分類は {MAIN_CATEGORIES} から選択。
                出力形式：
                店舗名：\n商品名：\n定価：\n割引後価格：\n半額フラグ：\n内容量：\n推定分類：
                """
                img_for_ai = image.copy().convert("RGB")
                img_for_ai.thumbnail((800, 800)) 
                buf = BytesIO()
                img_for_ai.save(buf, format="JPEG", quality=50) 
                response = model.generate_content([prompt, Image.open(buf)])
                text = response.text

                # 元の厳密なパース処理を復元
                parsed = {"store":"", "product":"", "orig_p":0, "disc_p":0, "is_half": False, "content":"", "cat":"肉", "sub":""}
                for line in text.split("\n"):
                    if "店舗名：" in line: parsed["store"] = line.split("：")[-1].strip()
                    if "商品名：" in line: parsed["product"] = line.split("：")[-1].strip()
                    if "定価：" in line: 
                        n = extract_numbers(line)
                        parsed["orig_p"] = int(n[0]) if n else 0
                    if "割引後価格：" in line:
                        n = extract_numbers(line)
                        parsed["disc_p"] = int(n[0]) if n else 0
                    if "半額フラグ：" in line: parsed["is_half"] = "True" in line
                    if "内容量：" in line: parsed["content"] = line.split("：")[-1].strip()
                    if "推定分類：" in line:
                        parts = line.split("：")[-1].split("/")
                        parsed["cat"] = parts[0].strip() if parts[0].strip() in MAIN_CATEGORIES else "肉"
                        if len(parts) > 1: parsed["sub"] = parts[1].strip()
                st.session_state.res = parsed
                res = parsed
                st.session_state.last_image_hash = img_hash

    st.divider()

    # 1. 大分類（連動の起点）
    cat_index = MAIN_CATEGORIES.index(res["cat"]) if res["cat"] in MAIN_CATEGORIES else 0
    cat = st.selectbox("大分類を選択", MAIN_CATEGORIES, index=cat_index)

    # 2. 小分類（連動）
    df_history = safe_read_csv()
    preset_subs = SUB_CAT_DICT.get(cat, [])
    # 履歴から、今の大分類に合う小分類を抽出
    history_subs = df_history[df_history["category"] == cat]["subcategory"].dropna().unique().tolist() if not df_history.empty else []
    
    # プリセット、履歴、今回のAI回答を統合（重複は自動で消去）
    temp_subs = preset_subs + history_subs
    if res["sub"] and res["sub"] not in temp_subs:
        temp_subs.append(res["sub"]) # ここで「牛肉」などのリスト外ワードを救済

    # 空欄を除いてソートし、最後に「空欄」を追加する（きれいに並べるため）
    all_subs = sorted(list(set([s for s in temp_subs if s]))) + [""]

    # AIの解析結果（res["sub"]）を初期値にセット。なければ空欄を選択。
    current_sub_default = res["sub"] if res["sub"] in all_subs else ""

    sub = st.selectbox(
        "小分類を選択", 
        options=all_subs, 
        index=all_subs.index(current_sub_default) if current_sub_default in all_subs else 0
    )    
    manual_sub = st.text_input("（リストにない小分類は手入力）", "")
    if manual_sub: sub = manual_sub

    # 安値トップ5（全項目表示・インデックスなし・ご指定の順序）
    if sub and not df_history.empty:
        top5 = df_history[df_history["subcategory"] == sub].copy()
        if not top5.empty:
            def sk(x):
                n = extract_numbers(x); return n[0] if n else 999999
            top5 = top5.assign(v=top5["単価"].apply(sk)).sort_values("v").head(5)
            
            top5_display = top5[["subcategory", "単価", "価格", "内容量", "店舗", "商品", "category", "日時", "備考", "画像"]]
            top5_display.columns = ["小分類", "単価", "値段", "容量", "店舗名", "商品名", "大分類", "登録日", "備考", "写真"]

            st.markdown(f"💡 **{sub}** の過去安値トップ5")
            st.dataframe(top5_display, hide_index=True, use_container_width=True)

    # 入力フォーム
    product = st.text_input("商品名（空欄なら小分類名が入ります）", res["product"])
    
    if res["is_half"] and res["orig_p"] > 0:
        price_display = f"{res['orig_p']}円 レジにて半額（{res['disc_p']}円）"
    else:
        price_display = f"{res['disc_p']}円" if res["disc_p"] > 0 else ""

    price_val = st.text_input("価格 (税込)", price_display)
    content_val = st.text_input("内容量", res["content"])

    # 店舗選択
    favorite_stores = ["イオン", "マルイチ", "ビッグハウス", "オセン", "土日ジャンボ", "じゃんまる", "ジョイス", "業務スーパー", "さっこら", "トライアル", "マイヤ", "薬王堂", "サンドラッグ", "やまや", ""]
    past_stores = df_history["店舗"].value_counts().index.tolist() if not df_history.empty else []
    all_stores = favorite_stores + [s for s in past_stores if s not in favorite_stores]
    
    c_st1, c_st2 = st.columns([3, 1])
    with c_st1:
        def_st_idx = all_stores.index(st.session_state.saved_store) if st.session_state.saved_store in all_stores else 0
        store = st.selectbox("店舗名を選択", options=all_stores, index=def_st_idx)
    with c_st2:
        keep_check = st.checkbox("店名固定", value=True)
    
    manual_store = st.text_input("（リストにない店名は入力）", "")
    if manual_store: store = manual_store

    note = st.text_area("備考", "")
    save_image_check = st.checkbox("写真を履歴に保存する", value=False)

    # 単価計算（元の精密なロジックを復元）
    p_nums = extract_numbers(price_val)
    cur_p = (p_nums[-1] if "半額" in price_val else p_nums[0]) if p_nums else 0
    c_nums = extract_numbers(content_val)
    u_display = "計算不可"
    if cur_p > 0 and c_nums:
        cl = content_val.lower()
        if "m" in cl and "ml" not in cl:
            tm = c_nums[0] * c_nums[1] if len(c_nums) >= 2 else c_nums[0]
            u_display = f"{round(cur_p/tm, 2)} 円/m" if tm > 0 else u_display
        elif any(x in cl for x in ["g", "ml", "k"]):
            bv = (c_nums[0] * c_nums[1] if len(c_nums) >= 2 else c_nums[0]) * (1000 if "k" in cl else 1)
            u_display = f"{round((cur_p/bv)*100, 1)} 円/{'100ml' if 'ml' in cl else '100g'}" if bv > 0 else u_display
        else:
            u_display = f"{round(cur_p/c_nums[0], 1)} 円/個"

    st.markdown(f"### 単価: <span style='color:red'>{u_display}</span>", unsafe_allow_html=True)

    if st.button("履歴に保存", type="primary", use_container_width=True):
        try:
            save_product = product if product else sub
            img_path = "なし"
            if file and save_image_check:
                img_path = os.path.join(SAVE_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                thumb = image.copy(); thumb.thumbnail((200, 200)); thumb.save(img_path, "JPEG", quality=50)
            
            # 接続を確立
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # 最新の全データを取得（ttl=0 でキャッシュを無視）
            try:
                df_all = conn.read(ttl=0)
            except:
                df_all = pd.DataFrame()
            
            # 新しい1行を作成
            new_row = pd.DataFrame([{
                "日時": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "店舗": store, 
                "商品": save_product, 
                "価格": price_val, 
                "内容量": content_val,
                "単価": u_display, 
                "category": cat, 
                "subcategory": sub, 
                "備考": note, 
                "画像": img_path
            }])
            
            # 既存データと結合
            if df_all is not None and not df_all.empty:
                # 列名が一致しない場合に備えて、新しい行を既存の列に合わせる
                updated_df = pd.concat([df_all, new_row], ignore_index=True)
            else:
                updated_df = new_row
            
            # スプレッドシートを丸ごと上書き保存
            conn.update(data=updated_df)
            
            # Streamlit側の表示キャッシュをクリア
            st.cache_data.clear()
            
            st.success("スプレッドシートを更新しました！")
            import time; time.sleep(1)
            st.session_state.saved_store = store if keep_check else ""
            st.session_state.res = None
            st.rerun()
        except Exception as e: 
            st.error(f"保存に失敗しました。エラー詳細: {e}")

elif mode == "履歴・分析":
    # ttl=0 を指定して、保存直後でも最新のスプレッドシートを表示させる
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=0) 
    
    if df is not None and not df.empty:

    df = safe_read_csv()
    if not df.empty:
        # --- 検索窓の修正（小分類を追加） ---
        with st.expander("🔍 履歴を検索・絞り込み", expanded=True):
            c1, c2, c3 = st.columns(3) # 3列にします
            with c1: 
                search_word = st.text_input("キーワード検索", "")
            with c2: 
                target_cat = st.selectbox("大分類で絞り込み", ["すべて"] + MAIN_CATEGORIES)
            with c3:
                # 大分類に連動した小分類リストを作成
                if target_cat != "すべて":
                    subs = ["すべて"] + SUB_CAT_DICT.get(target_cat, [])
                else:
                    subs = ["すべて"]
                target_sub = st.selectbox("小分類で絞り込み", subs)
        
        # フィルタリング処理（小分類の条件を追加）
        filtered_df = df.copy()
        if search_word:
            filtered_df = filtered_df[
                (filtered_df["商品"].astype(str).str.contains(search_word, na=False)) | 
                (filtered_df["備考"].astype(str).str.contains(search_word, na=False)) |
                (filtered_df["subcategory"].astype(str).str.contains(search_word, na=False))
            ]
        if target_cat != "すべて":
            filtered_df = filtered_df[filtered_df["category"] == target_cat]
        
        # 【追加】小分類での絞り込み
        if target_sub != "すべて":
            filtered_df = filtered_df[filtered_df["subcategory"] == target_sub]

        # --- 表示処理（ここは変更なし） ---
        display_cols = ["subcategory", "単価", "価格", "内容量", "店舗", "商品", "category", "日時", "備考", "画像"]
        df_view = filtered_df.reindex(columns=display_cols).sort_values("日時", ascending=False)
        df_view.columns = ["小分類", "単価", "値段", "容量", "店舗名", "商品名", "大分類", "登録日", "備考", "写真"]
        
        st.data_editor(df_view, use_container_width=True, hide_index=True)
        
    else:
        st.info("履歴がまだありません。")
