package com.live2d;

import okhttp3.*;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import org.lwjgl.BufferUtils;
import org.lwjgl.stb.STBTTFontinfo;
import org.lwjgl.stb.STBTruetype;
import org.lwjgl.system.MemoryStack;

import java.nio.ByteBuffer;
import java.nio.FloatBuffer;
import java.nio.IntBuffer;
import java.awt.Font;
import java.awt.FontMetrics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.InputStream;

import static org.lwjgl.opengl.GL33.*;
import static org.lwjgl.stb.STBTruetype.*;

/**
 * 气泡框组件
 * 用于显示 LLM 流式消息
 */
public class SpeechBubble {
    private StringBuilder messageText = new StringBuilder();
    private AtomicReference<String> currentMessage = new AtomicReference<>("");
    private AtomicReference<String> pendingTextUpdate = new AtomicReference<>(null);  // 待更新的文本
    private float alpha = 0.0f;
    private long lastMessageTime = 0;  // 初始化为0，表示还没有收到过消息
    private long lastTextureUpdateTime = 0;  // 上次更新纹理的时间
    
    private static final long MESSAGE_TIMEOUT_MS = 10000; // 10秒
    private static final float FADE_SPEED = 0.05f;
    private static final int BUBBLE_WIDTH = 400;
    private static final int BUBBLE_HEIGHT = 120;
    private static final int BUBBLE_PADDING = 15;
    private static final int BUBBLE_X = 50;
    private static final int BUBBLE_Y = 50;
    
    private OkHttpClient httpClient;
    private ScheduledExecutorService messageExecutor;
    private int windowWidth;
    private int windowHeight;
    
    // 气泡框渲染相关（使用现代 OpenGL）
    private int bubbleShaderProgram = 0;
    private int bubbleVAO = 0;
    private int bubbleVBO = 0;
    
    // 文本渲染相关
    private int textShaderProgram = 0;
    private int textVAO = 0;
    private int textVBO = 0;
    private int textTexture = 0;
    private int textTextureWidth = 0;
    private int textTextureHeight = 0;
    
    private static final String BUBBLE_VERTEX_SHADER = """
        #version 330 core
        layout (location = 0) in vec2 position;
        uniform vec2 windowSize;
        void main() {
            vec2 normalizedPos = (position / windowSize) * 2.0 - 1.0;
            gl_Position = vec4(normalizedPos.x, -normalizedPos.y, 0.0, 1.0);
        }
        """;
    
    private static final String BUBBLE_FRAGMENT_SHADER = """
        #version 330 core
        out vec4 FragColor;
        uniform vec4 color;
        void main() {
            FragColor = color;
        }
        """;
    
    private static final String TEXT_VERTEX_SHADER = """
        #version 330 core
        layout (location = 0) in vec2 position;
        layout (location = 1) in vec2 texCoord;
        out vec2 TexCoord;
        uniform vec2 windowSize;
        void main() {
            vec2 normalizedPos = (position / windowSize) * 2.0 - 1.0;
            gl_Position = vec4(normalizedPos.x, -normalizedPos.y, 0.0, 1.0);
            TexCoord = texCoord;
        }
        """;
    
    private static final String TEXT_FRAGMENT_SHADER = """
        #version 330 core
        in vec2 TexCoord;
        out vec4 FragColor;
        uniform sampler2D textTexture;
        uniform vec4 textColor;
        void main() {
            float alpha = texture(textTexture, TexCoord).r;
            FragColor = vec4(textColor.rgb, textColor.a * alpha);
        }
        """;
    
    public SpeechBubble(int windowWidth, int windowHeight) {
        this.windowWidth = windowWidth;
        this.windowHeight = windowHeight;
        this.httpClient = new OkHttpClient();
        this.messageExecutor = Executors.newScheduledThreadPool(1);
        initBubbleRenderer();
        startMessageReceiver();
    }
    
    private void initBubbleRenderer() {
        // 创建着色器程序
        int vertexShader = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vertexShader, BUBBLE_VERTEX_SHADER);
        glCompileShader(vertexShader);
        
        int fragmentShader = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fragmentShader, BUBBLE_FRAGMENT_SHADER);
        glCompileShader(fragmentShader);
        
        bubbleShaderProgram = glCreateProgram();
        glAttachShader(bubbleShaderProgram, vertexShader);
        glAttachShader(bubbleShaderProgram, fragmentShader);
        glLinkProgram(bubbleShaderProgram);
        
        glDeleteShader(vertexShader);
        glDeleteShader(fragmentShader);
        
        // 创建 VAO 和 VBO
        bubbleVAO = glGenVertexArrays();
        bubbleVBO = glGenBuffers();
        
        glBindVertexArray(bubbleVAO);
        glBindBuffer(GL_ARRAY_BUFFER, bubbleVBO);
        
        // 气泡框矩形顶点（两个三角形组成一个矩形）
        float[] vertices = {
            // 第一个三角形
            BUBBLE_X, BUBBLE_Y,
            BUBBLE_X + BUBBLE_WIDTH, BUBBLE_Y,
            BUBBLE_X, BUBBLE_Y + BUBBLE_HEIGHT,
            // 第二个三角形
            BUBBLE_X + BUBBLE_WIDTH, BUBBLE_Y,
            BUBBLE_X + BUBBLE_WIDTH, BUBBLE_Y + BUBBLE_HEIGHT,
            BUBBLE_X, BUBBLE_Y + BUBBLE_HEIGHT
        };
        
        FloatBuffer vertexBuffer = BufferUtils.createFloatBuffer(vertices.length);
        vertexBuffer.put(vertices);
        vertexBuffer.flip();
        
        glBufferData(GL_ARRAY_BUFFER, vertexBuffer, GL_STATIC_DRAW);
        glVertexAttribPointer(0, 2, GL_FLOAT, false, 2 * Float.BYTES, 0);
        glEnableVertexAttribArray(0);
        
        glBindVertexArray(0);
        
        // 初始化文本渲染
        initTextRenderer();
    }
    
    private void initTextRenderer() {
        // 创建文本着色器程序
        int vertexShader = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vertexShader, TEXT_VERTEX_SHADER);
        glCompileShader(vertexShader);
        
        int fragmentShader = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fragmentShader, TEXT_FRAGMENT_SHADER);
        glCompileShader(fragmentShader);
        
        textShaderProgram = glCreateProgram();
        glAttachShader(textShaderProgram, vertexShader);
        glAttachShader(textShaderProgram, fragmentShader);
        glLinkProgram(textShaderProgram);
        
        glDeleteShader(vertexShader);
        glDeleteShader(fragmentShader);
        
        // 创建文本 VAO 和 VBO
        textVAO = glGenVertexArrays();
        textVBO = glGenBuffers();
        
        // 创建文本纹理
        textTexture = glGenTextures();
        updateTextTexture("");  // 初始化空纹理
    }
    
    private void updateTextTexture(String text) {
        if (text == null || text.isEmpty()) {
            text = " ";  // 至少一个空格，避免纹理为 0
        }
        
        // 使用 Java AWT 生成文本图像
        int fontSize = 20;
        Font font = new Font("Microsoft YaHei", Font.PLAIN, fontSize);
        
        // 计算文本尺寸
        BufferedImage tempImg = new BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = tempImg.createGraphics();
        g2d.setFont(font);
        FontMetrics fm = g2d.getFontMetrics();
        
        // 文本换行处理
        String[] lines = wrapText(text, BUBBLE_WIDTH - BUBBLE_PADDING * 2, fontSize);
        int maxWidth = 0;
        for (String line : lines) {
            int width = fm.stringWidth(line);
            if (width > maxWidth) {
                maxWidth = width;
            }
        }
        
        int lineHeight = fm.getHeight();
        int totalHeight = lines.length * lineHeight;
        
        // 确保尺寸合理
        maxWidth = Math.max(maxWidth, 100);
        totalHeight = Math.max(totalHeight, lineHeight);
        
        // 创建文本图像
        BufferedImage textImage = new BufferedImage(maxWidth, totalHeight, BufferedImage.TYPE_INT_ARGB);
        g2d = textImage.createGraphics();
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g2d.setFont(font);
        g2d.setColor(java.awt.Color.WHITE);
        
        // 绘制文本
        int textY = fm.getAscent();
        for (String line : lines) {
            g2d.drawString(line, 0, textY);
            textY += lineHeight;
        }
        
        g2d.dispose();
        
        // 转换为 OpenGL 纹理
        textTextureWidth = textImage.getWidth();
        textTextureHeight = textImage.getHeight();
        
        ByteBuffer buffer = BufferUtils.createByteBuffer(textTextureWidth * textTextureHeight * 4);
        for (int y = 0; y < textTextureHeight; y++) {
            for (int x = 0; x < textTextureWidth; x++) {
                int pixel = textImage.getRGB(x, y);
                int a = (pixel >> 24) & 0xFF;
                // 使用 alpha 通道存储灰度值（白色文本）
                buffer.put((byte) a);
                buffer.put((byte) a);
                buffer.put((byte) a);
                buffer.put((byte) a);
            }
        }
        buffer.flip();
        
        // 上传纹理
        glBindTexture(GL_TEXTURE_2D, textTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, textTextureWidth, textTextureHeight, 0, GL_RGBA, GL_UNSIGNED_BYTE, buffer);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindTexture(GL_TEXTURE_2D, 0);
    }
    
    private void renderText() {
        if (textShaderProgram == 0 || textTexture == 0) {
            return;
        }
        
        // 如果纹理尺寸为0，说明还没有文本，不渲染
        if (textTextureWidth <= 0 || textTextureHeight <= 0) {
            return;
        }
        
        // 保存当前状态
        int[] currentProgram = new int[1];
        glGetIntegerv(GL_CURRENT_PROGRAM, currentProgram);
        int[] currentVAO = new int[1];
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, currentVAO);
        int[] currentTexture = new int[1];
        glGetIntegerv(GL_TEXTURE_BINDING_2D, currentTexture);
        
        // 使用文本着色器
        glUseProgram(textShaderProgram);
        
        // 设置窗口大小
        int windowSizeLoc = glGetUniformLocation(textShaderProgram, "windowSize");
        if (windowSizeLoc >= 0) {
            glUniform2f(windowSizeLoc, windowWidth, windowHeight);
        }
        
        // 设置文本颜色
        int textColorLoc = glGetUniformLocation(textShaderProgram, "textColor");
        if (textColorLoc >= 0) {
            glUniform4f(textColorLoc, 1.0f, 1.0f, 1.0f, alpha);
        }
        
        // 计算文本位置（在气泡框内）
        float textX = BUBBLE_X + BUBBLE_PADDING;
        float textY = BUBBLE_Y + BUBBLE_PADDING;
        float textW = textTextureWidth;
        float textH = textTextureHeight;
        
        // 创建文本矩形顶点
        float[] vertices = {
            textX, textY,
            textX + textW, textY,
            textX, textY + textH,
            textX + textW, textY,
            textX + textW, textY + textH,
            textX, textY + textH
        };
        
        float[] texCoords = {
            0.0f, 0.0f,
            1.0f, 0.0f,
            0.0f, 1.0f,
            1.0f, 0.0f,
            1.0f, 1.0f,
            0.0f, 1.0f
        };
        
        // 绑定纹理
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, textTexture);
        int textureLoc = glGetUniformLocation(textShaderProgram, "textTexture");
        if (textureLoc >= 0) {
            glUniform1i(textureLoc, 0);
        }
        
        // 创建并绑定 VAO
        glBindVertexArray(textVAO);
        glBindBuffer(GL_ARRAY_BUFFER, textVBO);
        
        // 上传顶点数据（位置 + 纹理坐标）
        FloatBuffer vertexBuffer = BufferUtils.createFloatBuffer(vertices.length + texCoords.length);
        for (int i = 0; i < 6; i++) {
            vertexBuffer.put(vertices[i * 2]);
            vertexBuffer.put(vertices[i * 2 + 1]);
            vertexBuffer.put(texCoords[i * 2]);
            vertexBuffer.put(texCoords[i * 2 + 1]);
        }
        vertexBuffer.flip();
        
        glBufferData(GL_ARRAY_BUFFER, vertexBuffer, GL_DYNAMIC_DRAW);
        glVertexAttribPointer(0, 2, GL_FLOAT, false, 4 * Float.BYTES, 0);
        glEnableVertexAttribArray(0);
        glVertexAttribPointer(1, 2, GL_FLOAT, false, 4 * Float.BYTES, 2 * Float.BYTES);
        glEnableVertexAttribArray(1);
        
        // 绘制
        glDrawArrays(GL_TRIANGLES, 0, 6);
        
        // 恢复状态
        glBindTexture(GL_TEXTURE_2D, currentTexture[0]);
        glBindVertexArray(currentVAO[0]);
        glUseProgram(currentProgram[0]);
    }
    
    public void update() {
        long now = System.currentTimeMillis();
        
        // 检查是否有待更新的文本（必须在主线程中更新纹理）
        // 现在是一次性完整文本，直接更新即可
        String pendingText = pendingTextUpdate.getAndSet(null);
        if (pendingText != null) {
            updateTextTexture(pendingText);
            lastTextureUpdateTime = now;
        }
        
        // 如果10秒没有新消息，开始淡出
        // 注意：只有当 lastMessageTime > 0 时才检查超时（表示曾经收到过消息）
        if (lastMessageTime > 0 && now - lastMessageTime > MESSAGE_TIMEOUT_MS && alpha > 0.0f) {
            alpha = Math.max(0.0f, alpha - FADE_SPEED);
            if (alpha <= 0.0f) {
                // 完全消失后清空消息
                synchronized (messageText) {
                    messageText.setLength(0);
                    currentMessage.set("");
                    lastMessageTime = 0;  // 重置，表示没有活跃消息
                }
            }
        }
    }
    
    public void render() {
        if (alpha <= 0.0f || bubbleShaderProgram == 0) {
            return;
        }
        
        // 优先使用待更新的文本（最新的），如果没有则使用当前消息
        String text = pendingTextUpdate.get();
        if (text == null || text.isEmpty()) {
            text = currentMessage.get();
        }
        if (text == null || text.isEmpty()) {
            return;
        }
        
        // 注意：OpenGL 3.3 Core Profile 不支持 glPushAttrib/glPopAttrib
        // 需要手动保存和恢复状态
        
        // 保存当前着色器程序
        int[] currentProgram = new int[1];
        glGetIntegerv(GL_CURRENT_PROGRAM, currentProgram);
        
        // 保存当前绑定的 VAO
        int[] currentVAO = new int[1];
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, currentVAO);
        
        // 保存当前渲染状态
        boolean depthTestEnabled = glIsEnabled(GL_DEPTH_TEST);
        boolean blendEnabled = glIsEnabled(GL_BLEND);
        int[] blendSrc = new int[1];
        int[] blendDst = new int[1];
        glGetIntegerv(GL_BLEND_SRC, blendSrc);
        glGetIntegerv(GL_BLEND_DST, blendDst);
        
        // 设置渲染状态
        glDisable(GL_DEPTH_TEST);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        
        // 使用气泡框着色器
        glUseProgram(bubbleShaderProgram);
        
        // 设置窗口大小 uniform
        int windowSizeLoc = glGetUniformLocation(bubbleShaderProgram, "windowSize");
        if (windowSizeLoc >= 0) {
            glUniform2f(windowSizeLoc, windowWidth, windowHeight);
        }
        
        // 绘制背景矩形
        int colorLoc = glGetUniformLocation(bubbleShaderProgram, "color");
        if (colorLoc >= 0) {
            glUniform4f(colorLoc, 0.15f, 0.15f, 0.2f, alpha * 0.85f);
        }
        
        glBindVertexArray(bubbleVAO);
        glDrawArrays(GL_TRIANGLES, 0, 6);
        
        // 绘制文本（只要有文本就渲染，即使尺寸为0也会在updateTextTexture中处理）
        if (textTexture != 0) {
            renderText();
        }
        
        // 恢复状态
        glBindVertexArray(currentVAO[0]);
        glUseProgram(currentProgram[0]);
        
        // 恢复渲染状态
        if (depthTestEnabled) {
            glEnable(GL_DEPTH_TEST);
        } else {
            glDisable(GL_DEPTH_TEST);
        }
        if (blendEnabled) {
            glEnable(GL_BLEND);
        } else {
            glDisable(GL_BLEND);
        }
        glBlendFunc(blendSrc[0], blendDst[0]);
    }
    
    private String lastReceivedText = "";  // 上次收到的完整文本，用于检测变化
    
    private void startMessageReceiver() {
        // 启动消息接收线程，定期检查是否有新消息
        messageExecutor.scheduleAtFixedRate(() -> {
            try {
                // 从本地 HTTP 服务器接收消息（端口 8765）
                Request request = new Request.Builder()
                    .url("http://localhost:8765/api/message")
                    .get()
                    .build();
                
                try (Response response = httpClient.newCall(request).execute()) {
                    if (response.isSuccessful() && response.body() != null) {
                        String body = response.body().string();
                        if (body != null && !body.isEmpty()) {
                            // 解析 JSON 消息
                            JsonObject json = JsonParser.parseString(body).getAsJsonObject();
                            if (json.has("text")) {
                                String text = json.get("text").getAsString();
                                if (text != null) {
                                    // 检查文本是否发生变化（避免重复处理）
                                    if (!text.equals(lastReceivedText)) {
                                        lastReceivedText = text;
                                        if (text.isEmpty()) {
                                            // 收到空消息，清空气泡框
                                            clearMessage();
                                        } else {
                                            // 收到新文本，直接替换（不追加）
                                            updateMessage(text);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            } catch (Exception e) {
                // 忽略连接错误（服务器可能未启动）
            }
        }, 0, 10, TimeUnit.SECONDS); // 每10秒检查一次
    }
    
    private void updateMessage(String text) {
        synchronized (messageText) {
            // 直接设置新消息，不追加
            messageText.setLength(0);
            messageText.append(text);
            currentMessage.set(text);
            lastMessageTime = System.currentTimeMillis();
            // 显示气泡框
            if (alpha < 1.0f) {
                alpha = 1.0f;
            }
            // 标记需要更新纹理（在主线程中更新，避免 OpenGL 上下文问题）
            // 注意：这里不立即更新，而是等待 update() 方法中的时间间隔控制
            pendingTextUpdate.set(text);
        }
    }
    
    private void appendMessage(String text) {
        // 保留此方法以保持兼容性，但现在使用 updateMessage
        updateMessage(text);
    }
    
    public void clearMessage() {
        synchronized (messageText) {
            messageText.setLength(0);
            currentMessage.set("");
            lastReceivedText = "";  // 重置上次收到的文本
            alpha = 0.0f;
            lastMessageTime = 0;  // 重置消息时间
        }
    }
    
    public void cleanup() {
        if (messageExecutor != null) {
            messageExecutor.shutdown();
        }
        if (httpClient != null) {
            httpClient.dispatcher().executorService().shutdown();
        }
        
        // 清理 OpenGL 资源
        if (bubbleVAO != 0) {
            glDeleteVertexArrays(bubbleVAO);
        }
        if (bubbleVBO != 0) {
            glDeleteBuffers(bubbleVBO);
        }
        if (bubbleShaderProgram != 0) {
            glDeleteProgram(bubbleShaderProgram);
        }
        
        if (textVAO != 0) {
            glDeleteVertexArrays(textVAO);
        }
        if (textVBO != 0) {
            glDeleteBuffers(textVBO);
        }
        if (textTexture != 0) {
            glDeleteTextures(textTexture);
        }
        if (textShaderProgram != 0) {
            glDeleteProgram(textShaderProgram);
        }
    }
    
    private String[] wrapText(String text, int maxWidth, int fontSize) {
        // 简单的文本换行（按字符数估算）
        int charsPerLine = maxWidth / (fontSize / 2);
        List<String> lines = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int end = Math.min(start + charsPerLine, text.length());
            if (end < text.length()) {
                // 尝试在空格处换行
                int lastSpace = text.lastIndexOf(' ', end);
                if (lastSpace > start) {
                    end = lastSpace;
                }
            }
            lines.add(text.substring(start, end));
            start = end;
            if (start < text.length() && text.charAt(start) == ' ') {
                start++;
            }
        }
        return lines.toArray(new String[0]);
    }
}

