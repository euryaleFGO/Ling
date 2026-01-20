package com.live2d.core;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.FloatByReference;
import com.sun.jna.Structure;

/**
 * Live2D Cubism Core JNA 接口
 * 封装 Live2D Cubism SDK 5-r.4.1 的 C API
 */
public interface CubismCore extends Library {
    
    CubismCore INSTANCE = Native.load("Live2DCubismCore", CubismCore.class);
    
    // 向量结构体
    class csmVector2 extends Structure {
        public float X;
        public float Y;
        
        @Override
        protected java.util.List<String> getFieldOrder() {
            return java.util.Arrays.asList("X", "Y");
        }
    }
    
    // 版本信息
    int csmGetVersion();
    
    // MOC 相关
    Pointer csmReviveMocInPlace(Pointer address, int size);
    
    // 模型相关
    int csmGetSizeofModel(Pointer moc);
    Pointer csmInitializeModelInPlace(Pointer moc, Pointer address, int size);
    void csmUpdateModel(Pointer model);
    
    // 画布信息
    void csmReadCanvasInfo(Pointer model, csmVector2 outSizeInPixels, 
                          csmVector2 outOriginInPixels, FloatByReference outPixelsPerUnit);
    
    // 参数
    int csmGetParameterCount(Pointer model);
    Pointer csmGetParameterIds(Pointer model);
    Pointer csmGetParameterValues(Pointer model);
    
    // 部件
    int csmGetPartCount(Pointer model);
    Pointer csmGetPartIds(Pointer model);
    Pointer csmGetPartOpacities(Pointer model);
    
    // 可绘制对象
    int csmGetDrawableCount(Pointer model);
    Pointer csmGetDrawableConstantFlags(Pointer model);
    Pointer csmGetDrawableDynamicFlags(Pointer model);
    Pointer csmGetDrawableTextureIndices(Pointer model);
    Pointer csmGetDrawableRenderOrders(Pointer model);
    Pointer csmGetDrawableVertexCounts(Pointer model);
    Pointer csmGetDrawableVertexPositions(Pointer model);
    Pointer csmGetDrawableVertexUvs(Pointer model);
    Pointer csmGetDrawableIndexCounts(Pointer model);
    Pointer csmGetDrawableIndices(Pointer model);
    
    void csmResetDrawableDynamicFlags(Pointer model);
}
