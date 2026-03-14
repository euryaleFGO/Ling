package com.live2d;

import com.live2d.core.Core;
import com.live2d.core.CubismCore;
import org.lwjgl.BufferUtils;

import java.nio.ByteBuffer;
import java.nio.FloatBuffer;
import java.nio.ShortBuffer;
import java.util.*;

import static org.lwjgl.opengl.GL33.*;

/**
 * Cubism 裁剪蒙版管理器
 * <p>
 * 将 Mask Drawable 预渲染到 FBO，主渲染时采样蒙版进行裁剪。
 * 参考 Cubism SDK Mask Preprocessing 流程。
 */
public class CubismClippingManager {

    private static final int MASK_TEXTURE_SIZE = 1024;
    private static final int MAX_MASK_CONTEXTS = 4;  // RGBA 四通道

    private int maskFbo;
    private int maskTexture;
    private int maskShaderProgram;
    private int maskVao;
    private int maskVboVertices;
    private int maskVboUvs;
    private int maskEbo;

    /** 每个 Drawable 的裁剪上下文索引，-1 表示无蒙版 */
    private int[] drawableToContext;
    /** 每个上下文的蒙版 Drawable 索引列表 */
    private List<int[]> contextMaskDrawables;
    /** 每个上下文的布局（在纹理中的区域 0-1） */
    private float[][] contextLayout;
    /** 模型边界（用于蒙版正交投影） */
    private float modelLeft, modelRight, modelBottom, modelTop;

    private boolean initialized;

    private static final String MASK_VERTEX_SHADER = """
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

    private static final String MASK_FRAGMENT_SHADER = """
        #version 330 core
        in vec2 TexCoord;
        out vec4 FragColor;
        uniform sampler2D texture0;
        uniform float alpha;
        void main() {
            vec4 texColor = texture(texture0, TexCoord);
            FragColor = vec4(0.0, 0.0, 0.0, texColor.a * alpha);
        }
        """;

    public void initialize(Core core, float canvasWidth, float canvasHeight,
                          float canvasOriginX, float canvasOriginY, float pixelsPerUnit,
                          List<Integer> textureIds, int[] vaos, int[] vboVertices, int[] vboUvs, int[] ebos) {
        if (initialized) return;
        int drawableCount = core.getDrawableCount();

        Map<String, Integer> maskKeyToContext = new HashMap<>();
        contextMaskDrawables = new ArrayList<>();
        drawableToContext = new int[drawableCount];
        Arrays.fill(drawableToContext, -1);

        for (int i = 0; i < drawableCount; i++) {
            int maskCount = core.getDrawableMaskCount(i);
            if (maskCount <= 0) continue;
            int[] masks = core.getDrawableMasks(i);
            if (masks == null || masks.length == 0) continue;
            Arrays.sort(masks);
            String key = Arrays.toString(masks);
            int ctx = maskKeyToContext.getOrDefault(key, -1);
            if (ctx < 0) {
                if (contextMaskDrawables.size() >= MAX_MASK_CONTEXTS) continue;
                ctx = contextMaskDrawables.size();
                maskKeyToContext.put(key, ctx);
                contextMaskDrawables.add(masks);
            }
            drawableToContext[i] = ctx;
        }

        if (contextMaskDrawables.isEmpty()) {
            initialized = true;
            return;
        }

        // 模型边界：顶点坐标使用 model units（1 unit = pixelsPerUnit pixels），原点在画布中心
        float halfW = canvasWidth / (2f * Math.max(1e-6f, pixelsPerUnit));
        float halfH = canvasHeight / (2f * Math.max(1e-6f, pixelsPerUnit));
        modelLeft = -halfW;
        modelRight = halfW;
        modelBottom = -halfH;
        modelTop = halfH;

        // 为每个上下文分配 RGBA 通道
        contextLayout = new float[contextMaskDrawables.size()][4];
        for (int i = 0; i < contextMaskDrawables.size(); i++) {
            float x = (i % 2) * 0.5f;
            float y = (i / 2) * 0.5f;
            contextLayout[i] = new float[]{x, y, 0.5f, 0.5f};
        }

        // 创建 FBO 和纹理
        maskTexture = glGenTextures();
        glBindTexture(GL_TEXTURE_2D, maskTexture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, MASK_TEXTURE_SIZE, MASK_TEXTURE_SIZE, 0,
                GL_RGBA, GL_UNSIGNED_BYTE, (ByteBuffer) null);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);

        maskFbo = glGenFramebuffers();
        glBindFramebuffer(GL_FRAMEBUFFER, maskFbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, maskTexture, 0);
        if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
            System.err.println("[Live2D] Mask FBO incomplete");
        }
        glBindFramebuffer(GL_FRAMEBUFFER, 0);

        // 蒙版着色器
        int vs = glCreateShader(GL_VERTEX_SHADER);
        glShaderSource(vs, MASK_VERTEX_SHADER);
        glCompileShader(vs);
        int fs = glCreateShader(GL_FRAGMENT_SHADER);
        glShaderSource(fs, MASK_FRAGMENT_SHADER);
        glCompileShader(fs);
        maskShaderProgram = glCreateProgram();
        glAttachShader(maskShaderProgram, vs);
        glAttachShader(maskShaderProgram, fs);
        glLinkProgram(maskShaderProgram);
        glDeleteShader(vs);
        glDeleteShader(fs);

        maskVao = glGenVertexArrays();
        maskVboVertices = glGenBuffers();
        maskVboUvs = glGenBuffers();
        maskEbo = glGenBuffers();

        glBindTexture(GL_TEXTURE_2D, 0);

        initialized = true;
        System.out.println("[Live2D] Clipping manager: " + contextMaskDrawables.size() + " mask context(s)");
    }

    /**
     * 每帧调用：将 Mask 绘制到 FBO
     */
    public void renderMasks(Core core, List<Integer> textureIds) {
        if (!initialized || contextMaskDrawables == null || contextMaskDrawables.isEmpty()) return;

        core.update();
        glBindFramebuffer(GL_FRAMEBUFFER, maskFbo);
        glViewport(0, 0, MASK_TEXTURE_SIZE, MASK_TEXTURE_SIZE);
        glClearColor(0, 0, 0, 0);
        glClear(GL_COLOR_BUFFER_BIT);

        float w = modelRight - modelLeft;
        float h = modelTop - modelBottom;
        if (w <= 0 || h <= 0) {
            glBindFramebuffer(GL_FRAMEBUFFER, 0);
            return;
        }

        float[] ortho = orthoMatrix(modelLeft, modelRight, modelBottom, modelTop);

        glUseProgram(maskShaderProgram);
        int projLoc = glGetUniformLocation(maskShaderProgram, "projection");
        glUniformMatrix4fv(projLoc, false, ortho);
        int alphaLoc = glGetUniformLocation(maskShaderProgram, "alpha");

        for (int ctx = 0; ctx < contextMaskDrawables.size(); ctx++) {
            int vpX = (ctx % 2) * (MASK_TEXTURE_SIZE / 2);
            int vpY = (ctx / 2) * (MASK_TEXTURE_SIZE / 2);
            glViewport(vpX, vpY, MASK_TEXTURE_SIZE / 2, MASK_TEXTURE_SIZE / 2);

            for (int maskDrawableIndex : contextMaskDrawables.get(ctx)) {
                if (!core.isDrawableVisible(maskDrawableIndex)) continue;
                CubismCore.csmVector2[] vertices = core.getDrawableVertices(maskDrawableIndex);
                if (vertices == null || vertices.length == 0) continue;
                short[] indices = core.getDrawableIndices(maskDrawableIndex);
                if (indices == null || indices.length == 0) continue;
                CubismCore.csmVector2[] uvs = core.getDrawableVertexUvs(maskDrawableIndex);
                if (uvs == null || uvs.length == 0) continue;
                int texIdx = core.getDrawableTextureIndex(maskDrawableIndex);
                if (texIdx < 0 || texIdx >= textureIds.size()) continue;

                float drawableOpacity = core.getDrawableOpacity(maskDrawableIndex);
                int parentPartIndex = core.getDrawableParentPartIndex(maskDrawableIndex);
                float partOpacity = parentPartIndex >= 0 ? core.getPartOpacity(parentPartIndex) : 1.0f;
                float alpha = drawableOpacity * partOpacity;

                FloatBuffer vb = BufferUtils.createFloatBuffer(vertices.length * 2);
                for (CubismCore.csmVector2 v : vertices) {
                    vb.put(v.X).put(v.Y);
                }
                vb.flip();
                FloatBuffer ub = BufferUtils.createFloatBuffer(uvs.length * 2);
                for (CubismCore.csmVector2 uv : uvs) {
                    ub.put(uv.X).put(1.0f - uv.Y);
                }
                ub.flip();
                ShortBuffer ib = BufferUtils.createShortBuffer(indices.length);
                ib.put(indices).flip();

                glActiveTexture(GL_TEXTURE0);
                glBindTexture(GL_TEXTURE_2D, textureIds.get(texIdx));
                glUniform1i(glGetUniformLocation(maskShaderProgram, "texture0"), 0);
                glUniform1f(alphaLoc, alpha);

                glBindVertexArray(maskVao);
                glBindBuffer(GL_ARRAY_BUFFER, maskVboVertices);
                glBufferData(GL_ARRAY_BUFFER, vb, GL_DYNAMIC_DRAW);
                glVertexAttribPointer(0, 2, GL_FLOAT, false, 0, 0);
                glEnableVertexAttribArray(0);
                glBindBuffer(GL_ARRAY_BUFFER, maskVboUvs);
                glBufferData(GL_ARRAY_BUFFER, ub, GL_DYNAMIC_DRAW);
                glVertexAttribPointer(1, 2, GL_FLOAT, false, 0, 0);
                glEnableVertexAttribArray(1);
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, maskEbo);
                glBufferData(GL_ELEMENT_ARRAY_BUFFER, ib, GL_DYNAMIC_DRAW);
                glDrawElements(GL_TRIANGLES, indices.length, GL_UNSIGNED_SHORT, 0);
            }
        }

        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glBindVertexArray(0);
    }

    private static float[] orthoMatrix(float left, float right, float bottom, float top) {
        float rl = right - left, tb = top - bottom;
        return new float[]{
                2 / rl, 0, 0, 0,
                0, 2 / tb, 0, 0,
                0, 0, -1, 0,
                -(right + left) / rl, -(top + bottom) / tb, 0, 1
        };
    }

    public int getMaskTextureId() { return maskTexture; }
    public boolean hasMasks() { return initialized && contextMaskDrawables != null && !contextMaskDrawables.isEmpty(); }
    public int getContextForDrawable(int drawableIndex) {
        if (drawableToContext == null || drawableIndex < 0 || drawableIndex >= drawableToContext.length)
            return -1;
        return drawableToContext[drawableIndex];
    }
    public float[] getLayoutForContext(int ctx) {
        if (contextLayout == null || ctx < 0 || ctx >= contextLayout.length) return null;
        return contextLayout[ctx];
    }
    public float[] getModelBounds() {
        return new float[]{modelLeft, modelBottom, modelRight, modelTop};
    }

    public void release() {
        if (maskFbo != 0) {
            glDeleteFramebuffers(maskFbo);
            maskFbo = 0;
        }
        if (maskTexture != 0) {
            glDeleteTextures(maskTexture);
            maskTexture = 0;
        }
        if (maskShaderProgram != 0) {
            glDeleteProgram(maskShaderProgram);
            maskShaderProgram = 0;
        }
        if (maskVao != 0) glDeleteVertexArrays(maskVao);
        if (maskVboVertices != 0) glDeleteBuffers(maskVboVertices);
        if (maskVboUvs != 0) glDeleteBuffers(maskVboUvs);
        if (maskEbo != 0) glDeleteBuffers(maskEbo);
        initialized = false;
    }
}
