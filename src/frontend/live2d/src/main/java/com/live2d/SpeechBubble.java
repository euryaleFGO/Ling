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
 * 新闻播报风格字幕组件
 * 底部居中横条，流式打字效果，跟随模型位置
 */
public class SpeechBubble {
    private StringBuilder messageText = new StringBuilder();
    private AtomicReference<String> currentMessage = new AtomicReference<>("");
    private AtomicReference<String> pendingTextUpdate = new AtomicReference<>(null);
    private float alpha = 0.0f;
    private long lastMessageTime = 0;
    private long lastTextureUpdateTime = 0;

    // 流式打字效果
    private int displayedCharCount = 0;   // 当前已显示的字符数
    private int totalCharCount = 0;       // 完整文本总字符数
    private String fullPendingText = "";   // 完整待显示文本
    private static final int CHARS_PER_FRAME = 3;  // 每帧显示字符数

    private static final long MESSAGE_TIMEOUT_MS = 10000; // 10秒
    private static final float FADE_SPEED = 0.05f;

    // 新闻播报底条样式
    private static final int SUBTITLE_BOTTOM_MARGIN = 20;  // 距底部边距
    private static final float SUBTITLE_WIDTH_RATIO = 0.75f; // 占窗口宽度比例
    private static final int SUBTITLE_PADDING_H = 24;       // 水平内边距
    private static final int SUBTITLE_PADDING_V = 24;       // 垂直内边距（防裁切）
    private static final int TEXT_FONT_SIZE = 36;            // 花字大字号
    private static final int TEXT_BITMAP_PADDING = 12;       // 更大留白给发光效果

    // 模型水平中心位置（由 Main.java 传入）
    private float modelCenterX = 0.0f;

    // 计算后的字幕区域
    private int subtitleBarX;
    private int subtitleBarY;
    private int subtitleBarWidth;
    private int subtitleBarHeight = 60;
    
    private OkHttpClient httpClient;
    private ScheduledExecutorService scheduler;
    private int windowWidth;
    private int windowHeight;

    // WebSocket 通信（替代旧的 HTTP 轮询）
    private WebSocket webSocket;
    private final AtomicReference<String> currentEmotion = new AtomicReference<>("neutral");
    private volatile float audioRms = 0.0f;
    private volatile boolean wsConnected = false;
    
    // Viseme（Rhubarb Lip Sync 精确口型数据）
    private volatile float visemeOpenY = 0.0f;
    private volatile float visemeForm = 0.0f;
    private volatile long lastVisemeTime = 0;

    // 待播放的动作（由 Agent 根据 LLM 情绪自主触发）
    private final AtomicReference<String[]> pendingMotion = new AtomicReference<>(null);

    // 对话状态（idle / listening / processing / speaking），用于空闲时自动动作
    private final AtomicReference<String> conversationState = new AtomicReference<>("idle");
    
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
        layout (location = 1) in vec4 vertColor;
        out vec4 vColor;
        uniform vec2 windowSize;
        void main() {
            vec2 normalizedPos = (position / windowSize) * 2.0 - 1.0;
            gl_Position = vec4(normalizedPos.x, -normalizedPos.y, 0.0, 1.0);
            vColor = vertColor;
        }
        """;

    private static final String BUBBLE_FRAGMENT_SHADER = """
        #version 330 core
        in vec4 vColor;
        out vec4 FragColor;
        uniform vec4 color;
        uniform int useVertexColor;
        void main() {
            if (useVertexColor != 0)
                FragColor = vColor;
            else
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
            vec4 texColor = texture(textTexture, TexCoord);
            FragColor = vec4(texColor.rgb, texColor.a * textColor.a);
        }
        """;
    
    public SpeechBubble(int windowWidth, int windowHeight) {
        this.windowWidth = windowWidth;
        this.windowHeight = windowHeight;
        this.modelCenterX = windowWidth / 2.0f;
        this.httpClient = new OkHttpClient.Builder()
                .retryOnConnectionFailure(true)
                .build();
        this.scheduler = Executors.newScheduledThreadPool(1);
        initBubbleRenderer();
        startWebSocketClient();
    }

    /** 设置模型水平中心位置，字幕跟随 */
    public void setModelCenterX(float x) {
        this.modelCenterX = x;
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
        
        // 创建 VAO 和 VBO（position 2f + color 4f = 6 floats per vertex）
        bubbleVAO = glGenVertexArrays();
        bubbleVBO = glGenBuffers();

        glBindVertexArray(bubbleVAO);
        glBindBuffer(GL_ARRAY_BUFFER, bubbleVBO);

        glBufferData(GL_ARRAY_BUFFER, 6 * 6 * Float.BYTES, GL_DYNAMIC_DRAW);
        // location 0: position (2 floats)
        glVertexAttribPointer(0, 2, GL_FLOAT, false, 6 * Float.BYTES, 0);
        glEnableVertexAttribArray(0);
        // location 1: color (4 floats)
        glVertexAttribPointer(1, 4, GL_FLOAT, false, 6 * Float.BYTES, 2 * Float.BYTES);
        glEnableVertexAttribArray(1);

        glBindVertexArray(0);

        // 初始化一次几何（默认高度）
        updateBubbleGeometry();
        
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
            text = " ";
        }

        // 使用 Java AWT 生成文本图像
        int fontSize = TEXT_FONT_SIZE;
        Font font = new Font("Microsoft YaHei", Font.BOLD, fontSize);

        BufferedImage tempImg = new BufferedImage(1, 1, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g2d = tempImg.createGraphics();
        g2d.setFont(font);
        FontMetrics fm = g2d.getFontMetrics();

        // 计算字幕条宽度（80% 窗口宽度）
        subtitleBarWidth = (int) (windowWidth * SUBTITLE_WIDTH_RATIO);
        int textAreaMaxWidth = subtitleBarWidth - SUBTITLE_PADDING_H * 2;

        String[] lines = wrapTextByMetrics(text, fm, textAreaMaxWidth);
        int maxWidth = 0;
        for (String line : lines) {
            int width = fm.stringWidth(line);
            if (width > maxWidth) {
                maxWidth = width;
            }
        }

        int lineHeight = fm.getHeight();
        int totalHeight = lines.length * lineHeight;
        g2d.dispose();

        maxWidth = Math.max(maxWidth, 100);
        totalHeight = Math.max(totalHeight, lineHeight);

        // 计算字幕条位置：底部居中，跟随模型 X
        subtitleBarHeight = totalHeight + SUBTITLE_PADDING_V * 2;
        subtitleBarX = (int) (modelCenterX - subtitleBarWidth / 2.0f);
        // 限制不超出窗口
        subtitleBarX = Math.max(10, Math.min(windowWidth - subtitleBarWidth - 10, subtitleBarX));
        subtitleBarY = windowHeight - SUBTITLE_BOTTOM_MARGIN - subtitleBarHeight;

        updateBubbleGeometry();

        // 创建文本图像（加 padding 防止发光效果被裁切）
        int pad = TEXT_BITMAP_PADDING;
        int imgW = maxWidth + pad * 2;
        int imgH = totalHeight + pad * 2;
        BufferedImage textImage = new BufferedImage(imgW, imgH, BufferedImage.TYPE_INT_ARGB);
        g2d = textImage.createGraphics();
        g2d.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g2d.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
        g2d.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g2d.setFont(font);

        java.awt.font.FontRenderContext frc = g2d.getFontRenderContext();

        // 第一遍：黑色描边
        int textY = pad + fm.getAscent();
        for (String line : lines) {
            if (line.isEmpty()) { textY += lineHeight; continue; }
            java.awt.font.TextLayout tl = new java.awt.font.TextLayout(line, font, frc);
            java.awt.Shape outline = tl.getOutline(null);
            java.awt.geom.AffineTransform tx = java.awt.geom.AffineTransform.getTranslateInstance(pad, textY);
            java.awt.Shape shiftedOutline = tx.createTransformedShape(outline);
            g2d.setColor(new java.awt.Color(0, 0, 0, 220));
            g2d.setStroke(new java.awt.BasicStroke(3f, java.awt.BasicStroke.CAP_ROUND, java.awt.BasicStroke.JOIN_ROUND));
            g2d.draw(shiftedOutline);
            textY += lineHeight;
        }

        // 第二遍：白色文字
        g2d.setColor(java.awt.Color.WHITE);
        textY = pad + fm.getAscent();
        for (String line : lines) {
            g2d.drawString(line, pad, textY);
            textY += lineHeight;
        }
        g2d.dispose();

        // 第三遍：像素级渐变（白色文字叠加从上到下的蓝色 tint）
        int[] pixels = textImage.getRGB(0, 0, imgW, imgH, null, 0, imgW);
        for (int py = 0; py < imgH; py++) {
            float t = (float) py / imgH;
            for (int px = 0; px < imgW; px++) {
                int idx = py * imgW + px;
                int argb = pixels[idx];
                int a = (argb >> 24) & 0xFF;
                if (a > 0) {
                    int r = (argb >> 16) & 0xFF;
                    int g = (argb >> 8) & 0xFF;
                    int b = argb & 0xFF;
                    // 只对白色像素做渐变，黑色描边不动
                    if (r > 200 && g > 200 && b > 200) {
                        r = (int) (r * (1 - t * 0.55f));
                        g = (int) (g * (1 - t * 0.15f));
                        pixels[idx] = (a << 24) | (r << 16) | (g << 8) | b;
                    }
                }
            }
        }
        textImage.setRGB(0, 0, imgW, imgH, pixels, 0, imgW);
        
        // 转换为 OpenGL 纹理
        textTextureWidth = textImage.getWidth();
        textTextureHeight = textImage.getHeight();
        
        ByteBuffer buffer = BufferUtils.createByteBuffer(textTextureWidth * textTextureHeight * 4);
        for (int y = 0; y < textTextureHeight; y++) {
            for (int x = 0; x < textTextureWidth; x++) {
                int pixel = textImage.getRGB(x, y);
                int a = (pixel >> 24) & 0xFF;
                int r = (pixel >> 16) & 0xFF;
                int g = (pixel >> 8) & 0xFF;
                int b = pixel & 0xFF;
                buffer.put((byte) r);
                buffer.put((byte) g);
                buffer.put((byte) b);
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
        boolean scissorEnabled = glIsEnabled(GL_SCISSOR_TEST);
        int[] scissorBox = new int[4];
        glGetIntegerv(GL_SCISSOR_BOX, scissorBox);

        glUseProgram(textShaderProgram);

        int windowSizeLoc = glGetUniformLocation(textShaderProgram, "windowSize");
        if (windowSizeLoc >= 0) {
            glUniform2f(windowSizeLoc, windowWidth, windowHeight);
        }

        int textColorLoc = glGetUniformLocation(textShaderProgram, "textColor");
        if (textColorLoc >= 0) {
            glUniform4f(textColorLoc, 1.0f, 1.0f, 1.0f, alpha);
        }

        // 文本居中于字幕条
        float textX = subtitleBarX + (subtitleBarWidth - textTextureWidth) / 2.0f;
        float textY = subtitleBarY + SUBTITLE_PADDING_V;
        float textW = textTextureWidth;
        float textH = textTextureHeight;

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

        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, textTexture);
        int textureLoc = glGetUniformLocation(textShaderProgram, "textTexture");
        if (textureLoc >= 0) {
            glUniform1i(textureLoc, 0);
        }

        glBindVertexArray(textVAO);
        glBindBuffer(GL_ARRAY_BUFFER, textVBO);

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

        glDrawArrays(GL_TRIANGLES, 0, 6);

        glBindTexture(GL_TEXTURE_2D, currentTexture[0]);
        glBindVertexArray(currentVAO[0]);
        glUseProgram(currentProgram[0]);
    }
    
    public void update() {
        long now = System.currentTimeMillis();

        // 检查是否有新消息到达
        String pendingText = pendingTextUpdate.getAndSet(null);
        if (pendingText != null) {
            fullPendingText = pendingText;
            totalCharCount = pendingText.length();
            displayedCharCount = 0;
            lastTextureUpdateTime = now;
        }

        // 流式打字效果：每帧显示 CHARS_PER_FRAME 个字符
        if (displayedCharCount < totalCharCount) {
            displayedCharCount = Math.min(displayedCharCount + CHARS_PER_FRAME, totalCharCount);
            String visibleText = fullPendingText.substring(0, displayedCharCount);
            updateTextTexture(visibleText);
        }

        // 10秒无新消息后淡出
        if (lastMessageTime > 0 && now - lastMessageTime > MESSAGE_TIMEOUT_MS && alpha > 0.0f) {
            alpha = Math.max(0.0f, alpha - FADE_SPEED);
            if (alpha <= 0.0f) {
                synchronized (messageText) {
                    messageText.setLength(0);
                    currentMessage.set("");
                    fullPendingText = "";
                    displayedCharCount = 0;
                    totalCharCount = 0;
                    lastMessageTime = 0;
                }
            }
        }
    }
    
    public void render() {
        if (alpha <= 0.0f || bubbleShaderProgram == 0) {
            return;
        }

        String text = pendingTextUpdate.get();
        if (text == null || text.isEmpty()) {
            text = currentMessage.get();
        }
        if (text == null || text.isEmpty()) {
            return;
        }

        // 保存当前状态（必须保存 glBlendFuncSeparate 的 4 个因子）
        int[] currentProgram = new int[1];
        glGetIntegerv(GL_CURRENT_PROGRAM, currentProgram);
        int[] currentVAO = new int[1];
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, currentVAO);
        boolean depthTestEnabled = glIsEnabled(GL_DEPTH_TEST);
        boolean blendEnabled = glIsEnabled(GL_BLEND);
        int[] blendSrcRGB = new int[1], blendDstRGB = new int[1];
        int[] blendSrcAlpha = new int[1], blendDstAlpha = new int[1];
        glGetIntegerv(GL_BLEND_SRC_RGB, blendSrcRGB);
        glGetIntegerv(GL_BLEND_DST_RGB, blendDstRGB);
        glGetIntegerv(GL_BLEND_SRC_ALPHA, blendSrcAlpha);
        glGetIntegerv(GL_BLEND_DST_ALPHA, blendDstAlpha);

        glDisable(GL_DEPTH_TEST);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

        glUseProgram(bubbleShaderProgram);
        int windowSizeLoc = glGetUniformLocation(bubbleShaderProgram, "windowSize");
        if (windowSizeLoc >= 0) {
            glUniform2f(windowSizeLoc, windowWidth, windowHeight);
        }
        int colorLoc = glGetUniformLocation(bubbleShaderProgram, "color");
        int useVertColorLoc = glGetUniformLocation(bubbleShaderProgram, "useVertexColor");

        // 1) 绘制渐变背景（使用顶点颜色）
        if (useVertColorLoc >= 0) glUniform1i(useVertColorLoc, 1);
        glBindVertexArray(bubbleVAO);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        // 2) 顶部彩色渐变装饰线（蓝→青→白）
        if (useVertColorLoc >= 0) glUniform1i(useVertColorLoc, 1);
        float lineY = subtitleBarY + subtitleBarHeight - 2;
        float lineH = 2;
        float lx = subtitleBarX;
        float lw = subtitleBarWidth;
        float la = alpha * 0.9f;
        float[] lineData = {
            lx, lineY,        0.2f, 0.5f, 1.0f, la,
            lx + lw, lineY,   0.0f, 0.8f, 1.0f, la,
            lx, lineY + lineH,0.4f, 0.7f, 1.0f, la * 0.6f,
            lx + lw, lineY,   0.0f, 0.8f, 1.0f, la,
            lx + lw, lineY + lineH, 0.0f, 1.0f, 1.0f, la * 0.6f,
            lx, lineY + lineH,0.4f, 0.7f, 1.0f, la * 0.6f,
        };
        FloatBuffer lineBuf = BufferUtils.createFloatBuffer(lineData.length);
        lineBuf.put(lineData).flip();
        glBindBuffer(GL_ARRAY_BUFFER, bubbleVBO);
        glBufferSubData(GL_ARRAY_BUFFER, 0, lineBuf);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        // 恢复渐变背景几何
        updateBubbleGeometry();

        // 绘制文本
        if (textTexture != 0) {
            renderText();
        }

        // 恢复状态
        glBindVertexArray(currentVAO[0]);
        glUseProgram(currentProgram[0]);
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
        glBlendFuncSeparate(blendSrcRGB[0], blendDstRGB[0], blendSrcAlpha[0], blendDstAlpha[0]);
    }
    
    // ============================================================
    //  WebSocket 客户端（替代旧的 HTTP 轮询，实时接收消息）
    // ============================================================

    private void startWebSocketClient() {
        // 可通过环境变量覆盖（方便复刻与自定义端口/主机）：
        // - LIYING_WS_URL=ws://127.0.0.1:8765
        // - 或 LIYING_WS_HOST / LIYING_WS_PORT
        String wsUrl = System.getenv("LIYING_WS_URL");
        if (wsUrl == null || wsUrl.isBlank()) {
            String host = System.getenv("LIYING_WS_HOST");
            String port = System.getenv("LIYING_WS_PORT");
            host = (host == null || host.isBlank()) ? "localhost" : host.trim();
            port = (port == null || port.isBlank()) ? "8765" : port.trim();
            wsUrl = "ws://" + host + ":" + port;
        }

        Request request = new Request.Builder()
                .url(wsUrl)
                .build();

        httpClient.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket ws, Response response) {
                webSocket = ws;
                wsConnected = true;
                System.out.println("[SpeechBubble] WebSocket 已连接到 Python 后端");
            }

            @Override
            public void onMessage(WebSocket ws, String text) {
                handleWebSocketMessage(text);
            }

            @Override
            public void onFailure(WebSocket ws, Throwable t, Response response) {
                wsConnected = false;
                // 3 秒后自动重连
                scheduleReconnect();
            }

            @Override
            public void onClosed(WebSocket ws, int code, String reason) {
                wsConnected = false;
                System.out.println("[SpeechBubble] WebSocket 已关闭: " + reason);
                scheduleReconnect();
            }
        });
    }

    private void handleWebSocketMessage(String rawMessage) {
        try {
            JsonObject json = JsonParser.parseString(rawMessage).getAsJsonObject();
            String type = json.has("type") ? json.get("type").getAsString() : "";

            switch (type) {
                case "subtitle" -> {
                    String text = json.has("text") ? json.get("text").getAsString() : "";
                    String emotion = json.has("emotion") ? json.get("emotion").getAsString() : "neutral";
                    // boolean isFinal = json.has("is_final") && json.get("is_final").getAsBoolean();
                    if (text.isEmpty()) {
                        clearMessage();
                    } else {
                        updateMessage(text);
                        currentEmotion.set(emotion);
                    }
                }
                case "audio_rms" -> {
                    if (json.has("rms")) {
                        audioRms = json.get("rms").getAsFloat();
                    }
                }
                case "viseme" -> {
                    // Rhubarb Lip Sync 精确口型数据
                    if (json.has("openY")) {
                        visemeOpenY = json.get("openY").getAsFloat();
                    }
                    if (json.has("form")) {
                        visemeForm = json.get("form").getAsFloat();
                    }
                    lastVisemeTime = System.currentTimeMillis();
                }
                case "emotion" -> {
                    if (json.has("emotion")) {
                        currentEmotion.set(json.get("emotion").getAsString());
                    }
                }
                case "motion" -> {
                    if (json.has("group")) {
                        String group = json.get("group").getAsString();
                        int index = json.has("index") ? json.get("index").getAsInt() : 0;
                        pendingMotion.set(new String[]{group, String.valueOf(index)});
                    }
                }
                case "state" -> {
                    if (json.has("state")) {
                        conversationState.set(json.get("state").getAsString());
                    }
                }
                case "clear" -> clearMessage();
            }
        } catch (Exception e) {
            // 忽略 JSON 解析异常
        }
    }

    private void scheduleReconnect() {
        if (scheduler != null && !scheduler.isShutdown()) {
            scheduler.schedule(this::startWebSocketClient, 3, TimeUnit.SECONDS);
        }
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
            fullPendingText = "";
            displayedCharCount = 0;
            totalCharCount = 0;
            alpha = 0.0f;
            lastMessageTime = 0;
        }
    }

    // ============================================================
    //  Getters（供 Main.java → ExpressionController 使用）
    // ============================================================

    /** 获取当前情绪标签 */
    public String getCurrentEmotion() {
        return currentEmotion.get();
    }

    /** 获取当前对话状态（idle / listening / processing / speaking） */
    public String getConversationState() {
        return conversationState.get();
    }

    /** 获取当前音频 RMS 值 */
    public float getAudioRms() {
        return audioRms;
    }

    /** 获取 Viseme 嘴张开程度 (0~1) */
    public float getVisemeOpenY() {
        return visemeOpenY;
    }

    /** 获取 Viseme 嘴型形状 (-1~1) */
    public float getVisemeForm() {
        return visemeForm;
    }

    /** Viseme 数据是否新鲜（200ms 内有更新） */
    public boolean hasActiveViseme() {
        return lastVisemeTime > 0 && (System.currentTimeMillis() - lastVisemeTime) < 200;
    }

    /** 获取并清除待播放动作，返回 [group, index] 或 null */
    public String[] takePendingMotion() {
        return pendingMotion.getAndSet(null);
    }

    /** WebSocket 是否已连接 */
    public boolean isConnected() {
        return wsConnected;
    }
    
    public void cleanup() {
        // 关闭 WebSocket
        if (webSocket != null) {
            webSocket.close(1000, "shutdown");
        }
        if (scheduler != null) {
            scheduler.shutdown();
        }
        if (httpClient != null) {
            httpClient.dispatcher().executorService().shutdown();
            httpClient.connectionPool().evictAll();
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

    /**
     * 基于 FontMetrics 的真实测宽换行。
     * - 支持中文/日文等无空格文本
     * - 保留原始换行符
     */
    private String[] wrapTextByMetrics(String text, FontMetrics fm, int maxWidthPx) {
        if (text == null) {
            return new String[]{""};
        }
        List<String> out = new ArrayList<>();
        String[] paragraphs = text.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        for (String para : paragraphs) {
            if (para.isEmpty()) {
                out.add("");
                continue;
            }
            StringBuilder line = new StringBuilder();
            int lineW = 0;
            for (int i = 0; i < para.length(); i++) {
                char ch = para.charAt(i);
                int cw = fm.charWidth(ch);
                if (line.length() == 0 && cw > maxWidthPx) {
                    out.add(String.valueOf(ch));
                    continue;
                }
                if (lineW + cw > maxWidthPx && line.length() > 0) {
                    out.add(line.toString());
                    line.setLength(0);
                    lineW = 0;
                }
                line.append(ch);
                lineW += cw;
            }
            if (line.length() > 0) {
                out.add(line.toString());
            }
        }
        return out.toArray(new String[0]);
    }

    private void updateBubbleGeometry() {
        float x = subtitleBarX;
        float y = subtitleBarY;
        float w = subtitleBarWidth;
        float h = subtitleBarHeight;

        // 渐变色：底部深色 → 顶部透明
        float[] bottomColor = {0.02f, 0.02f, 0.06f, 0.85f};  // 底部：深蓝黑，较不透明
        float[] topColor    = {0.02f, 0.02f, 0.06f, 0.0f};    // 顶部：完全透明

        // 6个顶点：2个三角形组成矩形，每个顶点 (x, y, r, g, b, a)
        float[] data = {
            // 三角形1: 左下, 右下, 左上
            x, y,         bottomColor[0], bottomColor[1], bottomColor[2], bottomColor[3],
            x + w, y,     bottomColor[0], bottomColor[1], bottomColor[2], bottomColor[3],
            x, y + h,     topColor[0], topColor[1], topColor[2], topColor[3],
            // 三角形2: 右下, 右上, 左上
            x + w, y,     bottomColor[0], bottomColor[1], bottomColor[2], bottomColor[3],
            x + w, y + h, topColor[0], topColor[1], topColor[2], topColor[3],
            x, y + h,     topColor[0], topColor[1], topColor[2], topColor[3],
        };

        FloatBuffer vertexBuffer = BufferUtils.createFloatBuffer(data.length);
        vertexBuffer.put(data).flip();

        glBindBuffer(GL_ARRAY_BUFFER, bubbleVBO);
        glBufferSubData(GL_ARRAY_BUFFER, 0, vertexBuffer);
        glBindBuffer(GL_ARRAY_BUFFER, 0);
    }
}

