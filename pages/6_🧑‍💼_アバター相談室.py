import streamlit as st
# ★ 変更点1：新しいパッケージのインポート
from google import genai
from google.genai import types
import edge_tts
import asyncio
import base64
import os
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore

# --- 画面の設定 ---
st.set_page_config(page_title="アバター相談室", page_icon="🧑‍💼", layout="wide")

# ==========================================
# 🚨 セキュリティバウンサー & データベース初期化 (マルチアプリ対応)
# ==========================================
if "user_email" not in st.session_state:
    st.warning("⚠️ ログインが必要です。左のメニューから「Home」に戻ってログインしてください。")
    st.stop()

# --- 🌟 自分専用の接続窓口名 ---
APP_NAME = "ai_matching_app"

if APP_NAME not in firebase_admin._apps:
    try:
        key_dict = dict(st.secrets["firebase_ai_matching"])
        cred = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(cred, name=APP_NAME)
    except Exception as e:
        st.error(f"ai-job-matching への接続に失敗しました: {e}")
        st.stop()
app = firebase_admin.get_app(APP_NAME)
db = firestore.client(app=app)

st.sidebar.success(f"🔌 接続先: {app.project_id}")
user_id = st.session_state.user_email

# === 🔑 APIキーの読み込み ===
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # ★ 変更点2：Client（通信係）を作成
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("⚠️ `.streamlit/secrets.toml` に APIキーを設定してください。")
    st.stop()

# もし混雑エラーが続く場合は、ここを "gemini-1.5-flash" に変更してください
TARGET_MODEL = "gemini-3.1-flash-lite"
VRM_DIR = "vrm_models"
os.makedirs(VRM_DIR, exist_ok=True)
vrm_files = [f for f in os.listdir(VRM_DIR) if f.endswith(".vrm")]

if not vrm_files:
    st.error(f"⚠️ `{VRM_DIR}` フォルダにVRMファイルがありません。")
    st.stop()

ALLOWED_VRMS = ["AI女性スタッフ.vrm", "AI男性スタッフ.vrm"]
allowed_vrm_files = [f for f in vrm_files if f in ALLOWED_VRMS]

if not allowed_vrm_files:
    st.error(f"⚠️ フォルダ内に「AI女性スタッフ.vrm」または「AI男性スタッフ.vrm」が見つかりません。")
    st.stop()

def save_settings_to_db():
    try:
        doc_ref = db.collection('user_settings').document(user_id)
        doc_ref.set({
            'vrm_name': st.session_state.vrm_name,
            'system_prompt': st.session_state.system_prompt,
            'voice_type': st.session_state.voice_type,
            'selected_speed': st.session_state.selected_speed,
            'input_mode': st.session_state.input_mode
        }, merge=True)
        return True, ""
    except Exception as e:
        return False, str(e)

def load_settings_from_db():
    try:
        doc = db.collection('user_settings').document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            db_vrm = data.get('vrm_name', "")
            st.session_state.vrm_name = db_vrm if db_vrm in allowed_vrm_files else allowed_vrm_files[0]
            st.session_state.system_prompt = data.get('system_prompt', "あなたは就労移行支援事業所の優しいサポートスタッフです。")
            st.session_state.voice_type = data.get('voice_type', "👩 女性")
            st.session_state.selected_speed = data.get('selected_speed', "標準")
            st.session_state.input_mode = data.get('input_mode', "🎙️ 音声モード")
            return True
    except:
        pass
    return False

if "avatar_messages" not in st.session_state: st.session_state.avatar_messages = []
if "latest_audio_b64" not in st.session_state: st.session_state.latest_audio_b64 = ""
if "last_audio_val" not in st.session_state: st.session_state.last_audio_val = None

if "settings_loaded" not in st.session_state:
    if not load_settings_from_db():
        st.session_state.vrm_name = allowed_vrm_files[0]
        st.session_state.system_prompt = "あなたは就労移行支援事業所の優しいサポートスタッフです。利用者の日々の悩みには共感をもって寄り添い、ビジネスマナーやオフィス系ソフト等の質問には初心者にもわかるよう丁寧に答えてください。AIとは名乗らず、人間として自然に振る舞ってください。質問者のことは、質問者さんということ。回答は基本簡潔にし、質問者から求められたりどうしても必要な時は少し長くなってもよい。"
        st.session_state.voice_type = "👩 女性"
        st.session_state.selected_speed = "標準"
        st.session_state.input_mode = "🎙️ 音声モード"
    st.session_state.settings_loaded = True

async def _generate_audio(text, voice, rate):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data.extend(chunk["data"])
    return bytes(audio_data)

def generate_audio(text, voice, rate):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_generate_audio(text, voice, rate))
    loop.close()
    return result

@st.cache_data(show_spinner=False)
def get_base64_vrm(file_path):
    with open(file_path, "rb") as f: return f"data:application/octet-stream;base64,{base64.b64encode(f.read()).decode()}"

def get_base64_audio(audio_bytes):
    return f"data:audio/mp3;base64,{base64.b64encode(audio_bytes).decode()}"

with st.sidebar:
    st.header("⚙️ 相談室の設定")
    st.session_state.input_mode = st.radio("⌨️ 入力方法", ["🎙️ 音声モード", "⌨️ テキストモード"], index=0 if "音声" in st.session_state.input_mode else 1)
    st.markdown("---")
    
    vrm_idx = allowed_vrm_files.index(st.session_state.vrm_name) if st.session_state.vrm_name in allowed_vrm_files else 0
    st.session_state.vrm_name = st.selectbox("🧑‍💼 アバターを選択", allowed_vrm_files, index=vrm_idx)
        
    st.session_state.system_prompt = st.text_area("📝 キャラクター設定", st.session_state.system_prompt, height=150)
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.session_state.voice_type = st.selectbox("🗣️ 声のタイプ", ["👩 女性", "👨 男性"], index=0 if "女性" in st.session_state.voice_type else 1)
    with col_v2:
        speed_opts = ["ゆっくり", "標準", "少し速め", "速い"]
        spd_idx = speed_opts.index(st.session_state.selected_speed) if st.session_state.selected_speed in speed_opts else 1
        st.session_state.selected_speed = st.selectbox("⏱️ 話す速さ", speed_opts, index=spd_idx)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 設定を保存する", use_container_width=True, type="primary"):
        with st.spinner("保存中..."):
            success, err = save_settings_to_db()
            if success: st.success("✅ ai-job-matching に保存しました！")
            else: st.error(f"❌ 保存失敗: {err}")
    st.markdown("---")
    if st.button("🗑️ 会話をリセット", use_container_width=True):
        st.session_state.avatar_messages = []
        st.session_state.latest_audio_b64 = ""
        st.session_state.last_audio_val = None
        st.rerun()

vrm_path = os.path.join(VRM_DIR, st.session_state.vrm_name)
voice_model = "ja-JP-NanamiNeural" if "女性" in st.session_state.voice_type else "ja-JP-KeitaNeural"
speed_map = {"ゆっくり": "-25%", "標準": "+0%", "少し速め": "+20%", "速い": "+50%"}
voice_rate = speed_map[st.session_state.selected_speed]

st.title("🧑‍💼 AIアバター相談室")
col_avatar, col_chat = st.columns([1.2, 1])

with col_avatar:
    with st.container(border=True):
        vrm_data_uri = get_base64_vrm(vrm_path)
        audio_data_uri = st.session_state.latest_audio_b64
        
        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ margin: 0; overflow: hidden; background-color: #F0F4F8; border-radius: 10px; cursor: default; }}
                #canvas-container {{ width: 100%; height: 500px; }}
                #play-button {{
                    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                    padding: 15px 30px; font-size: 18px; font-weight: bold; background-color: #2A9D8F; 
                    color: white; border: none; border-radius: 30px; cursor: pointer; z-index: 10;
                }}
            </style>
            <script type="importmap">
              {{
                "imports": {{
                  "three": "https://unpkg.com/three@0.154.0/build/three.module.js",
                  "three/addons/": "https://unpkg.com/three@0.154.0/examples/jsm/",
                  "@pixiv/three-vrm": "https://unpkg.com/@pixiv/three-vrm@2.0.6/lib/three-vrm.module.js"
                }}
              }}
            </script>
        </head>
        <body>
            <div id="canvas-container"></div>
            <button id="play-button" style="display: none;">🔊 返答を聞く</button>
            <script type="module">
                import * as THREE from 'three';
                import {{ GLTFLoader }} from 'three/addons/loaders/GLTFLoader.js';
                import {{ VRMLoaderPlugin, VRMUtils }} from '@pixiv/three-vrm';

                const vrmDataUrl = "{vrm_data_uri}";
                const audioDataUrl = "{audio_data_uri}";
                let currentVrm = null, analyser = null, dataArray = null, isPlaying = false;

                const scene = new THREE.Scene();
                const camera = new THREE.PerspectiveCamera(35, window.innerWidth / 500, 0.1, 20.0);
                camera.position.set(0.0, 1.45, 1.1);
                const renderer = new THREE.WebGLRenderer({{ alpha: true, antialias: true }});
                renderer.setSize(window.innerWidth, 500);
                renderer.outputColorSpace = THREE.SRGBColorSpace;
                document.getElementById('canvas-container').appendChild(renderer.domElement);

                scene.add(new THREE.DirectionalLight(0xffffff, 0.5));
                scene.add(new THREE.AmbientLight(0xffffff, 0.4));

                const loader = new GLTFLoader();
                loader.register((parser) => new VRMLoaderPlugin(parser));
                loader.load(vrmDataUrl, (gltf) => {{
                    const vrm = gltf.userData.vrm;
                    VRMUtils.removeUnnecessaryJoints(gltf.scene);
                    scene.add(vrm.scene);
                    vrm.scene.rotation.y = Math.PI;
                    
                    vrm.humanoid.getNormalizedBoneNode('leftUpperArm').rotation.z = 1.45;
                    vrm.humanoid.getNormalizedBoneNode('rightUpperArm').rotation.z = -1.45;
                    
                    currentVrm = vrm;
                    if (audioDataUrl && audioDataUrl !== "data:audio/mp3;base64,") setupAudio();
                }});

                function setupAudio() {{
                    const audio = new Audio(audioDataUrl);
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    const source = audioContext.createMediaElementSource(audio);
                    analyser = audioContext.createAnalyser();
                    source.connect(analyser);
                    analyser.connect(audioContext.destination);
                    dataArray = new Uint8Array(analyser.frequencyBinCount);
                    const playBtn = document.getElementById('play-button');
                    audio.play().then(() => isPlaying = true).catch(() => {{
                        playBtn.style.display = "block";
                        playBtn.onclick = () => {{ audioContext.resume(); audio.play(); isPlaying = true; playBtn.style.display = "none"; }};
                    }});
                    audio.onended = () => {{ isPlaying = false; if(currentVrm) currentVrm.expressionManager.setValue('aa', 0); }};
                }}

                const raycaster = new THREE.Raycaster();
                const mouse = new THREE.Vector2();
                let targetMouseX = 0;
                let targetMouseY = 0;
                let currentMouseX = 0;
                let currentMouseY = 0;

                let isClickReacting = false;
                let clickReactionTimer = 0;
                let clickReactionType = 1; 

                renderer.domElement.addEventListener('pointermove', (event) => {{
                    const rect = renderer.domElement.getBoundingClientRect();
                    targetMouseX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                    targetMouseY = -((event.clientY - rect.top) / rect.height) * 2 + 1;
                }});

                renderer.domElement.addEventListener('pointerleave', () => {{
                    targetMouseX = 0;
                    targetMouseY = 0;
                }});

                renderer.domElement.addEventListener('pointerdown', (event) => {{
                    const rect = renderer.domElement.getBoundingClientRect();
                    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

                    raycaster.setFromCamera(mouse, camera);

                    if (currentVrm && !isPlaying && !isClickReacting) {{
                        const intersects = raycaster.intersectObjects(currentVrm.scene.children, true);
                        if (intersects.length > 0) {{
                            isClickReacting = true;
                            clickReactionTimer = 0;
                            
                            if (intersects[0].point.y > 1.3) {{
                                clickReactionType = 1; 
                            }} else {{
                                clickReactionType = 2; 
                            }}
                        }}
                    }}
                }});

                const clock = new THREE.Clock();
                let blinkTimer = 0;
                let isBlinking = false;
                let idleAction = 0; 
                let idleTimer = 0;
                let idleDuration = 3;
                let lookDirection = 1;

                function animate() {{
                    requestAnimationFrame(animate);
                    const deltaTime = clock.getDelta();
                    const elapsedTime = clock.elapsedTime;

                    currentMouseX += (targetMouseX - currentMouseX) * deltaTime * 5.0;
                    currentMouseY += (targetMouseY - currentMouseY) * deltaTime * 5.0;

                    let mouseHeadY = currentMouseX * 0.6;
                    let mouseHeadX = currentMouseY * 0.3;
                    let mouseNeckY = currentMouseX * 0.3;
                    let mouseNeckX = currentMouseY * 0.15;
                    let mouseSpineY = currentMouseX * 0.1;

                    if (currentVrm) {{
                        const spine = currentVrm.humanoid.getNormalizedBoneNode('spine');
                        const chest = currentVrm.humanoid.getNormalizedBoneNode('chest');
                        const neck = currentVrm.humanoid.getNormalizedBoneNode('neck');
                        const head = currentVrm.humanoid.getNormalizedBoneNode('head');
                        const leftUpperArm = currentVrm.humanoid.getNormalizedBoneNode('leftUpperArm');
                        const rightUpperArm = currentVrm.humanoid.getNormalizedBoneNode('rightUpperArm');
                        const leftLowerArm = currentVrm.humanoid.getNormalizedBoneNode('leftLowerArm');
                        const rightLowerArm = currentVrm.humanoid.getNormalizedBoneNode('rightLowerArm');
                        
                        if (isPlaying) {{
                            if (leftUpperArm && rightUpperArm && leftLowerArm && rightLowerArm) {{
                                leftUpperArm.rotation.z = 1.45 + Math.sin(elapsedTime * 1.5) * 0.02; 
                                leftUpperArm.rotation.x = -0.3; 
                                leftUpperArm.rotation.y = 0;
                                leftLowerArm.rotation.z = 0; 
                                leftLowerArm.rotation.x = 0;
                                rightUpperArm.rotation.z = -1.45 - Math.cos(elapsedTime * 1.2) * 0.02; 
                                rightUpperArm.rotation.x = -0.3; 
                                rightUpperArm.rotation.y = 0;
                                rightLowerArm.rotation.z = 0; 
                                rightLowerArm.rotation.x = 0;
                            }}
                            if (spine) {{
                                spine.rotation.x = 0;
                                spine.rotation.y = mouseSpineY + Math.sin(elapsedTime * 1.0) * 0.15; 
                                spine.rotation.z = Math.sin(elapsedTime * 1.5) * 0.12; 
                            }}
                            if (chest) {{
                                chest.rotation.x = 0;
                                chest.rotation.z = Math.cos(elapsedTime * 1.5) * 0.06; 
                            }}
                            if (neck) {{
                                neck.rotation.x = mouseNeckX;
                                neck.rotation.y = mouseNeckY;
                                neck.rotation.z = 0;
                            }}
                            if (head) {{
                                head.rotation.x = mouseHeadX;
                                head.rotation.y = mouseHeadY;
                                head.rotation.z = Math.sin(elapsedTime * 1.5) * 0.08; 
                            }}
                            idleTimer = 0;
                            idleAction = 0;
                        }} else {{
                            let targetLeftArmZ = 1.45 + Math.sin(elapsedTime * 0.8) * 0.01;
                            let targetLeftArmX = -0.1;
                            let targetRightArmZ = -1.45 - Math.sin(elapsedTime * 0.8) * 0.01;
                            let targetRightArmX = -0.1;
                            
                            let targetSpineX = 0;
                            let targetHeadY = mouseHeadY;
                            let targetHeadX = mouseHeadX;
                            let targetNeckY = mouseNeckY;
                            let targetNeckX = mouseNeckX;

                            if (isClickReacting) {{
                                clickReactionTimer += deltaTime;
                                
                                if (clickReactionType === 1) {{
                                    let reactionDuration = 0.8;
                                    if (clickReactionTimer > reactionDuration) {{
                                        isClickReacting = false;
                                        currentVrm.expressionManager.setValue('Surprised', 0);
                                        currentVrm.expressionManager.setValue('surprised', 0);
                                        currentVrm.expressionManager.setValue('oh', 0);
                                    }} else {{
                                        let t = clickReactionTimer / reactionDuration;
                                        let amount = (Math.sin(t * Math.PI)) * 0.3;
                                        let exprAmount = Math.sin(t * Math.PI); 
                                        
                                        targetSpineX = amount;
                                        targetHeadX = mouseHeadX + amount * 0.5;
                                        targetLeftArmZ = 1.45 - (amount * 0.5);
                                        targetRightArmZ = -1.45 + (amount * 0.5);
                                        idleTimer = 0;
                                        
                                        currentVrm.expressionManager.setValue('Surprised', exprAmount);
                                        currentVrm.expressionManager.setValue('surprised', exprAmount);
                                        currentVrm.expressionManager.setValue('oh', exprAmount * 0.8);
                                    }}
                                }} else if (clickReactionType === 2) {{
                                    let reactionDuration = 1.2;
                                    if (clickReactionTimer > reactionDuration) {{
                                        isClickReacting = false;
                                        currentVrm.expressionManager.setValue('Surprised', 0);
                                        currentVrm.expressionManager.setValue('surprised', 0);
                                        currentVrm.expressionManager.setValue('oh', 0);
                                    }} else {{
                                        let t = clickReactionTimer / reactionDuration;
                                        let fade = Math.sin(t * Math.PI); 
                                        
                                        let flap = Math.sin(elapsedTime * 25) * 0.4;
                                        
                                        targetLeftArmZ = 1.2 + (flap * fade); 
                                        targetRightArmZ = -1.2 + (flap * fade);
                                        targetLeftArmX = -0.3 * fade; 
                                        targetRightArmX = -0.3 * fade;
                                        
                                        targetSpineX = Math.sin(elapsedTime * 20) * 0.05 * fade;
                                        targetHeadX = mouseHeadX + Math.sin(elapsedTime * 15) * 0.05 * fade; 
                                        
                                        idleTimer = 0;
                                        
                                        currentVrm.expressionManager.setValue('Surprised', fade);
                                        currentVrm.expressionManager.setValue('surprised', fade);
                                        currentVrm.expressionManager.setValue('oh', fade * 0.6); 
                                    }}
                                }}
                            }} 
                            else {{
                                idleTimer += deltaTime;
                                if (idleTimer > idleDuration) {{
                                    idleTimer = 0;
                                    let r = Math.random();
                                    if (r < 0.6) {{ idleAction = 0; idleDuration = 3 + Math.random() * 5; }}
                                    else if (r < 0.75) {{ idleAction = 1; idleDuration = 2.5 + Math.random() * 2; lookDirection = Math.random() > 0.5 ? 1 : -1; }}
                                    else if (r < 0.85) {{ idleAction = 2; idleDuration = 2.0; }}
                                    else {{ idleAction = 3; idleDuration = 3.0; }}
                                }}
                                let t = idleTimer / idleDuration;
                                let actionAmount = Math.sin(t * Math.PI); 

                                if (idleAction === 1) {{ targetHeadY += lookDirection * 0.8 * actionAmount; }}
                                else if (idleAction === 2) {{ targetSpineX += -actionAmount * 0.5; targetHeadX += -actionAmount * 0.3; targetLeftArmZ = 1.45 - actionAmount * 0.3; targetRightArmZ = -1.45 + actionAmount * 0.3; }}
                                else if (idleAction === 3) {{ targetSpineX += actionAmount * 0.15; targetHeadX += actionAmount * 0.2; targetLeftArmZ = 1.45 - actionAmount * 2.5; targetLeftArmX = -0.1 - actionAmount * 1.5; targetRightArmZ = -1.45 + actionAmount * 2.5; targetRightArmX = -0.1 - actionAmount * 1.5; }}
                            }}

                            if (spine) {{ spine.rotation.z = 0; spine.rotation.y = mouseSpineY + Math.sin(elapsedTime * 0.8) * 0.05; spine.rotation.x = targetSpineX; }}
                            if (chest) {{ chest.rotation.z = 0; chest.rotation.x = Math.sin(elapsedTime * 1.2) * 0.03; }}
                            if (neck) {{ neck.rotation.z = 0; neck.rotation.y = targetNeckY; neck.rotation.x = targetNeckX; }}
                            if (head) {{ head.rotation.z = 0; head.rotation.y = targetHeadY; head.rotation.x = targetHeadX; }}
                            if (leftUpperArm && rightUpperArm) {{
                                leftUpperArm.rotation.z = targetLeftArmZ; leftUpperArm.rotation.x = targetLeftArmX; leftUpperArm.rotation.y = 0;
                                leftLowerArm.rotation.z = 0; leftLowerArm.rotation.x = 0;
                                rightUpperArm.rotation.z = targetRightArmZ; rightUpperArm.rotation.x = targetRightArmX; rightUpperArm.rotation.y = 0;
                                rightLowerArm.rotation.z = 0; rightLowerArm.rotation.x = 0;
                            }}
                        }}

                        blinkTimer += deltaTime;
                        if (!isBlinking && blinkTimer > 3 + Math.random() * 4) {{ isBlinking = true; blinkTimer = 0; }}
                        if (isBlinking) {{
                            let blinkValue = 0;
                            if (blinkTimer < 0.1) blinkValue = blinkTimer / 0.1;
                            else if (blinkTimer < 0.2) blinkValue = 1.0 - ((blinkTimer - 0.1) / 0.1);
                            else {{ isBlinking = false; blinkTimer = 0; blinkValue = 0; }}
                            currentVrm.expressionManager.setValue('blink', blinkValue);
                        }}

                        currentVrm.update(deltaTime);

                        if (isPlaying && analyser) {{
                            analyser.getByteFrequencyData(dataArray);
                            let sum = 0;
                            for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                            currentVrm.expressionManager.setValue('aa', Math.min(1.0, (sum / dataArray.length / 50.0)));
                        }}
                    }}
                    renderer.render(scene, camera);
                }}
                animate();
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=500)

with col_chat:
    st.markdown(f"### {st.session_state.input_mode}")
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.avatar_messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

    user_input = None
    if "🎙️" in st.session_state.input_mode:
        audio_val = st.audio_input("マイク", label_visibility="collapsed")
        if audio_val and audio_val != st.session_state.last_audio_val:
            st.session_state.last_audio_val = audio_val
            with st.spinner("AIがあなたの声を届け中..."):
                try:
                    # ★ 変更点3：音声文字起こしの新しい書き方
                    audio_part = types.Part.from_bytes(data=audio_val.getvalue(), mime_type="audio/wav")
                    
                    t_res = client.models.generate_content(
                        model=TARGET_MODEL,
                        contents=[audio_part, "音声データを文字起こししてください。声が入っていない場合や無音の場合は「無音」とだけ出力してください。"]
                    )
                    stt_text = t_res.text
                    
                    if stt_text and "無音" not in stt_text:
                        user_input = stt_text
                    else:
                        st.warning("音声がうまく聞き取れませんでした。もう一度マイクを押して話しかけてください。")
                except Exception as e: 
                    st.error(f"音声の読み取りに失敗しました: {e}")
    else:
        user_input = st.chat_input("質問や相談を入力してEnter")

    if user_input:
        st.session_state.avatar_messages.append({"role": "user", "content": user_input})
        with st.spinner("AI支援員が返答を考え中..."):
            try:
                # ★ 変更点4：チャットセッションの新しい書き方
                config = types.GenerateContentConfig(system_instruction=st.session_state.system_prompt)
                
                # 履歴を新しい形式に変換して渡す
                formatted_history = []
                for m in st.session_state.avatar_messages[:-1]: # 最新の入力以外を履歴にする
                    role = "model" if m["role"] == "assistant" else "user"
                    formatted_history.append(
                        types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
                    )
                
                # チャットを作成してメッセージを送信
                chat = client.chats.create(model=TARGET_MODEL, config=config, history=formatted_history)
                response = chat.send_message(user_input)
                ai_text = response.text
                
                clean_ai_text = ai_text.strip()
                if not clean_ai_text:
                    clean_ai_text = "すみません、うまく言葉を返せませんでした。"
                    ai_text = clean_ai_text

                if "🎙️" in st.session_state.input_mode:
                    try:
                        ai_audio_bytes = generate_audio(clean_ai_text, voice_model, voice_rate)
                        if not ai_audio_bytes:
                            raise ValueError("音声データが空です")
                        st.session_state.latest_audio_b64 = get_base64_audio(ai_audio_bytes)
                    except Exception as audio_err:
                        st.session_state.latest_audio_b64 = ""
                        st.toast("⚠️ 絵文字などのため音声化をスキップしました", icon="🔇")
                else: 
                    st.session_state.latest_audio_b64 = ""
                
                st.session_state.avatar_messages.append({"role": "assistant", "content": ai_text})
                st.rerun()
            except Exception as e: 
                st.error(f"エラー: {e}")
