package com.live2d;

import com.live2d.core.Core;

import java.util.HashMap;
import java.util.Map;

/**
 * 表情控制器
 * <p>
 * 负责：
 * 1. 情绪 → Live2D 参数映射（neutral/joy/anger/sadness/surprise/shy/think/fear/cry）
 * 2. 情绪切换的平滑插值（lerp）
 * 3. 音频 RMS 驱动的嘴型同步
 * 4. 特殊情绪的额外参数控制（如哭泣时的半闭眼）
 * <p>
 * 由 SpeechBubble 提供 emotion / audioRms 数据，Main.loop() 每帧调用 update()。
 */
public class ExpressionController {

    // ============================================================
    //  情绪 → 参数映射表
    //  参数名必须与 hiyori_free_t08 模型 cdi3.json 中的 ID 完全一致
    // ============================================================
    private static final String[] PARAM_NAMES = {
            "ParamEyeLSmile",    // 0 - 左眼笑眯 (0~1)
            "ParamEyeRSmile",    // 1 - 右眼笑眯 (0~1)
            "ParamMouthForm",    // 2 - 嘴型形状 (-1=悲 ~ 1=笑)
            "ParamBrowLForm",    // 3 - 左眉变形 (-1=皱 ~ 1=挑)
            "ParamBrowRForm",    // 4 - 右眉变形 (-1=皱 ~ 1=挑)
            "ParamCheek",        // 5 - 脸红 (0~1)
    };

    // 额外控制的参数（不在基础映射表中，由特殊逻辑驱动）
    private static final String PARAM_EYE_L_OPEN = "ParamEyeLOpen";
    private static final String PARAM_EYE_R_OPEN = "ParamEyeROpen";

    private static final Map<String, float[]> EMOTION_PARAMS = new HashMap<>();

    static {
        //                              smile_L  smile_R  mouth   browL   browR   cheek
        EMOTION_PARAMS.put("neutral",  new float[]{0.0f,  0.0f,   0.0f,   0.0f,   0.0f,  0.0f});
        EMOTION_PARAMS.put("joy",      new float[]{0.7f,  0.7f,   0.8f,   0.3f,   0.3f,  0.5f});
        EMOTION_PARAMS.put("anger",    new float[]{0.0f,  0.0f,  -0.4f,  -0.7f,  -0.7f,  0.0f});
        EMOTION_PARAMS.put("sadness",  new float[]{0.0f,  0.0f,  -0.5f,  -0.3f,  -0.3f,  0.0f});
        EMOTION_PARAMS.put("surprise", new float[]{0.0f,  0.0f,   0.3f,   0.8f,   0.8f,  0.0f});
        EMOTION_PARAMS.put("shy",      new float[]{0.5f,  0.5f,   0.3f,   0.1f,   0.1f,  0.8f});
        EMOTION_PARAMS.put("think",    new float[]{0.0f,  0.0f,  -0.1f,   0.3f,  -0.2f,  0.0f});
        EMOTION_PARAMS.put("fear",     new float[]{0.0f,  0.0f,   0.0f,   0.6f,   0.6f,  0.0f});
        EMOTION_PARAMS.put("cry",      new float[]{0.6f,  0.6f,  -0.6f,  -0.4f,  -0.4f,  0.4f});
    }

    // 需要额外控制眼睛开合的情绪 → 目标 EyeOpen 值（null 表示不干预，由 Main.java 的眨眼逻辑控制）
    private static final Map<String, Float> EMOTION_EYE_OPEN = new HashMap<>();
    static {
        EMOTION_EYE_OPEN.put("cry",      0.35f);   // 哭泣：半闭眼，泪眼效果
        EMOTION_EYE_OPEN.put("surprise", 1.0f);    // 惊讶：睁大眼
        EMOTION_EYE_OPEN.put("fear",     0.85f);   // 害怕：微眯（紧张）
    }

    // ============================================================
    //  运行时状态
    // ============================================================

    // 情绪
    private String currentEmotion = "neutral";
    private String targetEmotion = "neutral";

    // 当前/目标表情参数（与 PARAM_NAMES 一一对应）
    private final float[] currentParams = new float[PARAM_NAMES.length];
    private final float[] targetParams = new float[PARAM_NAMES.length];

    // 眼睛开合（用于哭泣/惊讶等特殊控制）
    private float currentEyeOpen = 1.0f;
    private float targetEyeOpen = 1.0f;
    private boolean emotionControlsEyes = false;

    // 嘴型同步
    private float currentMouthOpen = 0.0f;
    private float targetMouthOpen = 0.0f;
    private volatile float audioRms = 0.0f;
    private long lastRmsUpdateTime = 0;

    // Viseme 口型同步（Rhubarb Lip Sync，优先级高于 RMS）
    private volatile float visemeOpenY = 0.0f;
    private volatile float visemeForm = 0.0f;
    private long lastVisemeUpdateTime = 0;
    private float currentVisemeForm = 0.0f;   // 平滑插值后的 MouthForm
    private boolean visemeActive = false;      // 是否有活跃的 viseme 数据

    // ============================================================
    //  调参常量
    // ============================================================
    /** 情绪参数过渡速度（0-1，越大越快） */
    private static final float EMOTION_SMOOTHING = 0.06f;
    /** 嘴型响应速度 */
    private static final float MOUTH_SMOOTHING = 0.35f;
    /** RMS 无更新后多久开始衰减 (ms) */
    private static final long RMS_TIMEOUT_MS = 150;
    /** RMS → 嘴张开程度的缩放系数 */
    private static final float RMS_SCALE = 5.0f;
    /** Viseme 无更新后多久开始衰减 (ms) */
    private static final long VISEME_TIMEOUT_MS = 200;
    /** Viseme 口型平滑速度（稍快于情绪，保证口型灵敏） */
    private static final float VISEME_FORM_SMOOTHING = 0.25f;

    // ============================================================
    //  构造
    // ============================================================
    public ExpressionController() {
        float[] neutral = EMOTION_PARAMS.get("neutral");
        System.arraycopy(neutral, 0, currentParams, 0, neutral.length);
        System.arraycopy(neutral, 0, targetParams, 0, neutral.length);
        System.out.println("[ExpressionController] 初始化完成 (支持情绪: "
                + String.join(", ", EMOTION_PARAMS.keySet()) + ")");
    }

    // ============================================================
    //  外部设置
    // ============================================================

    /**
     * 设置目标情绪（自动做名称校验）
     */
    public void setEmotion(String emotion) {
        if (emotion == null || emotion.isEmpty()) {
            emotion = "neutral";
        }
        emotion = emotion.toLowerCase();
        if (!EMOTION_PARAMS.containsKey(emotion)) {
            emotion = "neutral";
        }
        if (!emotion.equals(this.targetEmotion)) {
            this.targetEmotion = emotion;
            float[] params = EMOTION_PARAMS.get(emotion);
            System.arraycopy(params, 0, targetParams, 0, params.length);
            
            // 检查是否需要控制眼睛开合
            if (EMOTION_EYE_OPEN.containsKey(emotion)) {
                emotionControlsEyes = true;
                targetEyeOpen = EMOTION_EYE_OPEN.get(emotion);
            } else {
                emotionControlsEyes = false;
                targetEyeOpen = 1.0f; // 恢复正常
            }
            
            System.out.println("[Expression] 情绪: " + currentEmotion + " → " + emotion);
        }
    }

    /**
     * 设置音频 RMS 值（由 SpeechBubble WebSocket 接收后传入）
     */
    public void setAudioRms(float rms) {
        this.audioRms = Math.max(0.0f, rms);
        this.lastRmsUpdateTime = System.currentTimeMillis();
    }

    /**
     * 设置 Viseme 口型数据（由 Rhubarb Lip Sync 生成，优先于 RMS）
     *
     * @param openY 嘴张开程度 (0~1)
     * @param form  嘴型形状 (-1~1，负=圆/悄 正=平/笑)
     */
    public void setViseme(float openY, float form) {
        this.visemeOpenY = Math.max(0.0f, Math.min(1.0f, openY));
        this.visemeForm = Math.max(-1.0f, Math.min(1.0f, form));
        this.lastVisemeUpdateTime = System.currentTimeMillis();
        this.visemeActive = true;
    }

    // ============================================================
    //  每帧更新
    // ============================================================

    /**
     * 每帧调用，将情绪 + 嘴型参数写入 Cubism Core
     *
     * @param core        Cubism Core 实例
     * @param elapsedTime 从启动到现在的秒数（用于空闲微动画）
     */
    public void update(Core core, double elapsedTime) {
        if (core == null || !core.isInitialized()) return;

        // ---- 1. 情绪表情参数平滑过渡 ----
        for (int i = 0; i < PARAM_NAMES.length; i++) {
            currentParams[i] += (targetParams[i] - currentParams[i]) * EMOTION_SMOOTHING;

            // 眉毛加一点自然微动
            if (i == 3 || i == 4) {
                float jitter = (float) (Math.sin(elapsedTime * 1.5 + i * 0.5) * 0.05);
                core.setParameterValue(PARAM_NAMES[i], currentParams[i] + jitter);
            } else {
                core.setParameterValue(PARAM_NAMES[i], currentParams[i]);
            }
        }

        // ---- 1.5 特殊情绪的眼睛开合控制 ----
        if (emotionControlsEyes) {
            currentEyeOpen += (targetEyeOpen - currentEyeOpen) * EMOTION_SMOOTHING;
            core.setParameterValue(PARAM_EYE_L_OPEN, currentEyeOpen);
            core.setParameterValue(PARAM_EYE_R_OPEN, currentEyeOpen);
        } else {
            // 不控制时平滑恢复
            currentEyeOpen += (1.0f - currentEyeOpen) * EMOTION_SMOOTHING;
        }

        // ---- 2. 嘴型同步（Viseme 优先，Fallback 到 RMS）----
        long now = System.currentTimeMillis();

        // 判断是否有活跃的 Viseme 数据
        boolean useViseme = visemeActive && (now - lastVisemeUpdateTime < VISEME_TIMEOUT_MS);

        if (useViseme) {
            // ---- 2a. Viseme 驱动模式（Rhubarb Lip Sync）----
            targetMouthOpen = visemeOpenY;

            // MouthForm 混合: viseme 口型 + 情绪口型的加权融合
            // 情绪口型 = targetParams[2] (ParamMouthForm from emotion)
            float emotionMouthForm = targetParams[2];
            float blendedForm = visemeForm * 0.7f + emotionMouthForm * 0.3f;
            currentVisemeForm += (blendedForm - currentVisemeForm) * VISEME_FORM_SMOOTHING;

            // 平滑 MouthOpenY
            currentMouthOpen += (targetMouthOpen - currentMouthOpen) * MOUTH_SMOOTHING;
            core.setParameterValue("ParamMouthOpenY", currentMouthOpen);

            // Viseme 驱动的 MouthForm（覆盖情绪的静态 MouthForm）
            core.setParameterValue("ParamMouthForm", currentVisemeForm);
        } else {
            // ---- 2b. RMS Fallback 模式（老逻辑）----
            if (visemeActive) {
                // Viseme 刚超时，平滑回归到情绪 MouthForm
                visemeActive = false;
                currentVisemeForm = targetParams[2];
            }

            float rms = this.audioRms;
            // RMS 超时衰减
            if (now - lastRmsUpdateTime > RMS_TIMEOUT_MS) {
                rms = 0.0f;
            }

            if (rms > 0.01f) {
                targetMouthOpen = Math.min(1.0f, (float) Math.sqrt(rms) * RMS_SCALE);
            } else {
                targetMouthOpen = Math.max(0.0f,
                        (float) (Math.sin(elapsedTime * 2.5) * 0.04));
            }

            currentMouthOpen += (targetMouthOpen - currentMouthOpen) * MOUTH_SMOOTHING;
            core.setParameterValue("ParamMouthOpenY", currentMouthOpen);
            // RMS 模式下 MouthForm 由情绪控制（已在第 1 步设置）
        }

        // ---- 3. 更新当前情绪标记 ----
        currentEmotion = targetEmotion;
    }

    // ============================================================
    //  Getters
    // ============================================================
    public String getCurrentEmotion() {
        return currentEmotion;
    }

    public float getCurrentMouthOpen() {
        return currentMouthOpen;
    }

    /** 当前情绪是否在控制眼睛开合（如 cry/surprise/fear），此时 Main 的自动眨眼应暂停 */
    public boolean isEmotionControllingEyes() {
        return emotionControlsEyes;
    }
}
