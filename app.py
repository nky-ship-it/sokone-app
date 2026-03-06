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

API_KEY = "AIzaSyDCJKoIO_zMC4r0N4scSPtLCPfv2uEQBSw"

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

st.set_page_config(page_title="底値調", layout="centered")

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

            with st.spinner("自動解析中..."):

                model = genai.GenerativeModel(MODEL_NAME)

                # AIには「数値」と「フラグ」だけを厳密に答えさせる

                prompt = f"""

                画像の商品1つを解析し、以下の項目を正確に抽出せよ。

                1. 店舗名：屋号のみ。

                2. 商品名：

                3. 定価：割引前の税込数値のみ。

                4. 割引後価格：割引後の税込数値のみ。割引がない場合は定価と同じ数値を入れよ。

                5. 半額フラグ：画像内に「半額」の文字があれば「True」、なければ「False」。

                6. 内容量：数値と単位(g/ml/m/枚/ロール/ネット)。

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

                    if "内容量：" in line: parsed["content"] = line.split("：")[-1].strip()

                    if "推定分類：" in line:

                        parts = line.split("：")[-1].split("/")

                        parsed["cat"] = parts[0].strip() if parts[0].strip() in MAIN_CATEGORIES else "その他"

                        if len(parts) > 1: parsed["sub"] = parts[1].strip()

                

                st.session_state.res = parsed

                st.session_state.last_image_hash = img_hash



    if st.session_state.res:

        res = st.session_state.res

        st.divider()

        

        # --- UI用定型文作成（プログラムで組み立て） ---

        if res["is_half"] and res["orig_p"] > 0:

            price_display = f"{res['orig_p']}円 レジにて半額（{res['disc_p']}円）"

            final_price = res["disc_p"]

        else:

            price_display = f"{res['disc_p']}円"

            final_price = res["disc_p"]



        store = st.text_input("店舗名", res["store"])

        product = st.text_input("商品名", res["product"])

        price_val = st.text_input("価格 (税込)", price_display)

        content_val = st.text_input("内容量", res["content"])

        

        c1, col2 = st.columns(2)

        with c1: cat = st.selectbox("大分類", MAIN_CATEGORIES, index=MAIN_CATEGORIES.index(res["cat"]))

        with col2: sub = st.text_input("小分類", res["sub"])

        

        note = st.text_area("備考", "")

        save_image_check = st.checkbox("商品写真を履歴に保存する", value=True)



        # --- 単価計算（トイレットペーパーm単価 復活） ---

        c_nums = extract_numbers(content_val)

        unit_price_display = "計算不可"

        

        if final_price > 0 and c_nums:

            # mがあれば、ロール数に関わらずm（数値の大きい方、または2つあれば掛け算）を優先

            # --- 単価計算（修正版：kg対応） ---
            content_lower = content_val.lower()
            if "m" in content_lower and "ml" not in content_lower:
                total_m = c_nums[0] * c_nums[1] if len(c_nums) >= 2 else c_nums[0]
                unit_price_display = f"{round(final_price / total_m, 2)} 円/m"
            
            elif "kg" in content_lower:
                # 1kg = 1000g として 100g単価を出す
                total_kg = sum(c_nums)
                unit_price_display = f"{round((final_price / (total_kg * 1000)) * 100, 1)} 円/100g"
            
            elif any(x in content_lower for x in ["g", "ml"]):
                total_g = sum(c_nums)
                unit_price_display = f"{round((final_price / total_g) * 100, 1)} 円/100g"
            
            else:
                total_u = sum(c_nums)
                u_name = re.sub(r'[0-9.]', '', content_val).strip() or "単位"
                unit_price_display = f"{round(final_price / total_u, 1)} 円/{u_name}"



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
                
                st.success("画像付きで保存完了しました！")
                st.session_state.res = None
            except Exception as e:
                st.error(f"保存失敗: {e}")



elif mode == "履歴・分析":
    df = safe_read_csv()
    if not df.empty:
        st.subheader("登録履歴（最新順）")
        
        # 画像をブラウザが表示できる形式に変換する関数
        import base64
        def get_image_base64(path):
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
            return None

        # 表示用のコピーを作成
        display_df = df.copy()
        if "画像" in display_df.columns:
            display_df["画像"] = display_df["画像"].apply(get_image_base64)

        st.data_editor(
            display_df.sort_values("日時", ascending=False),
            column_config={
                "画像": st.column_config.ImageColumn("商品写真", width="small")
            },
            use_container_width=True,
            hide_index=True,
        )
        
        if st.sidebar.button("CSVリセット"):
            import shutil
            import time
            
            # 1. まずCSVファイルを消す
            if os.path.exists(FILE_NAME):
                os.remove(FILE_NAME)
            
            # 2. 画像フォルダを消す（粘り強くリトライする）
            if os.path.exists(SAVE_DIR):
                for _ in range(5):  # 最大5回挑戦する
                    try:
                        shutil.rmtree(SAVE_DIR)
                        break  # 消せたらループ（挑戦）を終了
                    except PermissionError:
                        time.sleep(0.2)  # 0.2秒だけ待って再挑戦
                        continue
            
            st.rerun()