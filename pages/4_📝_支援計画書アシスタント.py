import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
import pandas as pd
import datetime # ← ★時間を取得するために追加しました！

# --- 画面の設定 ---
st.set_page_config(page_title="AI支援計画書アシスタント", page_icon="📝", layout="centered")

# ==========================================
# 🚨 セキュリティバウンサー（未ログイン者を追い出す）
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()  # 👈 これが超重要！ここでプログラムの実行を強制ストップさせます
# ==========================================

# --- 診断ナビの記憶を消去するおまじない ---
if "diagnostic_result" in st.session_state:
    st.session_state.diagnostic_result = None

# === 🔑 APIキーの読み込み ===
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # ★ 変更点2：Client（通信係）を作成
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

TARGET_MODEL = "gemini-3.1-flash-lite"

# --- カスタムCSS ---
st.markdown("""
<style>
.stApp { background-color: #F8F9FA; }
.security-red {
    background-color: #fff5f5; padding: 20px; border-radius: 10px;
    border: 2px solid #ff4b4b; color: #ff4b4b; font-weight: bold; margin-bottom: 25px;
}
.guide-box { background-color: #ffffff; padding: 20px; border-radius: 10px; border: 1px solid #E0E0E0; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

st.title("📝 AI支援計画書作成アシスタント")
st.markdown("日々の面談記録や訓練ログから、支援計画書の下書きをAIがサポートします。")

# --- 🛡️ 重要：セキュリティに関する注意書き ---
st.markdown(f"""
<div class="security-red">
    ⚠️ 個人情報保護に関する重要なお願い<br>
    システムには「安全装置」が組み込まれており、氏名や連絡先などの個人情報が含まれている可能性のあるデータはAIへ送信されません。<br>
    事前にExcel等で該当の列を完全に削除してからアップロードしてください。
</div>
""", unsafe_allow_html=True)

# --- 💡 アップロード前の準備と注意点 ---
with st.expander("💡 アップロードするCSVデータの準備とコツ（必ずお読みください）", expanded=True):
    st.markdown("""
    **① 個人情報の削除（必須）**
    データベースから書き出したCSVをExcel等で開き、**「氏名」「対象者」「電話番号」**などの列を必ず削除してください。
    
    **② 不要な列の削除（AIの精度アップ！）**
    システムが出力した「レコードID」「入力スタッフ名」「更新日時」など、計画書に関係ないデータはなるべく削除してください。**「日付」「訓練内容」「本人の様子（特記事項）」**だけを残すと、AIが混乱せず、より的確な分析をしてくれます。
    
    **③ 待ち時間について**
    AIは一度に数ヶ月〜半年分のデータを読み込むことができます。ただし、データ量（文字数）が多い場合は、**ボタンを押してから結果が出るまでに30秒〜1分ほどかかることがあります。** 画面が固まったわけではありませんので、そのまま少しお待ちください。
    """)

# --- ファイルアップローダー ---
uploaded_file = st.file_uploader("匿名化した記録データ(CSV)を選択してください", type="csv")

if uploaded_file is not None:
    try:
        # CSVの読み込み（文字コードエラー対策済み）
        try:
            df = pd.read_csv(uploaded_file, encoding="cp932")
        except:
            df = pd.read_csv(uploaded_file, encoding="utf-8")
        
        # 🚨 【安全装置】個人情報の列が含まれていないかチェック 🚨
        forbidden_keywords = [
            "氏名", "名前", "なまえ", "住所", "電話", "連絡先", "メール", "生年月日", "年齢",
            "対象者", "利用者", "メンバー"
        ]
        danger_columns = []
        
        for col in df.columns:
            if any(keyword in str(col) for keyword in forbidden_keywords):
                danger_columns.append(col)
        
        # 危険な列が見つかったら強制ストップ
        if danger_columns:
            st.error(f"🛑 セキュリティブロックが作動しました！🛑\n\nアップロードされたデータに、個人情報が含まれている可能性のある列（ **{', '.join(danger_columns)}** ）が見つかりました。\n\n安全のためAIへの送信を中止しました。Excel等でこの列を削除してから、再度アップロードしてください。")
            st.stop()
            
        st.success("✅ データの安全性チェック完了。個人情報を含む可能性のある列は検出されませんでした！")
        
        # データの一部を表示
        st.write("▼ 読み込んだデータの一部")
        st.dataframe(df.head(3), use_container_width=True)
        
        # 解析ボタン
        if st.button("✨ 記録を分析して計画書案を作る", type="primary", use_container_width=True):
            # スピナーにも待ち時間に関するメッセージを追加
            with st.spinner("AIが膨大な記録を読み込み、要点をまとめています...（※データ量が多い場合は30秒〜1分ほどお待ちください）"):
                
                # CSVデータをテキスト化（上限を50,000文字）
                csv_text = df.to_string(index=False)
                
                prompt = f"""
                あなたは凄腕の就労支援員（サービス管理責任者）です。
                以下の「匿名化された日々の面談記録・訓練ログ」を分析し、次期の支援計画書を作成するための【補助資料】を作成してください。

                【解析するデータ】
                {csv_text[:50000]}

                【出力のルール】
                ・専門的な視点を持ちつつ、温かく前向きな表現を使ってください。
                ・データにない項目（家族の意向など）は「記録からは確認できません」とし、無理に推測しないでください。
                ・以下の項目で出力してください。

                ### 1. 📈 期間中の変化と現状（サマリー）
                （記録全体から見える、本人の体調や活動量の推移）
                ### 2. ✨ 発揮された強み・ポジティブな変化
                （本人ができたこと、褒められたこと、以前より改善した点）
                ### 3. ⚠️ 課題点とつまずきの傾向
                （どのような場面で不安になったり、作業が止まったりしたかの分析）
                ### 4. 🧭 次期の「短期目標」案
                （記録に基づいた、具体的で達成可能なスモールステップな目標）
                ### 5. 🤝 効果的だった支援・環境調整の提案
                （「こう声をかけたら上手くいった」「この環境だと安定していた」という現場へのヒント）
                """

                # ★ 変更点3：client経由で実行するように変更
                response = client.models.generate_content(
                    model=TARGET_MODEL,
                    contents=prompt
                )
                
                st.markdown("---")
                st.header("📋 AIからの分析・提案")
                st.info("※この内容はAIによるドラフトです。必ず支援員が内容を精査し、必要に応じて修正してください。")
                st.markdown(response.text)

                # ★★★ ここから保存・ダウンロード機能 ★★★
                st.markdown("---")
                st.subheader("💾 結果の保存・ダウンロード")
                st.write("支援計画書の作成ソフトに貼り付けやすい「テキスト形式」と、印刷や共有に便利な「PDF保存用」の2種類をご用意しました。")
                
                # 1. テキスト形式のデータ
                result_text = response.text
                
                # 2. HTML形式のデータ（印刷・PDF用）
                result_formatted = result_text.replace('\n', '<br>')
                report_html = f"""
                <html><head><meta charset="UTF-8"><title>AI支援計画書案</title>
                <style>
                    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 30px; background-color: #FAFAF7; }}
                    h1 {{ color: #4A90E2; border-bottom: 2px solid #4A90E2; padding-bottom: 10px; font-size: 24px; text-align: center; }}
                    .warning {{ background-color: #fff5f5; color: #ff4b4b; padding: 15px; border-radius: 8px; font-weight: bold; margin-bottom: 20px; }}
                    .content {{ background: #ffffff; padding: 25px; border-radius: 15px; border: 1px solid #ddd; margin-bottom: 20px; }}
                    .print-btn {{ display: block; width: 250px; margin: 20px auto; padding: 12px; text-align: center; background: #4A90E2; color: #fff; text-decoration: none; border-radius: 30px; cursor: pointer; border: none; font-size: 16px; font-weight: bold; }}
                    @media print {{ body {{ background-color: #fff; }} .no-print {{ display: none !important; }} }}
                </style></head>
                <body>
                    <button class="no-print print-btn" onclick="window.print()">🖨️ PDFとして保存 / 印刷する</button>
                    <h1>📝 AI支援計画書 ドラフト案</h1>
                    <div class="warning">⚠️ この内容はAIによる自動作成ドラフトです。必ず支援員が内容を精査・修正してご活用ください。</div>
                    <p style="text-align:right; font-size: 12px; color: #888;">作成日: {datetime.datetime.now().strftime('%Y年%m月%d日')}</p>
                    <div class="content">
                        {result_formatted}
                    </div>
                </body></html>
                """

                # 横に2つボタンを並べる
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📄 テキスト(.txt)で保存",
                        data=result_text,
                        file_name=f"支援計画書案_{datetime.datetime.now().strftime('%Y%m%d')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with col2:
                    st.download_button(
                        label="🖨️ 印刷・PDF用(.html)で保存",
                        data=report_html,
                        file_name=f"支援計画書案_{datetime.datetime.now().strftime('%Y%m%d')}.html",
                        mime="text/html",
                        use_container_width=True
                    )
                
    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生しました。ファイル形式を確認してください: {e}")
