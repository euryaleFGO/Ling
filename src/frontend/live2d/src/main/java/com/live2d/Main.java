package com.live2d;

import com.live2d.core.Core;
import com.live2d.core.CubismCore;
import com.live2d.model.Model;
import com.live2d.platform.WindowsTransparency;
import org.lwjgl.BufferUtils;
import org.lwjgl.glfw.GLFWErrorCallback;
import org.lwjgl.glfw.GLFWVidMode;
import org.lwjgl.glfw.GLFWNativeWin32;
import org.lwjgl.opengl.GL;
import org.lwjgl.stb.STBImage;
import org.lwjgl.system.MemoryStack;

import java.nio.ByteBuffer;
import java.nio.FloatBuffer;
import java.nio.IntBuffer;
import java.nio.ShortBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.opengl.GL33.*;
import static org.lwjgl.system.MemoryUtil.*;

/**
 * Live2D Desktop Pet - Transparent LWJGL Window
 */
public class Main {
    private long window;
    private int width = 1600;
    private int height = 1200;
    
    private Model model;
    private int shaderProgram;
    private List<Integer> textureIds = new ArrayList<>();
    
    private int[] vaos;
    private int[] vboVertices;
    private int[] vboUvs;
    private int[] vboModelPos;
    private int[] ebos;
    
    private CubismClippingManager clippingManager;
    
    private float canvasWidth;
    private float canvasHeight;
    private float canvasOriginX;
    private float canvasOriginY;
    private float pixelsPerUnit;
    
    private float modelScale = 1.0f;
    private float userScale = 1.0f;  // 用户通过滚轮控制的缩放比例
    private float offsetX = 0.0f;
    private float offsetY = 0.0f;
    
    private double startTime;
    private double nextBlinkTime;
    private double blinkStartTime;
    private int blinkPhase = 0;  // 0=idle, 1=closing, 2=opening (AIRI 风格)
    private float blinkStartLeft = 1.0f;
    private float blinkStartRight = 1.0f;

    // 眼跳 (Eye Saccade，参考 AIRI)
    private double lastMouseMoveTime = 0.0;
    private double nextSaccadeAt = 0.0;
    private float targetEyeBallX = 0.0f;
    private float targetEyeBallY = 0.0f;
    private float currentEyeBallX = 0.0f;
    private float currentEyeBallY = 0.0f;
    
    private double mouseX = 0.0;
    private double mouseY = 0.0;
    private double targetAngleX = 0.0;
    private double targetAngleY = 0.0;
    private double currentAngleX = 0.0;
    private double currentAngleY = 0.0;
    private boolean draggingWindow = false;
    private boolean draggingModel = false;
    private double dragStartX = 0.0;  // 窗口内相对坐标（拖动开始时的鼠标位置）
    private double dragStartY = 0.0;  // 窗口内相对坐标（拖动开始时的鼠标位置）
    private int windowStartX = 0;     // 拖动开始时的窗口位置
    private int windowStartY = 0;      // 拖动开始时的窗口位置
    
    private int frameCount = 0;
    private long lastFpsTime = 0;
    
    // 气泡框相关
    private SpeechBubble speechBubble;

    // 动作播放器（Agent 根据 LLM 情绪自主触发，参考 AIRI）
    private MotionPlayer motionPlayer;

    // 表情控制器（情绪映射 + 嘴型同步）
    private ExpressionController expressionController;

    private double lastLoopTime = 0;

    // 用户不交互时自动播放 Idle 动作：
    // 定义「事件」：对话状态变化为非 idle、收到 LLM/用户触发的动作指令（motion）
    // 1）无事件满 60 秒后，开始进入“随机动作模式”
    // 2）在该模式下，每隔 60 秒播放一次随机 Idle 动作
    private static final long IDLE_EVENT_THRESHOLD_MS = 60_000;      // 无事件多久后开始做动作
    private static final long IDLE_MOTION_INTERVAL_MS = 60_000;      // 进入后每隔多久做一个动作
    private long lastEventTimeMs = 0;        // 最近一次「事件」发生时间
    private long lastAutoMotionTimeMs = 0;   // 最近一次自动 Idle 动作时间
    
    private static final String VERTEX_SHADER = """
        #version 330 core
        layout (location = 0) in vec2 position;
        layout (location = 1) in vec2 texCoord;
        layout (location = 2) in vec2 modelPos;
        out vec2 TexCoord;
        out vec2 ModelPos;
        uniform mat4 projection;
        void main() {
            gl_Position = projection * vec4(position, 0.0, 1.0);
            TexCoord = texCoord;
            ModelPos = modelPos;
        }
        """;
    
    private static final String FRAGMENT_SHADER = """
        #version 330 core
        in vec2 TexCoord;
        in vec2 ModelPos;
        out vec4 FragColor;
        uniform sampler2D texture0;
        uniform sampler2D maskTexture;
        uniform float alpha;
        uniform int useMask;
        uniform vec4 maskLayout;
        uniform vec4 modelBounds;
        void main() {
            vec4 texColor = texture(texture0, TexCoord);
            float maskVal = 1.0;
            if (useMask != 0 && modelBounds.z > modelBounds.x && modelBounds.w > modelBounds.y) {
                vec2 uv = vec2(
                    maskLayout.x + (ModelPos.x - modelBounds.x) / (modelBounds.z - modelBounds.x) * maskLayout.z,
                    maskLayout.y + (ModelPos.y - modelBounds.y) / (modelBounds.w - modelBounds.y) * maskLayout.w
                );
                maskVal = texture(maskTexture, uv).a;
            }
            FragColor = vec4(texColor.rgb, texColor.a * alpha * maskVal);
        }
        """;
    
    public static void main(String[] args) {
        System.out.println("========================================");
        System.out.println("  Live2D Desktop Pet - Transparent");
        System.out.println("  Press ESC to exit");
        System.out.println("========================================");
        System.out.println();
        
        new Main().run();
    }
    
    public void run() {
        init();
        loop();
        cleanup();
    }
    
    private void init() {
        GLFWErrorCallback.createPrint(System.err).set();
        
        if (!glfwInit()) {
            throw new RuntimeException("Failed to initialize GLFW");
        }
        
        glfwDefaultWindowHints();
        glfwWindowHint(GLFW_TRANSPARENT_FRAMEBUFFER, GLFW_TRUE);
        glfwWindowHint(GLFW_DECORATED, GLFW_FALSE);
        glfwWindowHint(GLFW_FLOATING, GLFW_TRUE);
        glfwWindowHint(GLFW_ALPHA_BITS, 8);
        glfwWindowHint(GLFW_DEPTH_BITS, 0);
        glfwWindowHint(GLFW_STENCIL_BITS, 0);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
        glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
        glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
        glfwWindowHint(GLFW_VISIBLE, GLFW_TRUE);
        glfwWindowHint(GLFW_RESIZABLE, GLFW_FALSE);
        
        window = glfwCreateWindow(width, height, "Live2D Pet", NULL, NULL);
        if (window == NULL) {
            throw new RuntimeException("Failed to create GLFW window");
        }
        
        System.out.println("[OK] GLFW window created");
        
        try {
            long hwnd = GLFWNativeWin32.glfwGetWin32Window(window);
            if (hwnd != 0) {
                WindowsTransparency.enableTransparency(hwnd);
            }
        } catch (Exception e) {
            System.err.println("[WARN] Transparency config failed: " + e.getMessage());
        }
        
        GLFWVidMode vidmode = glfwGetVideoMode(glfwGetPrimaryMonitor());
        if (vidmode != null) {
            glfwSetWindowPos(window, 
                vidmode.width() - width - 20, 
                vidmode.height() - height - 60);
        }
        
        glfwSetCursorPosCallback(window, (win, xpos, ypos) -> {
            mouseX = xpos;
            mouseY = ypos;
            lastMouseMoveTime = glfwGetTime();
            targetAngleX = ((mouseX / width) - 0.5) * 60.0;
            targetAngleY = -((mouseY / height) - 0.5) * 60.0;
            
            if (draggingWindow) {
                // 计算鼠标在窗口内的移动距离
                double dx = xpos - dragStartX;
                double dy = ypos - dragStartY;
                
                // 使用移动距离更新窗口位置
                int newX = windowStartX + (int) dx;
                int newY = windowStartY + (int) dy;
                glfwSetWindowPos(window, newX, newY);
            } else if (draggingModel) {
                double dx = xpos - dragStartX;
                double dy = ypos - dragStartY;
                offsetX += (float) dx;
                offsetY += (float) dy;
                dragStartX = xpos;
                dragStartY = ypos;
            }
        });
        
        glfwSetScrollCallback(window, (win, xoffset, yoffset) -> {
            userScale *= (float) Math.pow(1.1, yoffset);
            userScale = Math.max(0.3f, Math.min(3.0f, userScale));
        });
        
        glfwSetMouseButtonCallback(window, (win, button, action, mods) -> {
            if (button == GLFW_MOUSE_BUTTON_LEFT && action == GLFW_PRESS) {
                // 开始拖动窗口
                draggingWindow = true;
                // 记录拖动开始时的鼠标位置（窗口内相对坐标）
                dragStartX = mouseX;
                dragStartY = mouseY;
                
                // 记录拖动开始时的窗口位置（屏幕绝对坐标）
                int[] px = new int[1];
                int[] py = new int[1];
                glfwGetWindowPos(window, px, py);
                windowStartX = px[0];
                windowStartY = py[0];
            } else if (button == GLFW_MOUSE_BUTTON_LEFT && action == GLFW_RELEASE) {
                // 停止拖动窗口
                draggingWindow = false;
            }
            if (button == GLFW_MOUSE_BUTTON_RIGHT && action == GLFW_PRESS) {
                // 右键拖动模型（在窗口内移动模型位置）
                draggingModel = true;
                dragStartX = mouseX;
                dragStartY = mouseY;
            } else if (button == GLFW_MOUSE_BUTTON_RIGHT && action == GLFW_RELEASE) {
                draggingModel = false;
            }
        });
        
        glfwMakeContextCurrent(window);
        glfwSwapInterval(1);
        GL.createCapabilities();
        
        String renderer = glGetString(GL_RENDERER);
        int[] alphaBits = new int[1];
        glGetIntegerv(GL_ALPHA_BITS, alphaBits);
        
        System.out.println("\n[GPU] " + renderer);
        System.out.println("[GPU] Alpha bits: " + alphaBits[0]);
        if (alphaBits[0] == 0) {
            System.out.println("[WARN] Alpha bits = 0, transparency may not work");
            System.out.println("[HINT] Set java.exe to 'Power saving' in Windows Graphics Settings");
        }
        System.out.println();
        
        glViewport(0, 0, width, height);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
        glDisable(GL_DEPTH_TEST);
        
        model = new Model();
        String modelPath = "res";
        System.out.println("Loading model: " + modelPath);
        if (!model.load(modelPath)) {
            throw new RuntimeException("Failed to load model");
        }
        System.out.println("[OK] Model loaded");
        
        createShaderProgram();
        loadTextures();
        loadCanvasInfo();
        updateScale();
        initializeBuffers();
        clippingManager = new CubismClippingManager();
        clippingManager.initialize(model.getCore(), canvasWidth, canvasHeight,
                canvasOriginX, canvasOriginY, pixelsPerUnit, textureIds, vaos, vboVertices, vboUvs, ebos);
        
        startTime = glfwGetTime();
        lastMouseMoveTime = startTime;
        blinkStartTime = startTime;
        nextBlinkTime = startTime + (3.0 + ThreadLocalRandom.current().nextDouble() * 5.0);  // AIRI: 3~8s
        nextSaccadeAt = startTime + randomSaccadeIntervalSeconds();
        lastFpsTime = System.currentTimeMillis();
        
        System.out.println("[OK] Initialization complete");
        System.out.println("  Window: " + width + "x" + height + " | Transparent: Yes | TopMost: Yes");
        
        // 初始化气泡框
        speechBubble = new SpeechBubble(width, height);

        // 初始化动作播放器
        motionPlayer = new MotionPlayer(modelPath);
        if (motionPlayer.loadModelConfig("res/hiyori_free_t08.model3.json")) {
            System.out.println("[OK] 动作组加载完成");
        } else {
            System.out.println("[WARN] 动作组加载失败，将仅使用表情参数");
        }

        // 初始化表情控制器
        expressionController = new ExpressionController();
        lastLoopTime = glfwGetTime();
    }
    
    private void loop() {
        while (!glfwWindowShouldClose(window)) {
            Core core = model.getCore();
            if (core != null && core.isInitialized()) {
                updateModelParameters(core);

                // 检查并播放待触发的动作（Agent 根据 LLM 情绪 / 工具调用）
                if (speechBubble != null && motionPlayer != null) {
                    String[] pending = speechBubble.takePendingMotion();
                    if (pending != null && pending.length >= 1) {
                        String group = pending[0];
                        int index = pending.length >= 2 ? Integer.parseInt(pending[1]) : 0;
                        motionPlayer.playMotion(group, index);
                        // 这是一个「事件」：收到来自 LLM/用户的明确动作指令
                        long nowMs = System.currentTimeMillis();
                        lastEventTimeMs = nowMs;
                        lastAutoMotionTimeMs = nowMs;  // 重置自动动作计时，避免立刻再次触发
                    }
                }

                // 用户不交互时自动播放 Idle 动作：
                // - 仅当对话状态为 idle
                // - 且距离最近一次「事件」已超过 IDLE_EVENT_THRESHOLD_MS
                // - 且距离上一次自动 Idle 动作已超过 IDLE_MOTION_INTERVAL_MS
                if (speechBubble != null && motionPlayer != null) {
                    String state = speechBubble.getConversationState();
                    if (!"idle".equals(state)) {
                        // 非 idle 状态视为有「事件」发生（在说话 / 处理 / 监听）
                        long nowMs = System.currentTimeMillis();
                        lastEventTimeMs = nowMs;
                    } else {
                        long nowMs = System.currentTimeMillis();
                        // 无事件时间已超过阈值，且距离上一次自动动作超过固定间隔
                        if ((nowMs - lastEventTimeMs) >= IDLE_EVENT_THRESHOLD_MS
                                && (nowMs - lastAutoMotionTimeMs) >= IDLE_MOTION_INTERVAL_MS) {
                            int count = motionPlayer.getMotionCount("Idle");
                            if (count > 0) {
                                int index = ThreadLocalRandom.current().nextInt(count);
                                motionPlayer.playMotion("Idle", index);
                                lastAutoMotionTimeMs = nowMs;
                            }
                        }
                    }
                }

                // 动作播放（覆盖其控制的参数，如 ParamAngleX/Y、身体等）
                if (motionPlayer != null) {
                    double now = glfwGetTime();
                    double dt = lastLoopTime > 0 ? now - lastLoopTime : 0.016;
                    lastLoopTime = now;
                    motionPlayer.update(core, dt);
                }

                // 从 SpeechBubble 获取情绪 / RMS / Viseme，驱动表情控制器
                // 始终在动作之后执行，这样情绪/口型可以自然地覆盖并“拉回”状态，避免动作结束时瞬间跳变
                if (speechBubble != null && expressionController != null) {
                    expressionController.setEmotion(speechBubble.getCurrentEmotion());
                    expressionController.setAudioRms(speechBubble.getAudioRms());
                    // Rhubarb Viseme 精确口型（有数据时自动覆盖 RMS）
                    if (speechBubble.hasActiveViseme()) {
                        expressionController.setViseme(
                            speechBubble.getVisemeOpenY(),
                            speechBubble.getVisemeForm()
                        );
                    }
                    double elapsed = glfwGetTime() - startTime;
                    expressionController.update(core, elapsed);
                }

                core.update();
            }
            
            render();
            if (speechBubble != null) {
                speechBubble.update();
                speechBubble.render();
            }
            glfwSwapBuffers(window);
            glfwPollEvents();
            
            frameCount++;
            long now = System.currentTimeMillis();
            // 每 30 秒打印一次 FPS，避免终端刷屏
            if (now - lastFpsTime >= 30_000) {
                int fps = (int) (frameCount / 30.0);
                System.out.println("[FPS] " + fps);
                frameCount = 0;
                lastFpsTime = now;
            }
        }
    }
    
    private void render() {
        glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        
        Core core = model.getCore();
        if (core == null || !core.isInitialized()) {
            return;
        }
        
        if (clippingManager != null && clippingManager.hasMasks()) {
            clippingManager.renderMasks(core, textureIds);
        }
        glViewport(0, 0, width, height);
        
        FloatBuffer projectionMatrix = BufferUtils.createFloatBuffer(16);
        projectionMatrix.put(new float[] {
            2f / width, 0, 0, 0,
            0, 2f / -height, 0, 0,
            0, 0, -1, 0,
            -1, 1, 0, 1
        });
        projectionMatrix.flip();
        
        int drawableCount = core.getDrawableCount();
        int[] renderOrders = core.getDrawableRenderOrders();
        
        Integer[] sortedIndices = new Integer[drawableCount];
        for (int i = 0; i < drawableCount; i++) {
            sortedIndices[i] = i;
        }
        java.util.Arrays.sort(sortedIndices, (a, b) -> Integer.compare(renderOrders[a], renderOrders[b]));
        
        for (int idx = 0; idx < drawableCount; idx++) {
            int i = sortedIndices[idx];
            
            if (!core.isDrawableVisible(i)) continue;
            
            CubismCore.csmVector2[] vertices = core.getDrawableVertices(i);
            if (vertices == null || vertices.length == 0) continue;
            
            short[] indices = core.getDrawableIndices(i);
            if (indices == null || indices.length == 0) continue;
            
            CubismCore.csmVector2[] uvs = core.getDrawableVertexUvs(i);
            if (uvs == null || uvs.length == 0) continue;
            
            int textureIndex = core.getDrawableTextureIndex(i);
            if (textureIndex < 0 || textureIndex >= textureIds.size()) continue;
            
            float drawableOpacity = core.getDrawableOpacity(i);
            int parentPartIndex = core.getDrawableParentPartIndex(i);
            float partOpacity = (parentPartIndex >= 0) ? core.getPartOpacity(parentPartIndex) : 1.0f;
            float alpha = drawableOpacity * partOpacity;
            
            int maskCtx = (clippingManager != null) ? clippingManager.getContextForDrawable(i) : -1;
            boolean useMask = maskCtx >= 0 && clippingManager != null && clippingManager.hasMasks();
            
            glUseProgram(shaderProgram);
            int projLoc = glGetUniformLocation(shaderProgram, "projection");
            glUniformMatrix4fv(projLoc, false, projectionMatrix);
            glUniform1f(glGetUniformLocation(shaderProgram, "alpha"), alpha);
            glUniform1i(glGetUniformLocation(shaderProgram, "useMask"), useMask ? 1 : 0);
            
            glActiveTexture(GL_TEXTURE0);
            glBindTexture(GL_TEXTURE_2D, textureIds.get(textureIndex));
            glUniform1i(glGetUniformLocation(shaderProgram, "texture0"), 0);
            glActiveTexture(GL_TEXTURE1);
            if (useMask) {
                glBindTexture(GL_TEXTURE_2D, clippingManager.getMaskTextureId());
                float[] layout = clippingManager.getLayoutForContext(maskCtx);
                float[] bounds = clippingManager.getModelBounds();
                if (layout != null && layout.length >= 4 && bounds != null && bounds.length >= 4) {
                    glUniform4f(glGetUniformLocation(shaderProgram, "maskLayout"), layout[0], layout[1], layout[2], layout[3]);
                    glUniform4f(glGetUniformLocation(shaderProgram, "modelBounds"), bounds[0], bounds[1], bounds[2], bounds[3]);
                }
            } else {
                glBindTexture(GL_TEXTURE_2D, textureIds.get(0));
            }
            glUniform1i(glGetUniformLocation(shaderProgram, "maskTexture"), 1);
            
            FloatBuffer vertexBuffer = BufferUtils.createFloatBuffer(vertices.length * 2);
            FloatBuffer modelPosBuffer = BufferUtils.createFloatBuffer(vertices.length * 2);
            for (CubismCore.csmVector2 v : vertices) {
                vertexBuffer.put(transformX(v.X));
                vertexBuffer.put(transformY(v.Y));
                modelPosBuffer.put(v.X);
                modelPosBuffer.put(v.Y);
            }
            vertexBuffer.flip();
            modelPosBuffer.flip();
            
            FloatBuffer uvBuffer = BufferUtils.createFloatBuffer(uvs.length * 2);
            for (CubismCore.csmVector2 uv : uvs) {
                uvBuffer.put(uv.X);
                uvBuffer.put(1.0f - uv.Y);
            }
            uvBuffer.flip();
            
            ShortBuffer indexBuffer = BufferUtils.createShortBuffer(indices.length);
            indexBuffer.put(indices);
            indexBuffer.flip();
            
            glBindVertexArray(vaos[i]);
            glBindBuffer(GL_ARRAY_BUFFER, vboVertices[i]);
            glBufferData(GL_ARRAY_BUFFER, vertexBuffer, GL_DYNAMIC_DRAW);
            glBindBuffer(GL_ARRAY_BUFFER, vboUvs[i]);
            glBufferData(GL_ARRAY_BUFFER, uvBuffer, GL_DYNAMIC_DRAW);
            glBindBuffer(GL_ARRAY_BUFFER, vboModelPos[i]);
            glBufferData(GL_ARRAY_BUFFER, modelPosBuffer, GL_DYNAMIC_DRAW);
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebos[i]);
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, indexBuffer, GL_DYNAMIC_DRAW);
            
            glDrawElements(GL_TRIANGLES, indices.length, GL_UNSIGNED_SHORT, 0);
        }
    }
    
    /** AIRI 风格：随机眼跳间隔（秒），基于概率分布 */
    private double randomSaccadeIntervalSeconds() {
        double r = ThreadLocalRandom.current().nextDouble();
        double[] cumul = {0.075, 0.185, 0.31, 0.45, 0.575, 0.625, 0.665, 0.695, 0.715, 1.0};
        int[] baseMs = {800, 1200, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4400};  // AIRI 源码 P[i][1]=P[i-1][1]+400
        for (int i = 0; i < cumul.length; i++) {
            if (r <= cumul[i]) {
                return (baseMs[i] + ThreadLocalRandom.current().nextDouble() * 400) / 1000.0;
            }
        }
        return 4.0 + ThreadLocalRandom.current().nextDouble() * 2.0;
    }

    /** AIRI 风格：easeOutQuad = 1 - (1-t)² */
    private static float easeOutQuad(float t) {
        return 1.0f - (1.0f - t) * (1.0f - t);
    }

    /** AIRI 风格：easeInQuad = t² */
    private static float easeInQuad(float t) {
        return t * t;
    }

    private void updateModelParameters(Core core) {
        double currentTime = glfwGetTime();
        double elapsed = currentTime - startTime;
        
        float breathValue = (float) (Math.sin(elapsed * 2.0) * 0.5);
        core.setParameterValue("ParamBreath", breathValue);
        
        double smoothing = 0.15;
        currentAngleX += (targetAngleX - currentAngleX) * smoothing;
        currentAngleY += (targetAngleY - currentAngleY) * smoothing;
        
        core.setParameterValue("ParamAngleX", (float) currentAngleX);
        core.setParameterValue("ParamAngleY", (float) currentAngleY);
        core.setParameterValue("ParamAngleZ", (float) (currentAngleX * 0.3));

        // 眼球：鼠标跟随 or 空闲眼跳 (AIRI 风格)
        double mouseIdleSeconds = currentTime - lastMouseMoveTime;
        if (mouseIdleSeconds > 2.0) {
            // 空闲 2 秒后：随机眼跳
            if (currentTime >= nextSaccadeAt) {
                targetEyeBallX = (float) (ThreadLocalRandom.current().nextDouble() * 2.0 - 1.0) * 0.5f;
                targetEyeBallY = (float) (ThreadLocalRandom.current().nextDouble() * 1.7 - 1.0) * 0.5f;  // Y 偏上
                nextSaccadeAt = currentTime + randomSaccadeIntervalSeconds();
            }
            currentEyeBallX += (targetEyeBallX - currentEyeBallX) * 0.3f;
            currentEyeBallY += (targetEyeBallY - currentEyeBallY) * 0.3f;
        } else {
            // 鼠标活跃：跟随鼠标
            float mouseEyeX = (float) (currentAngleX * 0.8 / 30.0);
            float mouseEyeY = (float) (currentAngleY * 0.8 / 30.0);
            currentEyeBallX += (mouseEyeX - currentEyeBallX) * 0.3f;
            currentEyeBallY += (mouseEyeY - currentEyeBallY) * 0.3f;
        }
        core.setParameterValue("ParamEyeBallX", currentEyeBallX);
        core.setParameterValue("ParamEyeBallY", currentEyeBallY);
        
        float bodySwayX = (float) (Math.sin(elapsed * 0.5) * 5.0 + currentAngleX * 0.2);
        float bodySwayY = (float) (Math.cos(elapsed * 0.6) * 3.0 + currentAngleY * 0.1);
        core.setParameterValue("ParamBodyAngleX", bodySwayX);
        core.setParameterValue("ParamBodyAngleY", bodySwayY);
        core.setParameterValue("ParamBodyAngleZ", bodySwayX * 0.5f);
        
        // AIRI 风格眨眼：easeOutQuad 闭眼 + easeInQuad 睁眼，各 200ms，间隔 3~8s
        if (!expressionController.isEmotionControllingEyes()) {
            float eyeLOpen = 1.0f;
            float eyeROpen = 1.0f;
            double blinkElapsedMs = (currentTime - blinkStartTime) * 1000.0;
            if (blinkPhase == 0 && currentTime >= nextBlinkTime) {
                blinkPhase = 1;
                blinkStartTime = currentTime;
                blinkStartLeft = 1.0f;
                blinkStartRight = 1.0f;
            }
            if (blinkPhase == 1) {
                float progress = (float) Math.min(1.0, blinkElapsedMs / 200.0);
                float eased = easeOutQuad(progress);
                eyeLOpen = Math.max(0, blinkStartLeft * (1.0f - eased));
                eyeROpen = Math.max(0, blinkStartRight * (1.0f - eased));
                if (progress >= 1.0f) {
                    blinkPhase = 2;
                    blinkStartTime = currentTime;
                }
            } else if (blinkPhase == 2) {
                float progress = (float) Math.min(1.0, blinkElapsedMs / 200.0);
                float eased = easeInQuad(progress);
                eyeLOpen = Math.min(1.0f, blinkStartLeft * eased);
                eyeROpen = Math.min(1.0f, blinkStartRight * eased);
                if (progress >= 1.0f) {
                    blinkPhase = 0;
                    nextBlinkTime = currentTime + (3.0 + ThreadLocalRandom.current().nextDouble() * 5.0);
                }
            }
            core.setParameterValue("ParamEyeLOpen", eyeLOpen);
            core.setParameterValue("ParamEyeROpen", eyeROpen);
        }
        
        // 注意：MouthForm / MouthOpenY / BrowLY / BrowRY / EyeSmile / Cheek
        // 已移交给 ExpressionController 管理（情绪映射 + 嘴型同步）
        
        float hairFront = (float) (Math.sin(elapsed * 2.0) * 0.3 + currentAngleX * 0.02);
        float hairSide = (float) (Math.cos(elapsed * 1.8) * 0.25 + currentAngleX * 0.03);
        float hairBack = (float) (Math.sin(elapsed * 1.5) * 0.2 - currentAngleY * 0.02);
        core.setParameterValue("ParamHairFront", hairFront);
        core.setParameterValue("ParamHairSide", hairSide);
        core.setParameterValue("ParamHairBack", hairBack);
    }
    
    private void createShaderProgram() {
        int vertexShader = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vertexShader, VERTEX_SHADER);
        glCompileShader(vertexShader);
        checkShaderCompilation(vertexShader, "VERTEX");
        
        int fragmentShader = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fragmentShader, FRAGMENT_SHADER);
        glCompileShader(fragmentShader);
        checkShaderCompilation(fragmentShader, "FRAGMENT");
        
        shaderProgram = glCreateProgram();
        glAttachShader(shaderProgram, vertexShader);
        glAttachShader(shaderProgram, fragmentShader);
        glLinkProgram(shaderProgram);
        
        glDeleteShader(vertexShader);
        glDeleteShader(fragmentShader);
    }
    
    private void loadTextures() {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            IntBuffer widthBuf = stack.mallocInt(1);
            IntBuffer heightBuf = stack.mallocInt(1);
            IntBuffer channelsBuf = stack.mallocInt(1);
            
            String texturePath = "res/hiyori_free_t08.2048/texture_00.png";
            ByteBuffer imageData = model.loadResourceAsBuffer(texturePath);
            
            if (imageData == null) {
                throw new RuntimeException("Failed to load texture: " + texturePath);
            }
            
            STBImage.stbi_set_flip_vertically_on_load(false);
            ByteBuffer imageBuffer = STBImage.stbi_load_from_memory(
                imageData, widthBuf, heightBuf, channelsBuf, 4);
            
            if (imageBuffer == null) {
                throw new RuntimeException("Failed to decode texture");
            }
            
            int texWidth = widthBuf.get(0);
            int texHeight = heightBuf.get(0);
            
            int textureId = glGenTextures();
            glBindTexture(GL_TEXTURE_2D, textureId);
            
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texWidth, texHeight, 
                        0, GL_RGBA, GL_UNSIGNED_BYTE, imageBuffer);
            
            textureIds.add(textureId);
            STBImage.stbi_image_free(imageBuffer);
            
            System.out.println("[OK] Texture loaded: " + texWidth + "x" + texHeight);
        }
    }
    
    private void loadCanvasInfo() {
        Core core = model.getCore();
        if (core != null && core.isInitialized()) {
            float[] canvasInfo = core.getCanvasInfo();
            if (canvasInfo != null && canvasInfo.length >= 5) {
                canvasWidth = canvasInfo[0];
                canvasHeight = canvasInfo[1];
                canvasOriginX = canvasInfo[2];
                canvasOriginY = canvasInfo[3];
                pixelsPerUnit = canvasInfo[4];
            }
        }
    }
    
    private void updateScale() {
        float windowSize = Math.min(width, height);
        float canvasSize = Math.max(canvasWidth * pixelsPerUnit, canvasHeight * pixelsPerUnit);
        
        if (canvasSize > 0) {
            modelScale = windowSize * 0.8f / canvasSize;
        }
        
        offsetX = width / 2.0f;
        offsetY = height / 2.0f;
    }
    
    private void initializeBuffers() {
        Core core = model.getCore();
        if (core == null || !core.isInitialized()) return;
        
        int drawableCount = core.getDrawableCount();
        vaos = new int[drawableCount];
        vboVertices = new int[drawableCount];
        vboUvs = new int[drawableCount];
        vboModelPos = new int[drawableCount];
        ebos = new int[drawableCount];
        
        for (int i = 0; i < drawableCount; i++) {
            vaos[i] = glGenVertexArrays();
            vboVertices[i] = glGenBuffers();
            vboUvs[i] = glGenBuffers();
            vboModelPos[i] = glGenBuffers();
            ebos[i] = glGenBuffers();
            
            glBindVertexArray(vaos[i]);
            
            glBindBuffer(GL_ARRAY_BUFFER, vboVertices[i]);
            glVertexAttribPointer(0, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
            glEnableVertexAttribArray(0);
            
            glBindBuffer(GL_ARRAY_BUFFER, vboUvs[i]);
            glVertexAttribPointer(1, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
            glEnableVertexAttribArray(1);
            
            glBindBuffer(GL_ARRAY_BUFFER, vboModelPos[i]);
            glVertexAttribPointer(2, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
            glEnableVertexAttribArray(2);
        }
        
        glBindVertexArray(0);
        System.out.println("[OK] Buffers initialized: " + drawableCount);
    }
    
    private float transformX(float liveX) {
        float size = Math.min(width, height) * userScale;
        return (liveX * size + canvasOriginX * pixelsPerUnit * modelScale * userScale) + offsetX;
    }
    
    private float transformY(float liveY) {
        float size = Math.min(width, height) * userScale;
        return (-liveY * size + canvasOriginY * pixelsPerUnit * modelScale * userScale) + offsetY;
    }
    
    private void checkShaderCompilation(int shader, String type) {
        int[] success = new int[1];
        glGetShaderiv(shader, GL_COMPILE_STATUS, success);
        if (success[0] == GL_FALSE) {
            String infoLog = glGetShaderInfoLog(shader);
            throw new RuntimeException("Shader compilation failed (" + type + "): " + infoLog);
        }
    }
    
    private void cleanup() {
        if (speechBubble != null) {
            speechBubble.cleanup();
        }
        
        if (clippingManager != null) {
            clippingManager.release();
        }
        if (vaos != null) {
            for (int vao : vaos) glDeleteVertexArrays(vao);
        }
        if (vboVertices != null) glDeleteBuffers(vboVertices);
        if (vboUvs != null) glDeleteBuffers(vboUvs);
        if (vboModelPos != null) glDeleteBuffers(vboModelPos);
        if (ebos != null) glDeleteBuffers(ebos);
        
        for (int textureId : textureIds) glDeleteTextures(textureId);
        glDeleteProgram(shaderProgram);
        
        glfwDestroyWindow(window);
        glfwTerminate();
        glfwSetErrorCallback(null).free();
    }
}
