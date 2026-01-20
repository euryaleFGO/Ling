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
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import okhttp3.*;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.opengl.GL33.*;
import static org.lwjgl.system.MemoryUtil.*;
import static org.lwjgl.stb.STBTruetype.*;

/**
 * Live2D Desktop Pet - Transparent LWJGL Window
 */
public class Main {
    private long window;
    private int width = 800;
    private int height = 600;
    
    private Model model;
    private int shaderProgram;
    private List<Integer> textureIds = new ArrayList<>();
    
    private int[] vaos;
    private int[] vboVertices;
    private int[] vboUvs;
    private int[] ebos;
    
    private float canvasWidth;
    private float canvasHeight;
    private float canvasOriginX;
    private float canvasOriginY;
    private float pixelsPerUnit;
    
    private float modelScale = 1.0f;
    private float offsetX = 0.0f;
    private float offsetY = 0.0f;
    
    private double startTime;
    private double lastBlinkTime;
    private double nextBlinkTime;
    private boolean isBlinking = false;
    private double blinkStartTime;
    
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
    
    private static final String VERTEX_SHADER = """
        #version 330 core
        layout (location = 0) in vec2 position;
        layout (location = 1) in vec2 texCoord;
        out vec2 TexCoord;
        uniform mat4 projection;
        void main() {
            gl_Position = projection * vec4(position, 0.0, 1.0);
            TexCoord = texCoord;
        }
        """;
    
    private static final String FRAGMENT_SHADER = """
        #version 330 core
        in vec2 TexCoord;
        out vec4 FragColor;
        uniform sampler2D texture0;
        uniform float alpha;
        void main() {
            vec4 texColor = texture(texture0, TexCoord);
            FragColor = vec4(texColor.rgb, texColor.a * alpha);
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
        
        startTime = glfwGetTime();
        lastBlinkTime = startTime;
        nextBlinkTime = startTime + 2.0 + ThreadLocalRandom.current().nextDouble() * 3.0;
        lastFpsTime = System.currentTimeMillis();
        
        System.out.println("[OK] Initialization complete");
        System.out.println("  Window: " + width + "x" + height + " | Transparent: Yes | TopMost: Yes");
        
        // 初始化气泡框
        speechBubble = new SpeechBubble(width, height);
    }
    
    private void loop() {
        while (!glfwWindowShouldClose(window)) {
            Core core = model.getCore();
            if (core != null && core.isInitialized()) {
                updateModelParameters(core);
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
            if (now - lastFpsTime >= 5000) {
                System.out.println("[FPS] " + frameCount / 5);
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
        
        glUseProgram(shaderProgram);
        
        FloatBuffer projectionMatrix = BufferUtils.createFloatBuffer(16);
        projectionMatrix.put(new float[] {
            2f / width, 0, 0, 0,
            0, 2f / -height, 0, 0,
            0, 0, -1, 0,
            -1, 1, 0, 1
        });
        projectionMatrix.flip();
        
        int projectionLoc = glGetUniformLocation(shaderProgram, "projection");
        glUniformMatrix4fv(projectionLoc, false, projectionMatrix);
        
        int alphaLoc = glGetUniformLocation(shaderProgram, "alpha");
        
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
            
            glActiveTexture(GL_TEXTURE0);
            glBindTexture(GL_TEXTURE_2D, textureIds.get(textureIndex));
            glUniform1i(glGetUniformLocation(shaderProgram, "texture0"), 0);
            glUniform1f(alphaLoc, 1.0f);
            
            FloatBuffer vertexBuffer = BufferUtils.createFloatBuffer(vertices.length * 2);
            for (CubismCore.csmVector2 v : vertices) {
                vertexBuffer.put(transformX(v.X));
                vertexBuffer.put(transformY(v.Y));
            }
            vertexBuffer.flip();
            
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
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebos[i]);
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, indexBuffer, GL_DYNAMIC_DRAW);
            
            glDrawElements(GL_TRIANGLES, indices.length, GL_UNSIGNED_SHORT, 0);
        }
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
        
        core.setParameterValue("ParamEyeBallX", (float) (currentAngleX * 0.8 / 30.0));
        core.setParameterValue("ParamEyeBallY", (float) (currentAngleY * 0.8 / 30.0));
        
        float bodySwayX = (float) (Math.sin(elapsed * 0.5) * 5.0 + currentAngleX * 0.2);
        float bodySwayY = (float) (Math.cos(elapsed * 0.6) * 3.0 + currentAngleY * 0.1);
        core.setParameterValue("ParamBodyAngleX", bodySwayX);
        core.setParameterValue("ParamBodyAngleY", bodySwayY);
        core.setParameterValue("ParamBodyAngleZ", bodySwayX * 0.5f);
        
        float eyeOpen = 1.0f;
        if (currentTime >= nextBlinkTime && !isBlinking) {
            isBlinking = true;
            blinkStartTime = currentTime;
        }
        
        if (isBlinking) {
            double blinkElapsed = currentTime - blinkStartTime;
            double blinkDuration = 0.15;
            
            if (blinkElapsed < blinkDuration) {
                double t = blinkElapsed / blinkDuration;
                if (t < 0.5) {
                    eyeOpen = 1.0f - (float)(Math.sin(t * Math.PI));
                } else {
                    eyeOpen = (float)(Math.sin((t - 0.5) * Math.PI));
                }
                eyeOpen = Math.max(0.0f, eyeOpen);
            } else {
                isBlinking = false;
                nextBlinkTime = currentTime + 2.0 + ThreadLocalRandom.current().nextDouble() * 4.0;
                eyeOpen = 1.0f;
            }
        }
        
        core.setParameterValue("ParamEyeLOpen", eyeOpen);
        core.setParameterValue("ParamEyeROpen", eyeOpen);
        
        float mouthForm = (float) (Math.sin(elapsed * 3.0) * 0.15);
        core.setParameterValue("ParamMouthForm", mouthForm);
        float mouthOpenY = (float) (Math.sin(elapsed * 2.5) * 0.1);
        core.setParameterValue("ParamMouthOpenY", Math.max(0, mouthOpenY));
        
        float browLY = (float) (Math.sin(elapsed * 1.5 + 0.5) * 0.1);
        float browRY = (float) (Math.sin(elapsed * 1.5) * 0.1);
        core.setParameterValue("ParamBrowLY", browLY);
        core.setParameterValue("ParamBrowRY", browRY);
        
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
        ebos = new int[drawableCount];
        
        for (int i = 0; i < drawableCount; i++) {
            vaos[i] = glGenVertexArrays();
            vboVertices[i] = glGenBuffers();
            vboUvs[i] = glGenBuffers();
            ebos[i] = glGenBuffers();
            
            glBindVertexArray(vaos[i]);
            
            glBindBuffer(GL_ARRAY_BUFFER, vboVertices[i]);
            glVertexAttribPointer(0, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
            glEnableVertexAttribArray(0);
            
            glBindBuffer(GL_ARRAY_BUFFER, vboUvs[i]);
            glVertexAttribPointer(1, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
            glEnableVertexAttribArray(1);
        }
        
        glBindVertexArray(0);
        System.out.println("[OK] Buffers initialized: " + drawableCount);
    }
    
    private float transformX(float liveX) {
        float size = Math.min(width, height);
        return (liveX * size + canvasOriginX * pixelsPerUnit * modelScale) + offsetX;
    }
    
    private float transformY(float liveY) {
        float size = Math.min(width, height);
        return (-liveY * size + canvasOriginY * pixelsPerUnit * modelScale) + offsetY;
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
        
        if (vaos != null) {
            for (int vao : vaos) glDeleteVertexArrays(vao);
        }
        if (vboVertices != null) glDeleteBuffers(vboVertices);
        if (vboUvs != null) glDeleteBuffers(vboUvs);
        if (ebos != null) glDeleteBuffers(ebos);
        
        for (int textureId : textureIds) glDeleteTextures(textureId);
        glDeleteProgram(shaderProgram);
        
        glfwDestroyWindow(window);
        glfwTerminate();
        glfwSetErrorCallback(null).free();
    }
}
